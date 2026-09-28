"""Nightly house league: Claude writes two new bots, they fight, the junk gets retired.

    python -m colosseum.house_league --once          # one night, real API call
    python -m colosseum.house_league --once --dry-run  # everything except the API call

What one night does:

 1. read the current leaderboard, matrix, balance read and the most lopsided replays
 2. check the spend caps *before* spending anything
 3. ask Claude for one attacker and one defender that exploit a named weakness
 4. validate the returned files without executing them on the host
 5. write them into bots/house/ with a date-stamped name
 6. smoke-test each one **in the sandbox** -- house bots are untrusted from here on
 7. rerun the full tournament, sandboxed and parallel
 8. retire any house bot that has finished bottom of its ladder three nights running

Caps are hard and checked before the call, not after: a night that would exceed the token
cap, the dollar cap or the call cap aborts with a log line and spends nothing.
"""
import argparse
import ast
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .rules import SEASON0
from .sim import run_match
from .tournament import DEFAULT_OUT, ROOT, run_tournament

HOUSE = ROOT / "bots" / "house"
RETIRED = HOUSE / "RETIRED"
LOG = DEFAULT_OUT / "house_league.log"
HISTORY = DEFAULT_OUT / "house_history.json"

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
MAX_OUTPUT_TOKENS = 16000


class CapExceeded(RuntimeError):
    pass


@dataclass
class Caps:
    max_usd: float = 2.00
    max_tokens: int = 200_000
    max_calls: int = 4
    bots_per_night: int = 2
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        return cls(
            max_usd=float(env.get("HOUSE_LEAGUE_MAX_USD", 2.00)),
            max_tokens=int(env.get("HOUSE_LEAGUE_MAX_TOKENS", 200_000)),
            max_calls=int(env.get("HOUSE_LEAGUE_MAX_CALLS", 4)),
            bots_per_night=int(env.get("HOUSE_LEAGUE_BOTS", 2)),
            model=env.get("HOUSE_LEAGUE_MODEL", DEFAULT_MODEL),
        )


@dataclass
class Spend:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def add(self, model, in_tok, out_tok):
        rate_in, rate_out = PRICES.get(model, PRICES[DEFAULT_MODEL])
        self.calls += 1
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.usd += (in_tok * rate_in + out_tok * rate_out) / 1_000_000

    @property
    def tokens(self):
        return self.input_tokens + self.output_tokens


def log(message: str, path: Path = LOG):
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


def build_prompt(ctx: dict) -> str:
    lb = ctx["leaderboard"]
    atk = "\n".join(f"  {r['name']}: elo {r['elo']:.0f}, win rate {r['win_rate']:.0%}, "
                    f"mean CER {r['mean_cer']}" for r in lb["attackers"])
    dfn = "\n".join(f"  {r['name']}: elo {r['elo']:.0f}, win rate {r['win_rate']:.0%}, "
                    f"mean CER {r['mean_cer']}" for r in lb["defenders"])
    return f"""You are writing bots for Swarm Colosseum, an abstract strategy benchmark on a
blank 2D plane with made-up units. It is a game, not a model of anything real.

A protected asset sits at the origin. An attacker launches cheap drones from a ring; a
defender has a limited magazine of interceptors, a short-range gun, and a radar that sees
position but only reveals a drone's type inside a close range. Everything is made-up units.

## Current standings

Attackers:
{atk}

Defenders:
{dfn}

## Mean score_defender per pairing (high = defender did well)

{json.dumps(ctx['matrix'], indent=2)}

## The most lopsided pairings, with one match each

{json.dumps(ctx['lopsided'], indent=2)}

## Current rules

{json.dumps(ctx['rules'], indent=2)}

## The policy API

A bot is one Python file with module-level `NAME` (str), `ROLE` ("attacker" or
"defender"), `act(obs) -> dict`, and optionally `reset(seed)`. Standard library only.
It is loaded fresh for every match, so module state does not leak between matches.

Attacker obs: tick, budget, asset{{pos,hp,radius}}, drones[{{id,type,pos,vel,waypoint}}],
interceptors[[x,y]], rules.
Attacker action: {{"launch": [{{"type": "striker"|"decoy", "bearing": float}}],
                   "steer": {{drone_id: [x,y] or None}}}}
A drone flies to its waypoint if it has one, then heads for the asset.

Defender obs: tick, asset, tracks[{{id,pos,vel,range,cls}}] where cls is
"unknown"/"striker"/"decoy", interceptors[{{id,target,pos,age}}], stock, ammo, rules.
Defender action: {{"intercept": [track_id], "retarget": {{interceptor_id: track_id}},
                   "gun": track_id or None}}

Launch caps are per tick and enforced by the engine; exceeding them wastes the request.

## Your task

Write exactly TWO bots: one attacker and one defender. Each must exploit a weakness you can
name in the current standings above — the docstring must say which bot or which pairing it
is targeting and why the weakness exists.

Requirements:
- Standard library only. No file, network or subprocess access.
- Fast: `act` is called up to 600 times per match, with a per-tick timeout.
- Deterministic given the same observations. If you need randomness, seed it in `reset`.
- Do not raise. Return a well-formed action every tick.

Return exactly two fenced Python code blocks and nothing else — the attacker first, then
the defender. No commentary outside the blocks."""


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


