"""Nightly house league: Claude writes two new bots, they fight, the junk gets retired.

    python -m colosseum.house_league --once                 # one night, real model call
    python -m colosseum.house_league --once --dry-run       # everything except the call
    python -m colosseum.house_league --once --backend api   # Anthropic API, not the CLI

Two generator backends:

  cli (default)  the Claude Code CLI on this box, headless (`claude -p`), on the
                 subscription login in ~/.claude. No API key, no dollar cost.
  api            the Anthropic SDK with ANTHROPIC_API_KEY. Kept for later.

What one night does:

 1. read the current leaderboard, matrix, balance read and replays
 2. pick a persona per role (colosseum/personas.py): exploiter, counter_meta, generalist
    or contrarian -- each defined by the evidence it is shown and the bot it must beat
 3. per bot: check the caps *before* spending anything, then one model call
 4. validate the returned file without executing it on the host
 5. write it into bots/house/ with a date-stamped name, plus a .meta.json sidecar that
    records persona, target, backend, model and tokens
 6. smoke-test each one **in the sandbox** -- house bots are untrusted from here on
 7. rerun the full tournament, sandboxed and parallel; record whether each new bot beat
    the target its persona was given
 8. retire any house bot that has finished bottom of its ladder three nights running

Caps are hard and checked before the call, not after: a night that would exceed the token
cap or the call cap (and, on the api backend, the dollar cap) aborts with a log line and
spends nothing. On the cli backend there is no dollar cost, so there is no dollar cap.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import personas
from .prompts import generator as prompt_text
from .rules import SEASON0
from .sim import run_match
from .tournament import DEFAULT_OUT, ROOT, run_tournament

HOUSE = ROOT / "bots" / "house"
SUBMITTED = ROOT / "bots" / "submitted"
RETIRED = HOUSE / "RETIRED"
LOG = DEFAULT_OUT / "house_league.log"
HISTORY = DEFAULT_OUT / "house_history.json"
RAW = DEFAULT_OUT / "house_raw"            # every model response, verbatim, for post-mortems
# One JSON line per real night (dry runs are not recorded): status, reason, tokens, bots
# written/rejected/retired, and wall time per phase. The weekly meta report reads this.
NIGHTS = DEFAULT_OUT / "nights.jsonl"
ALERT = DEFAULT_OUT / "ALERT.md"


class Phases:
    """Wall time per phase of a night: `with phases("tournament"): ...`."""

    def __init__(self):
        self.seconds = {}

    def __call__(self, name):
        phases = self

        class _Timer:
            def __enter__(self):
                self.t0 = time.monotonic()

            def __exit__(self, *exc):
                phases.seconds[name] = round(
                    phases.seconds.get(name, 0.0) + time.monotonic() - self.t0, 2)
        return _Timer()

# $ per million tokens, from the model table cached in the claude-api skill (2026-06-24).
# If Anthropic's prices move, this table is what needs updating -- the caps are enforced
# against it, so a stale table means the dollar cap is enforced against a stale price.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DEFAULT_MODEL = "claude-opus-5"
# The CLI takes an alias and resolves it itself; the resolved id is logged after the call.
DEFAULT_CLI_MODEL = "opus"
BACKENDS = ("cli", "api")
MAX_OUTPUT_TOKENS = 32000
CLI_TIMEOUT_S = 900


class CapExceeded(RuntimeError):
    pass


class BackendError(RuntimeError):
    """The generator backend failed: not logged in, not installed, timed out, bad output."""


@dataclass
class Caps:
    max_usd: float = 2.00
    max_tokens: int = 200_000
    max_calls: int = 4
    bots_per_night: int = 2
    model: str = ""                          # "" = the backend's default
    backend: str = "cli"

    def __post_init__(self):
        if not self.model:
            self.model = DEFAULT_CLI_MODEL if self.backend == "cli" else DEFAULT_MODEL

    @classmethod
    def from_env(cls, env=None, backend=None):
        env = os.environ if env is None else env
        backend = backend or env.get("HOUSE_LEAGUE_BACKEND", "cli")
        if backend not in BACKENDS:
            raise ValueError(f"HOUSE_LEAGUE_BACKEND must be one of {BACKENDS}, got {backend!r}")
        return cls(
            max_usd=float(env.get("HOUSE_LEAGUE_MAX_USD", 2.00)),
            max_tokens=int(env.get("HOUSE_LEAGUE_MAX_TOKENS", 200_000)),
            max_calls=int(env.get("HOUSE_LEAGUE_MAX_CALLS", 4)),
            bots_per_night=int(env.get("HOUSE_LEAGUE_BOTS", 2)),
            model=env.get("HOUSE_LEAGUE_MODEL", ""),
            backend=backend,
        )

    def describe(self):
        usd = "no $ cap (subscription)" if self.backend == "cli" else f"${self.max_usd:.2f}"
        return (f"backend={self.backend} model={self.model} caps={usd}/"
                f"{self.max_tokens:,} tokens/{self.max_calls} calls")


@dataclass
class Spend:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def add(self, model, in_tok, out_tok, priced=True):
        self.calls += 1
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        if priced:
            rate_in, rate_out = PRICES.get(model, PRICES[DEFAULT_MODEL])
            self.usd += (in_tok * rate_in + out_tok * rate_out) / 1_000_000

    @property
    def tokens(self):
        return self.input_tokens + self.output_tokens


def log(message: str, path: Path = None):
    path = path or LOG                       # looked up at call time, so tests can redirect it
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}"
    with open(path, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


# --- context -----------------------------------------------------------------

def gather_context(out: Path = DEFAULT_OUT, n_replays: int = 3) -> dict:
    """The leaderboard, the matrix, the balance read, and the most lopsided pairings."""
    leaderboard = json.loads((out / "leaderboard.json").read_text())
    matrix = json.loads((out / "matrix.json").read_text())["matrix"]
    balance = (out / "BALANCE.md").read_text()

    # "Lopsided" = the pairings furthest from an even 0.5 score, in both directions.
    pairs = [(a, d, s) for a, row in matrix.items() for d, s in row.items()]
    pairs.sort(key=lambda p: -abs(p[2] - 0.5))
    lopsided = pairs[:n_replays]

    samples = []
    for a, d, score in lopsided:
        replay = out / "replays" / f"{a}__{d}__s0.json"
        if not replay.exists():
            continue
        meta = json.loads(replay.read_text())["meta"]
        samples.append(dict(attacker=a, defender=d, mean_score_defender=score,
                            outcome=meta["outcome"], asset_hp=meta["asset_hp"],
                            ticks=meta["ticks"],
                            drones_launched=meta["drones_launched"],
                            drones_killed=meta["drones_killed"],
                            drones_impacted=meta["drones_impacted"],
                            interceptors_launched=meta["interceptors_launched"],
                            shots_fired=meta["shots_fired"],
                            cost_exchange_ratio=meta["cost_exchange_ratio"]))
    return dict(leaderboard=leaderboard, matrix=matrix, balance=balance,
                lopsided=samples, rules=SEASON0.as_dict())


LAST_EVIDENCE = {}          # the budget record of the last prompt built (goes in .meta.json)


def build_prompt(ctx: dict, role: str = "attacker", persona: str = "exploiter",
                 target: str = None, out: Path = DEFAULT_OUT, second_of_two=False) -> str:
    """One bot, one persona. All wording is in colosseum/prompts/generator.py."""
    target = target or personas.target_for(persona, role, ctx)
    text, info = personas.evidence_with_budget(persona, role, target, ctx, out)
    LAST_EVIDENCE.clear()
    LAST_EVIDENCE.update(info)
    return "\n".join([
        prompt_text.INTRO,
        text,
        prompt_text.RULES.substitute(rules=json.dumps(ctx["rules"], indent=2)),
        prompt_text.API,
        personas.task(persona, role, target, second_of_two),
    ])


# --- model call ---------------------------------------------------------------

CANNED_RESPONSE = '''```python
"""Canned dry-run attacker. Targets nothing; exists so --dry-run exercises the whole path."""
NAME = "dryrun_attacker"
ROLE = "attacker"


def act(obs):
    rules = obs["rules"]
    n = min(int(rules["attacker_launches_per_tick"]),
            int(obs["budget"] // rules["striker_cost"]))
    return {"launch": [{"type": "striker", "bearing": 30.0 * i} for i in range(n)],
            "steer": {}}
```

```python
"""Canned dry-run defender. Targets nothing; exists so --dry-run exercises the whole path."""
NAME = "dryrun_defender"
ROLE = "defender"


def act(obs):
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    engaged = {i["target"] for i in obs["interceptors"]}
    free = [t["id"] for t in tracks if t["id"] not in engaged]
    in_gun = [t for t in tracks if t["range"] <= obs["rules"]["gun_range"]]
    return {"intercept": free[:2], "retarget": {},
            "gun": in_gun[0]["id"] if in_gun else None}
```'''


# What `claude -p` sends on top of our prompt, plus retries inside one call. Worst observed:
# 2026-10-01/02, 15,999 input tokens for a 17,526-char prompt (a call that hit a safety
# check and retried internally); this module estimates that prompt at ~5,500 on its own.
CLI_INPUT_OVERHEAD = 12000


def estimate_input_tokens(prompt: str, backend: str = "api") -> int:
    """Deliberately crude and deliberately high: ~3.5 chars per token, rounded up.

    The estimate only guards the pre-call cap check, and over-estimating is the safe
    direction -- it aborts a night that might have squeaked under, rather than spending
    past a cap the founder set.
    """
    overhead = CLI_INPUT_OVERHEAD if backend == "cli" else 0
    return int(len(prompt) / 3.5) + 500 + overhead


def check_caps(caps: Caps, spend: Spend, prompt: str):
    """Raise before spending anything if this call could take the night over a cap."""
    if spend.calls + 1 > caps.max_calls:
        raise CapExceeded(f"call cap: {spend.calls + 1} > {caps.max_calls}")
    projected_in = estimate_input_tokens(prompt, caps.backend)
    projected_tokens = spend.tokens + projected_in + MAX_OUTPUT_TOKENS
    if projected_tokens > caps.max_tokens:
        raise CapExceeded(f"token cap: projected {projected_tokens:,} > "
                          f"{caps.max_tokens:,}")
    if caps.backend == "cli":
        return                               # subscription: no dollar cost to cap
    rate_in, rate_out = PRICES.get(caps.model, PRICES[DEFAULT_MODEL])
    projected_usd = spend.usd + (projected_in * rate_in
                                 + MAX_OUTPUT_TOKENS * rate_out) / 1_000_000
    if projected_usd > caps.max_usd:
        raise CapExceeded(f"dollar cap: projected ${projected_usd:.2f} > "
                          f"${caps.max_usd:.2f}")


SYSTEM_PROMPT = prompt_text.SYSTEM


def call_model(prompt: str, caps: Caps, spend: Spend, dry_run: bool) -> str:
    check_caps(caps, spend, prompt)          # always, even in dry run
    if dry_run:
        log("dry-run: skipping the model call, using the canned response")
        return CANNED_RESPONSE
    if caps.backend == "cli":
        return call_cli(prompt, caps, spend)
    return call_api(prompt, caps, spend)


def call_api(prompt: str, caps: Caps, spend: Spend) -> str:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise BackendError("the anthropic SDK is not installed (pip install anthropic)") from exc

    client = Anthropic()
    response = client.messages.create(
        model=caps.model,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    spend.add(caps.model, usage.input_tokens, usage.output_tokens)
    log(f"api call: model={caps.model} in={usage.input_tokens} out={usage.output_tokens} "
        f"night_total=${spend.usd:.4f} ({spend.tokens:,} tokens, {spend.calls} calls)")
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")


def find_claude(env=None) -> str:
    """The CLI binary. Cron's PATH is /usr/bin:/bin, so ~/.local/bin is checked explicitly."""
    env = os.environ if env is None else env
    if env.get("HOUSE_LEAGUE_CLAUDE_BIN"):
        return env["HOUSE_LEAGUE_CLAUDE_BIN"]
    home = env.get("HOME") or str(Path.home())
    path = os.pathsep.join([env.get("PATH", ""), f"{home}/.local/bin"])
    found = shutil.which("claude", path=path)
    if not found:
        raise BackendError(f"claude CLI not found on PATH or in {home}/.local/bin")
    return found


