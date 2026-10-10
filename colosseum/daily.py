"""The build session (charter section 2, scoped by the founder 2026-10-03): unattended
`claude -p` every three hours, restricted to build-only items (BUILD_ITEMS).

    scripts/daily.sh            # what cron runs at 05:00 UTC; it calls run_day()

The wrapper, not the agent, owns branches and master:

  1. refuse to start if the allow-list's sha256 is not the approved one, if yesterday's
     session went over the token cap, or if another session holds the lock
  2. commit last night's new house bots on master (pathspec commit, league author)
  3. worktree /srv/swarm-daily on branch daily-wip: continue it (rebased on master) if it
     holds unmerged work from yesterday, otherwise start it fresh from master; refuse if
     a previous session left uncommitted changes (nothing is ever silently discarded)
  4. copy the live out/ data the tests read into the worktree
  5. run the session: --restricted (file tools confined to the worktree), dontAsk with
     the allow-list, no settings/MCP/plugins/hooks/slash commands/CLAUDE.md, 2 h wall clock;
     the full stream-json transcript goes to out/daily/<date>.jsonl
  6. merge only if: no WIP.md, nothing left uncommitted, rebased cleanly on master, and the
     full test suite is green -- then master is fast-forwarded. Otherwise the branch waits
     for tomorrow, and a failed session writes out/ALERT.md
  7. publish the session's DAILY.md on master either way, and record tokens/time

The token cap is enforced after the fact: claude -p has no token limit for an agentic
session, so a session that used more than TOKEN_CAP blocks the next day's from starting.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .tournament import ROOT

WORKTREE = Path("/srv/swarm-daily")
BRANCH = "daily-wip"
TOKEN_CAP = 200_000
# Backstop enforced by the CLI during the session, on its notional list price. Not money:
# the subscription isn't billed per call. It stops a runaway session before the 2 h clock.
RUNAWAY_USD = 5
WALL_CLOCK_S = 2 * 3600
ALLOWLIST = "scripts/daily_allowlist.txt"
ALLOWLIST_SHA = "scripts/daily_allowlist.sha256"
LEAGUE_AUTHOR = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]
OUT_COPY = ("leaderboard.json", "matrix.json", "BALANCE.md", "breaches.json", "nights.jsonl",
            "WATCH.md", "watch.jsonl", "house_history.json", "replays", "history", "cache",
            "meta")


# Launch sprint (founder, 2026-10-04): unattended sessions take the mechanical sprint items.
# Post-launch (founder, 2026-10-10), in BACKLOG.md order: P5 the persona-ablation write-up,
# W the weekly founder report, then SPEC-3 3.13 and 3.14. Human-gated and never a build
# item: 3.8, G, and switching fold-back on. The season boundary (P4) is a scripted step,
# not a session item, because it needs a branch merge the session may not make.
BUILD_ITEMS = ("P5", "W", "3.13", "3.14", "hygiene")
# Since launch every merge to master is public the next night, so a session may not touch
# what publishes, audits, sandboxes or admits code; the wrapper refuses to merge a branch
# that does (finish(), "protected").
PROTECTED = ("scripts/publish.sh", "scripts/rewrite_identity.sh", "scripts/audit_secrets.py",
             "scripts/public_identity", "scripts/daily_allowlist.txt",
             "scripts/daily_allowlist.sha256", "colosseum/daily.py", "colosseum/foldback.py",
             "colosseum/ops.py", "colosseum/sandbox.py", "colosseum/sandbox_runner.py",
             "colosseum/submit.py", "colosseum/submit_pr.py", "colosseum/policy.py",
             "colosseum/rules.py", "colosseum/sim.py", ".github/", "CHARTER.md")
SESSION_ITEM = "SESSION_ITEM"             # one line, written by the session before it starts
NO_PROGRESS_LIMIT = 2                     # consecutive non-merged sessions -> item frozen


def frozen_items(out: Path):
    """Items whose last NO_PROGRESS_LIMIT sessions all ended without a merge."""
    path = out / "daily" / "sessions.jsonl"
    if not path.exists():
        return []
    by_item = {}
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item in (rec.get("item") or "").split(","):
            if item:
                by_item.setdefault(item, []).append(rec.get("status"))
    return sorted(i for i, sts in by_item.items()
                  if len(sts) >= NO_PROGRESS_LIMIT
                  and all(st != "merged" for st in sts[-NO_PROGRESS_LIMIT:]))


class Refused(RuntimeError):
    pass


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=check)


def _dirty(wt: Path):
    return [l[3:] for l in git(wt, "status", "--porcelain").stdout.splitlines()
            if not l[3:].startswith("out/") and l[3:] != SESSION_ITEM]


# --- 1. preconditions ---------------------------------------------------------------

def allowed_tools(root: Path = ROOT):
    lines = (root / ALLOWLIST).read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def check_allowlist(root: Path = ROOT):
    actual = hashlib.sha256((root / ALLOWLIST).read_bytes()).hexdigest()
    approved = (root / ALLOWLIST_SHA).read_text().split()[0]
    if actual != approved:
        raise Refused(f"{ALLOWLIST} changed since it was approved (sha256 {actual[:12]} != "
                      f"{approved[:12]}); a founder must review it and update "
                      f"{ALLOWLIST_SHA}")


def check_last_session(out: Path):
    last = out / "daily" / "last.json"
    if last.exists():
        rec = json.loads(last.read_text())
        if (rec.get("tokens") or 0) > TOKEN_CAP:
            raise Refused(f"the last daily session ({rec.get('date')}) used "
                          f"{rec['tokens']:,} tokens, over the {TOKEN_CAP:,} cap; a founder "
                          "must clear out/daily/last.json to resume")


# --- 2-4. master, worktree, data -----------------------------------------------------

def commit_new_house_bots(root: Path):
    new = [l[3:] for l in git(root, "status", "--porcelain", "--untracked-files=all",
                              "--", "bots/house").stdout.splitlines() if l.startswith("??")]
    if not new:
        return []
    git(root, "add", "--", *new)
    git(root, *LEAGUE_AUTHOR, "commit", "-q", "-m",
        f"House bots from the night of {date.today().isoformat()}", "--", *new)
    return new


def prepare_worktree(root: Path, wt: Path, branch: str = BRANCH):
    """Returns 'continued' or 'fresh'. Raises Refused rather than discard anything."""
    exists = git(root, "rev-parse", "--verify", "--quiet", branch, check=False).returncode == 0
    if not wt.exists():
        if exists:
            git(root, "worktree", "add", "-q", str(wt), branch)
        else:
            git(root, "worktree", "add", "-q", str(wt), "-b", branch, "master")
            return "fresh"
    leftovers = _dirty(wt)
    if leftovers:
        raise Refused(f"{wt} has uncommitted changes from a previous session "
                      f"({leftovers[:5]}); review them before the next session runs")
    ahead = int(git(root, "rev-list", "--count", f"master..{branch}").stdout.strip() or 0)
    if ahead == 0:
        git(wt, "reset", "-q", "--hard", "master")       # clean, nothing unmerged
        return "fresh"
    rebase(wt)
    return "continued"


def rebase(wt: Path):
    """Rebase the branch on master. The only file master and the branch both change is
    DAILY.md (the wrapper publishes it to master every day); a conflict there takes
    master's copy. Any other conflict aborts and refuses."""
    r = git(wt, "rebase", "master", check=False)
    while r.returncode != 0:
        conflicted = git(wt, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if not conflicted or set(conflicted) - {"DAILY.md"}:
            git(wt, "rebase", "--abort", check=False)
            raise Refused(f"rebasing {BRANCH} on master conflicts in {conflicted}")
        git(wt, "checkout", "--ours", "--", "DAILY.md")
        git(wt, "add", "DAILY.md")
        r = subprocess.run(["git", "-C", str(wt), "-c", "core.editor=true", "rebase",
                            "--continue"], capture_output=True, text=True)


def copy_out(src: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for name in OUT_COPY:
        s, d = src / name, dest / name
        if not s.exists():
            continue
        if d.exists():
            shutil.rmtree(d) if d.is_dir() else d.unlink()
        shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)


# --- 5. the session --------------------------------------------------------------------

def build_prompt(root: Path, wt: Path, out: Path, frozen=()) -> str:
    def text(p):
        return p.read_text() if p.exists() else "(none)"
    log = out / "house_league.log"
    tail = "\n".join(log.read_text().splitlines()[-40:]) if log.exists() else "(no log)"
    recent = git(root, "log", "--oneline", "-15").stdout
    return f"""You are the daily engineering session for Swarm Colosseum. Follow the charter
below exactly. Today is {date.today().isoformat()}.

Where you are: a git worktree at {wt} on branch {BRANCH}. Work only here. Commit your work
on this branch with clear messages, and no Co-Authored-By or other attribution trailers
(the founder asked for none). Do not create, switch or merge branches; the wrapper
that started you merges this branch into master after you exit, and only if the full test
suite is green and there is no WIP.md. If you cannot finish an item, write WIP.md at the
worktree root describing the exact state and commit it; tomorrow's session continues
from it. Untrusted bots never run on the host (tests included). The live league data is
copied into out/ for you; it is a snapshot, not the live directory.

SCOPE (post-launch, founder 2026-10-10). You may work ONLY on: {", ".join(BUILD_ITEMS)}
("hygiene" = charter section 4, including writing up a stuck item), in BACKLOG.md order,
each only once its gate in BACKLOG.md has passed. Item G and item 3.8 are human-gated:
never touch them, and never switch fold-back on. The site and repo are public: everything
you merge is published the next night. The wrapper refuses to merge any change to these
files: {", ".join(PROTECTED)}. If an item needs one, write it up instead. Before
anything else, use the Write tool (not the shell) to write the id of the item you are taking
(one of {", ".join(BUILD_ITEMS)}) as the first line of a file named {SESSION_ITEM} at the
worktree root. If you finish it with time left, take the next unblocked in-scope item and
add its id as a new line before starting it. The wrapper refuses to merge anything else.
LAUNCH_STATUS.md is the founder's dashboard: update your items' lines (one phone screen).

How to run commands. Your shell already starts in the worktree root: never use `cd`,
`git -C`, redirection (`>`), pipes into other commands, or `&&` chains. Use the file tools
(Read, Write, Edit, Glob, Grep) for files. Only these shell command forms are allowed; any
other form is refused, which does not mean the shell is unavailable:
{chr(10).join("  " + t for t in allowed_tools(root) if t.startswith("Bash("))}
Frozen items (two sessions in a row without a merge; do not work on them, write them up
under hygiene instead): {", ".join(frozen) or "none"}.

Order: 1) if ALERT.md below shows a failure in the night or in a previous session, write it
up and fix it if it falls within scope;
2) otherwise take the next unblocked in-scope item in BACKLOG.md; 3) run python3 -m pytest tests -q;
4) append to PROGRESS.md; 5) rewrite DAILY.md (one phone screen: date, night status, what
was done, what is next, open stops); 6) commit everything and exit. Before you exit,
`git status` must show nothing to commit, and no document may contain a placeholder for a
result you haven't got: report only what a command you ran printed. Anything left
uncommitted blocks the merge.

Stop conditions in charter section 1 apply: write them up in DAILY.md and PROGRESS.md and
do not work around them.

===== CHARTER.md =====
{text(root / "CHARTER.md")}
===== BACKLOG.md =====
{text(wt / "BACKLOG.md")}
===== DAILY.md (yesterday) =====
{text(root / "DAILY.md")}
===== WIP.md =====
{text(wt / "WIP.md")}
===== out/ALERT.md =====
{text(out / "ALERT.md")}
===== last 40 lines of the league log =====
{tail}
===== recent commits on master =====
{recent}"""


def session_command(binary: str, root: Path = ROOT):
    return [binary, "-p", "--output-format", "stream-json", "--verbose", "--model", "opus",
            "--restricted", "--tools", "Read,Edit,Write,Glob,Grep,Bash",
            "--allowedTools", ",".join(allowed_tools(root)),
            "--permission-mode", "dontAsk", "--setting-sources", "",
            "--max-budget-usd", str(RUNAWAY_USD),
            "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"]


def run_session(cmd, prompt, wt: Path, transcript: Path, env: dict, timeout=WALL_CLOCK_S):
    transcript.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with open(transcript, "w") as f:
        try:
            proc = subprocess.run(cmd, input=prompt, stdout=f, stderr=subprocess.STDOUT,
                                  text=True, cwd=wt, env=env, timeout=timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    tokens = reads = 0
    for line in transcript.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            u = ev.get("usage") or {}
            tokens = sum(int(u.get(k) or 0) for k in (
                "input_tokens", "cache_creation_input_tokens", "output_tokens"))
            reads = int(u.get("cache_read_input_tokens") or 0)
    # The cap counts new input, cache writes and output -- what the league's single calls
    # consist of. An agentic session re-reads its own context every turn; those cache
    # reads are recorded (tokens_incl_cache_reads) but not counted against the cap.
    return dict(exit=code, tokens=tokens, tokens_incl_cache_reads=tokens + reads,
                seconds=round(time.monotonic() - t0))


# --- 6-7. merge, publish, record --------------------------------------------------------

def session_items(wt: Path):
    """The items a session declared, in order (one per line)."""
    p = wt / SESSION_ITEM
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text().splitlines() if l.strip()]


def session_item(wt: Path):
    items = session_items(wt)
    return ",".join(items) if items else None


def finish(root: Path, wt: Path, test_cmd: str, frozen=()):
    """Returns (status, detail). status in merged / nothing / wip / dirty / red / conflict /
    out-of-scope / protected."""
    items = session_items(wt)
    bad = [i for i in items if i not in BUILD_ITEMS]
    if not items or bad:
        return "out-of-scope", (f"{SESSION_ITEM} lists {items!r}; allowed: {BUILD_ITEMS}")
    stuck = [i for i in items if i in frozen]
    if stuck:
        return "out-of-scope", f"item(s) {stuck} are frozen (no mergeable progress twice running)"
    if (wt / "WIP.md").exists():
        return "wip", "WIP.md present; continuing tomorrow"
    dirty = _dirty(wt)
    if dirty:
        return "dirty", f"uncommitted changes left: {dirty[:5]}"
    ahead = int(git(root, "rev-list", "--count", f"master..{BRANCH}").stdout.strip() or 0)
    if ahead == 0:
        return "nothing", "no commits"
    touched = git(root, "diff", "--name-only", f"master...{BRANCH}").stdout.split()
    hit = sorted(p for p in touched if any(p == x or (x.endswith("/") and p.startswith(x))
                                           for x in PROTECTED))
    if hit:
        return "protected", f"touches {hit[:5]}: protected since launch; not merged"
    try:
        rebase(wt)                           # master may have moved during the session
    except Refused as exc:
        return "conflict", str(exc)
    tests = subprocess.run(test_cmd, shell=True, cwd=wt, capture_output=True, text=True)
    if tests.returncode != 0:
        last = (tests.stdout + tests.stderr).strip().splitlines()
        return "red", last[-1] if last else "tests failed"
    git(root, "merge", "-q", "--ff-only", BRANCH)
    return "merged", f"{ahead} commit(s) fast-forwarded onto master"


def publish_daily(root: Path, wt: Path):
    src = wt / "DAILY.md"
    if not src.exists():
        return False
    if (root / "DAILY.md").exists() and (root / "DAILY.md").read_bytes() == src.read_bytes():
        return False
    shutil.copy2(src, root / "DAILY.md")
    git(root, "add", "--", "DAILY.md")
    git(root, *LEAGUE_AUTHOR, "commit", "-q", "-m",
        f"DAILY.md for {date.today().isoformat()}", "--", "DAILY.md")
    return True


def run_day(root: Path = ROOT, wt: Path = WORKTREE, out: Path = None, binary: str = None,
            test_cmd: str = "python3 -m pytest tests -q", env: dict = None,
            timeout: int = WALL_CLOCK_S):
    out = out or root / "out"
    record = dict(date=date.today().isoformat(),
                  started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    lock = out / "daily" / "lock"
    try:
        check_allowlist(root)
        check_last_session(out)
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            raise Refused(f"another daily session holds {lock}")
    except Refused as exc:
        record.update(status="refused", detail=str(exc))
        _write_record(out, record, alert=True)
        return record
    try:
        record["house_bots_committed"] = commit_new_house_bots(root)
        record["branch"] = prepare_worktree(root, wt)
        copy_out(out, wt / "out")
        if binary is None:
            from .house_league import find_claude
            binary = find_claude()
        if env is None:
            from .house_league import cli_env
            env = cli_env()
        frozen = frozen_items(out)
        record["frozen"] = frozen
        if (wt / SESSION_ITEM).exists():
            (wt / SESSION_ITEM).unlink()           # each session declares its own
        prompt = build_prompt(root, wt, out, frozen)
        transcript = out / "daily" / f"{record['date']}.jsonl"
        record.update(run_session(session_command(binary, root), prompt, wt, transcript,
                                  env, timeout))
        status, detail = finish(root, wt, test_cmd, frozen)
        record.update(status=status, detail=detail, item=session_item(wt),
                      daily_published=publish_daily(root, wt))
        _write_record(out, record, alert=status in ("red", "conflict", "dirty",
                                                    "out-of-scope", "protected")
                      or record.get("exit") != 0)
    except Refused as exc:
        record.update(status="refused", detail=str(exc))
        _write_record(out, record, alert=True)
    finally:
        if lock.exists():
            lock.unlink()
    return record


def _write_record(out: Path, record: dict, alert: bool):
    d = out / "daily"
    d.mkdir(parents=True, exist_ok=True)
    (d / "last.json").write_text(json.dumps(record, indent=2) + "\n")
    with open(d / "sessions.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    if alert:
        from . import ops
        ops.write_alert(f"daily session {record.get('date')}: {record.get('status')} -- "
                        f"{record.get('detail') or record.get('exit')}",
                        alert=out / "ALERT.md", log=out / "house_league.log")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="only check the allow-list and the token record, then exit")
    args = ap.parse_args()
    if args.check:
        try:
            check_allowlist()
            check_last_session(ROOT / "out")
        except Refused as exc:
            print(f"REFUSED: {exc}")
            return 1
        print("ok: allow-list approved, last session under the cap")
        return 0
    rec = run_day()
    print(json.dumps(rec, indent=2))
    return 0 if rec.get("status") in ("merged", "nothing", "wip") else 1


if __name__ == "__main__":
    sys.exit(main())