def estimate_input_tokens(prompt: str) -> int:
    """Deliberately crude and deliberately high: ~3.5 chars per token, rounded up.

    The estimate only guards the pre-call cap check, and over-estimating is the safe
    direction -- it aborts a night that might have squeaked under, rather than spending
    past a cap the founder set.
    """
    return int(len(prompt) / 3.5) + 500


def check_caps(caps: Caps, spend: Spend, prompt: str):
    """Raise before spending anything if this call could take the night over a cap."""
    if spend.calls + 1 > caps.max_calls:
        raise CapExceeded(f"call cap: {spend.calls + 1} > {caps.max_calls}")
    projected_in = estimate_input_tokens(prompt)
    projected_tokens = spend.tokens + projected_in + MAX_OUTPUT_TOKENS
    if projected_tokens > caps.max_tokens:
        raise CapExceeded(f"token cap: projected {projected_tokens:,} > "
                          f"{caps.max_tokens:,}")
    rate_in, rate_out = PRICES.get(caps.model, PRICES[DEFAULT_MODEL])
    projected_usd = spend.usd + (projected_in * rate_in
                                 + MAX_OUTPUT_TOKENS * rate_out) / 1_000_000
    if projected_usd > caps.max_usd:
        raise CapExceeded(f"dollar cap: projected ${projected_usd:.2f} > "
                          f"${caps.max_usd:.2f}")


def call_model(prompt: str, caps: Caps, spend: Spend, dry_run: bool) -> str:
    check_caps(caps, spend, prompt)          # always, even in dry run
    if dry_run:
        log("dry-run: skipping the API call, using the canned response")
        return CANNED_RESPONSE
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError("the anthropic SDK is not installed (pip install anthropic)") from exc

    client = Anthropic()
    response = client.messages.create(
        model=caps.model,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    spend.add(caps.model, usage.input_tokens, usage.output_tokens)
    log(f"api call: model={caps.model} in={usage.input_tokens} out={usage.output_tokens} "
        f"night_total=${spend.usd:.4f} ({spend.tokens:,} tokens, {spend.calls} calls)")
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")


# --- validation ---------------------------------------------------------------

BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


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


def record_night(history: dict, leaderboard: dict, when: str) -> dict:
    house_names = {p.stem for p in HOUSE.glob("*.py")}
    def bottom(role):
        rows = [r for r in leaderboard[role] if r["name"] in house_names]
        return rows[-1]["name"] if rows else None
    history["nights"].append(dict(date=when, attacker_bottom=bottom("attackers"),
                                  defender_bottom=bottom("defenders")))
    return history


def apply_retirement(history: dict, nights: int = 3) -> list:
    """Bottom of its ladder three nights running and a house bot moves to RETIRED/."""
    recent = history["nights"][-nights:]
    if len(recent) < nights:
        return []
    retired = []
    for key in ("attacker_bottom", "defender_bottom"):
        names = [n.get(key) for n in recent]
        if names[0] and all(n == names[0] for n in names):
            src = HOUSE / f"{names[0]}.py"
            if src.exists():
                RETIRED.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(RETIRED / src.name))
                retired.append(names[0])
                log(f"retired {names[0]}: bottom of its ladder {nights} nights running")
    return retired