def cli_env(env=None) -> dict:
    """A minimal environment for the child: enough to find the login, nothing else.

    ANTHROPIC_API_KEY is deliberately dropped -- if it were passed through, the CLI would
    bill the key instead of using the subscription. So is everything from any parent
    Claude Code session (CLAUDECODE, session ids, sockets), so a night started from inside
    a session behaves the same as one started from cron.
    """
    env = os.environ if env is None else env
    home = env.get("HOME") or str(Path.home())
    return {
        "HOME": home,
        "PATH": os.pathsep.join([f"{home}/.local/bin", "/usr/local/bin", "/usr/bin", "/bin"]),
        "LANG": env.get("LANG", "C.UTF-8"),
        # Makes MAX_OUTPUT_TOKENS a real ceiling, so the pre-call token projection holds.
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(MAX_OUTPUT_TOKENS),
    }


def cli_command(binary: str, caps: Caps) -> list:
    """Headless, one turn, no tools, no settings, no MCP, no hooks, no plugins, no session file.

    `--bare` would be simpler but it refuses OAuth, i.e. the subscription login. Instead:
    no setting sources means no user settings, so no plugins and none of their hooks; and
    the child runs in an empty temp dir so no CLAUDE.md is discovered.
    """
    return [binary, "-p", "--output-format", "json", "--model", caps.model,
            "--tools", "", "--setting-sources", "", "--strict-mcp-config",
            "--disable-slash-commands", "--no-session-persistence",
            "--system-prompt", SYSTEM_PROMPT]