# --- the night ----------------------------------------------------------------

def run_night(caps: Caps = None, dry_run: bool = False, out: Path = DEFAULT_OUT,
              seeds: int = 10) -> dict:
    caps = caps or Caps.from_env()
    spend = Spend()
    when = date.today().isoformat()
    started = time.monotonic()
    log(f"night {when} starting: model={caps.model} caps=${caps.max_usd:.2f}/"
        f"{caps.max_tokens:,} tokens/{caps.max_calls} calls dry_run={dry_run}")

    ctx = gather_context(out)
    prompt = build_prompt(ctx)
    try:
        text = call_model(prompt, caps, spend, dry_run)
    except CapExceeded as exc:
        log(f"ABORT before any API call -- {exc}")
        return dict(status="aborted", reason=str(exc), spend=vars(spend))
    except Exception as exc:
        # This runs unattended from cron: a missing key or SDK must leave a log line and
        # a non-zero exit, not a traceback nobody reads.
        log(f"ABORT: {type(exc).__name__}: {exc}")
        return dict(status="error", reason=f"{type(exc).__name__}: {exc}",
                    spend=vars(spend))

    blocks = extract_bots(text)
    wanted = [("attacker", 0), ("defender", 1)][:max(1, caps.bots_per_night)]
    written, rejected = [], []
    for role, index in wanted:
        if index >= len(blocks):
            rejected.append((role, "model returned too few code blocks"))
            continue
        ok, name, reason = validate_bot(blocks[index], role)
        if not ok:
            log(f"rejected {role}: {reason}")
            rejected.append((role, reason))
            continue
        HOUSE.mkdir(parents=True, exist_ok=True)
        path = HOUSE / f"{when}_{role}_{slug(name)}.py"
        path.write_text(blocks[index] + "\n")
        ok, detail = smoke_test(path, role)
        if not ok:
            log(f"rejected {path.name}: {detail}")
            path.unlink()
            rejected.append((role, detail))
            continue
        log(f"accepted {path.name}: {detail}")
        written.append(path.name)

    lb = None
    if written:
        lb, _, results = run_tournament(seeds=seeds, out=out, sandbox=True, quiet=True)
        history = record_night(load_history(), lb, when)
        retired = apply_retirement(history)
        save_history(history)
    else:
        log("no new bots survived validation; tournament not rerun")
        retired = []

    summary = dict(status="ok", date=when, written=written, rejected=rejected,
                   retired=retired, spend=vars(spend),
                   seconds=round(time.monotonic() - started, 1))
    if lb:
        summary["top_attacker"] = lb["attackers"][0]["name"]
        summary["top_defender"] = lb["defenders"][0]["name"]
        summary["house_positions"] = {
            r["name"]: dict(role=r["role"], elo=r["elo"], win_rate=r["win_rate"])
            for role in ("attackers", "defenders") for r in lb[role]
            if r["name"] in {Path(w).stem for w in written}}
    log(f"night {when} done: {json.dumps(summary)}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="run one night now")
    ap.add_argument("--dry-run", action="store_true",
                    help="do everything except call the API")
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()
    if not args.once:
        ap.error("use --once to run a night (there is no daemon mode)")
    summary = run_night(dry_run=args.dry_run, seeds=args.seeds)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