def run_cli(cmd: list, prompt: str, env: dict, timeout: float) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="house_league_") as cwd:
        return subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd,
                              env=env, timeout=timeout)


def parse_cli_result(stdout: str) -> dict:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BackendError(f"CLI did not return JSON: {stdout[:200]!r}") from exc
    if not isinstance(result, dict) or "result" not in result:
        raise BackendError(f"CLI JSON has no result field: {stdout[:200]!r}")
    return result


def cli_tokens(result: dict):
    """(input incl. cache reads/writes, output incl. thinking) from the CLI's usage block."""
    u = result.get("usage") or {}
    in_tok = sum(int(u.get(k) or 0) for k in
                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return in_tok, int(u.get("output_tokens") or 0)


def call_cli(prompt: str, caps: Caps, spend: Spend) -> str:
    binary = find_claude()
    timeout = float(os.environ.get("HOUSE_LEAGUE_CLI_TIMEOUT", CLI_TIMEOUT_S))
    try:
        proc = run_cli(cli_command(binary, caps), prompt, cli_env(), timeout)
    except FileNotFoundError as exc:
        raise BackendError(f"claude CLI not runnable: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendError(f"claude CLI timed out after {timeout:.0f}s") from exc

    result = None
    if proc.stdout.strip():
        try:
            result = parse_cli_result(proc.stdout)
        except BackendError:
            if proc.returncode == 0:
                raise
    if result is not None:
        # Count whatever was used even if the call then failed: it still came off the cap.
        in_tok, out_tok = cli_tokens(result)
        if in_tok or out_tok:
            spend.add(caps.model, in_tok, out_tok, priced=False)
    if proc.returncode != 0 or result is None or result.get("is_error"):
        detail = (result or {}).get("result") or proc.stderr.strip()[-300:] or "no output"
        raise BackendError(f"claude CLI failed (exit {proc.returncode}): {detail}")

    resolved = ",".join(result.get("modelUsage") or {}) or caps.model
    log(f"cli call: model={resolved} in={in_tok} out={out_tok} "
        f"secs={result.get('duration_ms', 0) / 1000:.1f} "
        f"night_total={spend.tokens:,} tokens, {spend.calls} calls "
        f"(notional list price ${result.get('total_cost_usd', 0):.4f}, not billed)")
    if spend.tokens > caps.max_tokens:
        log(f"WARNING: night used {spend.tokens:,} tokens, over the {caps.max_tokens:,} cap "
            f"the pre-call projection allowed")
    return result["result"]


# --- validation ---------------------------------------------------------------

# Tolerant of ```py / ```Python / trailing spaces after the fence and CRLF line endings.
BLOCK = re.compile(r"```[ \t]*(?:python3?|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)


def extract_bots(text: str):
    return [b.strip() for b in BLOCK.findall(text)]


def validate_bot(source: str, expected_role: str):
    """Check a generated bot WITHOUT executing it. Returns (ok, name, reason)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, "", f"syntax error: {exc}"

    names = {}
    has_act = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant):
                    names[t.id] = node.value.value
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "act":
            has_act = True

    if not has_act:
        return False, "", "no module-level act() function"
    if "NAME" not in names or not isinstance(names["NAME"], str):
        return False, "", "missing or non-string NAME"
    if names.get("ROLE") != expected_role:
        return False, names.get("NAME", ""), f"ROLE is {names.get('ROLE')!r}, expected {expected_role!r}"
    banned = {"subprocess", "socket", "shutil", "ctypes", "multiprocessing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in banned:
                    return False, names["NAME"], f"imports {a.name}"
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in banned:
            return False, names["NAME"], f"imports from {node.module}"
    return True, names["NAME"], ""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_")[:40] or "bot"


def smoke_test(path: Path, role: str) -> tuple:
    """One sandboxed match against a baseline. House bots never run in-process."""
    opponent = (ROOT / "bots" / "defenders" / "layered.py") if role == "attacker" else \
               (ROOT / "bots" / "attackers" / "rush.py")
    a, d = (path, opponent) if role == "attacker" else (opponent, path)
    try:
        meta = run_match(a, d, 0, record=False, sandbox=True)["meta"]
    except Exception as exc:
        return False, f"sandboxed match failed: {type(exc).__name__}: {exc}"
    errors = meta["attacker_errors" if role == "attacker" else "defender_errors"]
    if errors["policy_errors"] >= meta["ticks"]:
        return False, f"errored on every tick: {errors['last_error']}"
    return True, (f"ok ({meta['ticks']} ticks, {errors['policy_errors']} policy errors, "
                  f"outcome {meta['outcome']})")


# --- retirement ---------------------------------------------------------------

def load_history() -> dict:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text())
    return {"nights": []}


def save_history(history: dict):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(history, indent=2))


def retirable_file(name: str):
    """The .py of a house or submitted bot by name, or None (baselines never retire)."""
    for folder in (HOUSE, SUBMITTED / "attacker", SUBMITTED / "defender"):
        p = folder / f"{name}.py"
        if p.exists():
            return p
    return None


def record_night(history: dict, leaderboard: dict, when: str) -> dict:
    def bottom(role):
        # The bottom of the whole ladder, and only if that is a house or submitted bot.
        # Not "the lowest house bot": with one house bot at #1 that would count as a
        # bottom finish.
        rows = leaderboard[role]
        return rows[-1]["name"] if rows and retirable_file(rows[-1]["name"]) else None
    history["nights"].append(dict(date=when, attacker_bottom=bottom("attackers"),
                                  defender_bottom=bottom("defenders")))
    return history


def unique_coverage(name: str, role: str, breaches: dict):
    """Opponents that only `name` covers, among every bot in the last tournament.

    An attacker covers a defender if it destroyed the asset in at least one seed; a
    defender covers an attacker if it kept the asset in at least one seed. Same bar both
    ways: "can do it at all". breaches = the contents of out/breaches.json.
    """
    b, seeds = breaches["breaches"], breaches["seeds"]
    attackers = sorted(b)
    defenders = sorted({d for row in b.values() for d in row})
    if role == "attacker":
        covers = lambda a, d: b.get(a, {}).get(d, 0) > 0                     # noqa: E731
        return [d for d in defenders if covers(name, d)
                and not any(covers(a, d) for a in attackers if a != name)]
    stops = lambda d, a: b.get(a, {}).get(d, seeds) < seeds                  # noqa: E731
    return [a for a in attackers if stops(name, a)
            and not any(stops(d, a) for d in defenders if d != name)]


def apply_retirement(history: dict, nights: int = 3, breaches: dict = None) -> list:
    """Bottom of its ladder three nights running and a bot moves to RETIRED/ -- unless it
    is the only live bot that covers some opponent (see unique_coverage). The product is a
    library of tactics, and a mediocre bot that is the only answer to something stays."""
    recent = history["nights"][-nights:]
    if len(recent) < nights:
        return []
    retired = []
    for key, role in (("attacker_bottom", "attacker"), ("defender_bottom", "defender")):
        names = [n.get(key) for n in recent]
        if not (names[0] and all(n == names[0] for n in names)):
            continue
        src = retirable_file(names[0])
        if src is None:
            continue
        only = unique_coverage(names[0], role, breaches) if breaches else []
        if only:
            verb = "breaches" if role == "attacker" else "stops"
            log(f"exempt {names[0]} from retirement: bottom {nights} nights running, but "
                f"the only live bot that {verb} {', '.join(only)}")
            continue
        dest = src.parent / "RETIRED"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest / src.name))
        meta = src.with_suffix(".meta.json")
        if meta.exists():
            shutil.move(str(meta), str(dest / meta.name))
        retired.append(names[0])
        log(f"retired {names[0]}: bottom of its ladder {nights} nights running")
    return retired


# --- bot metadata -------------------------------------------------------------

SNAPSHOT_FILES = ("leaderboard.json", "matrix.json", "breaches.json")


def last_matrices(out: Path, n: int = 2):
    """The matrices of the last n real nights, oldest first, from out/history/."""
    days = sorted(p for p in (out / "history").glob("*") if (p / "matrix.json").exists())
    return [json.loads((d / "matrix.json").read_text())["matrix"] for d in days[-n:]]


def snapshot(out: Path, when: str):
    """Keep this night's ladder: out/history/<date>/. The meta report diffs these."""
    dest = out / "history" / when
    dest.mkdir(parents=True, exist_ok=True)
    for name in SNAPSHOT_FILES:
        if (out / name).exists():
            shutil.copy2(out / name, dest / name)


def rel(path: Path) -> str:
    """Repo-relative when inside the repo (readable in logs), absolute otherwise."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_meta(bot: Path, meta: dict):
    """Sidecar next to the bot. tournament.discover() only globs *.py, so it is inert."""
    bot.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def judge(stem: str, meta: dict, lb: dict, matrix: dict) -> dict:
    """Did the new bot beat what its persona told it to beat? Scores are its own side's."""
    role, target = meta["role"], meta["target"]
    if role == "attacker":
        mine = {d: round(1.0 - s, 3) for d, s in matrix[stem].items()}
    else:
        mine = {a: round(row[stem], 3) for a, row in matrix.items()}
    ladder = lb[role + "s"]
    rank = next(i for i, r in enumerate(ladder, 1) if r["name"] == stem)
    field_mean = round(sum(mine.values()) / len(mine), 3)
    if target == "field":
        others = [r["mean_score"] for r in ladder if r["name"] != stem]
        return dict(field_mean=field_mean, rank=rank,
                    beat_target=field_mean > max(others, default=0.0))
    return dict(score_vs_target=mine.get(target), field_mean=field_mean, rank=rank,
                beat_target=mine.get(target, 0.0) > 0.5)


# --- the night ----------------------------------------------------------------

def run_night(caps: Caps = None, dry_run: bool = False, out: Path = DEFAULT_OUT,
              seeds: int = 10) -> dict:
    """One night. Never raises: any failure becomes a logged status="error" summary, and
    every real night (not dry runs) is appended to the NIGHTS ledger."""
    phases = Phases()
    started = time.monotonic()
    try:
        summary = _run_night(caps, dry_run, out, seeds, phases)
    except Exception as exc:
        import traceback
        tail = traceback.format_exc().strip().splitlines()[-6:]
        log(f"ABORT: unexpected {type(exc).__name__}: {exc} | " + " / ".join(tail))
        summary = dict(status="error", reason=f"unexpected {type(exc).__name__}: {exc}",
                       spend={})
    summary["phases"] = phases.seconds
    summary.setdefault("seconds", round(time.monotonic() - started, 1))
    if not dry_run:
        record = dict(date=date.today().isoformat(),
                      finished=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      **{k: summary.get(k) for k in (
                          "status", "reason", "backend", "written", "rejected", "retired",
                          "spend", "phases", "seconds", "tournament_seconds", "cache",
                          "house_positions", "top_attacker", "top_defender")})
        NIGHTS.parent.mkdir(parents=True, exist_ok=True)
        with open(NIGHTS, "a") as f:
            f.write(json.dumps(record) + "\n")
        # out/ALERT.md: written by a failed night, removed by the next good one.
        from . import ops
        try:
            if summary.get("status") == "ok":
                ops.clear_alert(ALERT)
            else:
                ops.write_alert(summary.get("reason") or summary.get("status"), LOG, ALERT)
        except OSError as exc:
            log(f"could not update {ALERT.name}: {exc}")
    return summary


def _run_night(caps, dry_run, out, seeds, phases) -> dict:
    spend = Spend()
    when = date.today().isoformat()
    started = time.monotonic()
    try:
        caps = caps or Caps.from_env()
    except ValueError as exc:
        log(f"ABORT: bad configuration: {exc}")
        return dict(status="error", reason=str(exc), spend=vars(spend))
    log(f"night {when} starting: {caps.describe()} dry_run={dry_run}")

    ctx = gather_context(out)
    nights = len(load_history()["nights"])
    try:
        plan = personas.plan_night(ctx, nights, last_matrices(out, 2),
                                   os.environ.get("HOUSE_LEAGUE_PERSONAS", ""),
                                   slots=caps.bots_per_night)
    except (ValueError, KeyError) as exc:
        log(f"ABORT: persona setup failed: {type(exc).__name__}: {exc}")
        return dict(status="error", reason=str(exc), spend=vars(spend))
    log("plan: " + "; ".join(f"{r} {p} vs {t}" + (f" ({n})" if n else "")
                             for r, p, t, n in plan))
    written, rejected, metas = [], [], {}
    seen_targets = set()
    for role, persona, target, note in plan:
        second = (role, target) in seen_targets
        seen_targets.add((role, target))
        try:
            prompt = build_prompt(ctx, role, persona, target, out, second_of_two=second)
        except (ValueError, KeyError, OSError) as exc:
            log(f"ABORT: persona setup failed for {role}: {type(exc).__name__}: {exc}")
            if not written:
                return dict(status="error", reason=str(exc), spend=vars(spend))
            rejected.append((role, f"persona setup: {exc}"))
            break
        evidence_info = dict(LAST_EVIDENCE)
        log(f"{role}: persona={persona} target={target} prompt={len(prompt):,} chars "
            f"evidence {evidence_info.get('used')}/{evidence_info.get('budget')} tokens "
            f"{evidence_info.get('included')}")
        before = (spend.input_tokens, spend.output_tokens)
        try:
            with phases("generation"):
                text = call_model(prompt, caps, spend, dry_run)
        except CapExceeded as exc:
            log(f"ABORT before the {role} call -- {exc}")
            if not written:
                return dict(status="aborted", reason=str(exc), spend=vars(spend))
            rejected.append((role, f"cap: {exc}"))
            break
        except Exception as exc:
            # This runs unattended from cron: a logged-out CLI, a missing key or SDK, a
            # timeout must leave a log line and a non-zero exit, not a traceback nobody reads.
            log(f"ABORT: {type(exc).__name__}: {exc}")
            if not written:
                return dict(status="error", reason=f"{type(exc).__name__}: {exc}",
                            spend=vars(spend))
            rejected.append((role, f"{type(exc).__name__}: {exc}"))
            break

        raw_path = None
        if not dry_run:
            RAW.mkdir(parents=True, exist_ok=True)
            raw_path = RAW / (f"{datetime.now(timezone.utc):%Y-%m-%dT%H%M%S}_{caps.backend}"
                              f"_{role}_{persona}.md")
            raw_path.write_text(text)
            log(f"raw response saved to {rel(raw_path)} ({len(text):,} chars)")

        blocks = extract_bots(text)
        if dry_run:                          # the canned response holds both roles
            i = 0 if role == "attacker" else 1
            blocks = blocks[i:i + 1]
        if not blocks:
            log(f"rejected {role}: model returned no code block")
            rejected.append((role, "model returned no code block"))
            continue
        with phases("validation"):
            ok, name, reason = validate_bot(blocks[0], role)
        if not ok:
            log(f"rejected {role}: {reason}")
            rejected.append((role, reason))
            continue
        HOUSE.mkdir(parents=True, exist_ok=True)
        path = HOUSE / f"{when}_{role}_{slug(name)}.py"
        n = 2
        while path.exists():                 # two bots in one night may pick one NAME
            path = HOUSE / f"{when}_{role}_{slug(name)}_{n}.py"
            n += 1
        path.write_text(blocks[0] + "\n")
        with phases("smoke"):
            ok, detail = smoke_test(path, role)
        if not ok:
            log(f"rejected {path.name}: {detail}")
            path.unlink()
            rejected.append((role, detail))
            continue
        log(f"accepted {path.name}: {detail}")
        written.append(path.name)
        metas[path.stem] = dict(
            name=path.stem, role=role, date=when, persona=persona, target=target,
            escalation=note == "escalation", prompt_version=prompt_text.PROMPT_VERSION,
            evidence=evidence_info,
            backend=caps.backend, model=caps.model, dry_run=dry_run,
            tokens=dict(input=spend.input_tokens - before[0],
                        output=spend.output_tokens - before[1]),
            raw_response=rel(raw_path) if raw_path else None)
        write_meta(path, metas[path.stem])

    lb = None
    tournament_s = None
    cache_info = None
    if written:
        t0 = time.monotonic()
        with phases("tournament"):
            lb, _, results = run_tournament(seeds=seeds, out=out, sandbox=True, quiet=True)
        if not dry_run:
            snapshot(out, when)
        tournament_s = round(time.monotonic() - t0, 1)
        from .tournament import LAST_RUN
        cache_info = dict(LAST_RUN)
        log(f"tournament: {len(results)} matches in {tournament_s}s -- "
            f"{cache_info.get('ran')} played in the sandbox, {cache_info.get('cached')} "
            f"from the cache ({cache_info.get('cache_entries')} entries)")
        matrix = json.loads((out / "matrix.json").read_text())["matrix"]
        for stem, meta in metas.items():
            meta["result"] = judge(stem, meta, lb, matrix)
            write_meta(HOUSE / f"{stem}.py", meta)
            log(f"{stem} ({meta['persona']} vs {meta['target']}): "
                f"{json.dumps(meta['result'])}")
        if dry_run:
            retired = []                     # canned bots must not count toward retirement
        else:
            history = record_night(load_history(), lb, when)
            breaches_path = out / "breaches.json"
            breaches = (json.loads(breaches_path.read_text())
                        if breaches_path.exists() else None)
            retired = apply_retirement(history, breaches=breaches)
            save_history(history)
    else:
        log("no new bots survived validation; tournament not rerun")
        retired = []

    summary = dict(status="ok", date=when, written=written, rejected=rejected,
                   retired=retired, spend=vars(spend), backend=caps.backend,
                   tournament_seconds=tournament_s, cache=cache_info,
                   seconds=round(time.monotonic() - started, 1))
    if lb:
        summary["top_attacker"] = lb["attackers"][0]["name"]
        summary["top_defender"] = lb["defenders"][0]["name"]
        summary["house_positions"] = {
            r["name"]: dict(role=r["role"], elo=r["elo"], win_rate=r["win_rate"],
                            rank=lb[role].index(r) + 1, persona=metas[r["name"]]["persona"],
                            target=metas[r["name"]]["target"],
                            beat_target=metas[r["name"]].get("result", {}).get("beat_target"))
            for role in ("attackers", "defenders") for r in lb[role]
            if r["name"] in metas}
    log(f"night {when} done: {json.dumps(summary)}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="run one night now")
    ap.add_argument("--dry-run", action="store_true",
                    help="do everything except call the model")
    ap.add_argument("--backend", choices=BACKENDS, default=None,
                    help="generator backend (default: $HOUSE_LEAGUE_BACKEND or cli)")
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()
    if not args.once:
        ap.error("use --once to run a night (there is no daemon mode)")
    try:
        caps = Caps.from_env(backend=args.backend)
    except ValueError as exc:
        log(f"ABORT: bad configuration: {exc}")
        return 2
    summary = run_night(caps=caps, dry_run=args.dry_run, seeds=args.seeds)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
