"""The autonomous loop (founder, 2026-10-16): a fresh `claude -p` every three hours.

    scripts/daily.sh            # what cron runs; it calls run_day()

Each session gets only the founder's PROMPT (no transcript, no item list), loads the
repo's CLAUDE.md and .claude/ (the four agents, the hooks, the slash commands, the Ralph
loop plugin) and nothing from the user's settings, runs architect -> builder -> test runner
-> reviewer, and exits. The wrapper, not the agent, owns branches and master:

  1. refuse to start if the allow-list's sha256 is not the approved one, if the last
     session went over the token cap, or if another session holds the lock
  2. commit last night's new house bots on master (pathspec commit, league author)
  3. worktree /srv/swarm-daily on branch daily-wip: continue it (rebased on master) if it
     holds unmerged work, otherwise start it fresh from master; refuse if a previous
     session left uncommitted changes (nothing is ever silently discarded)
  4. copy the live out/ data the tests read into the worktree, and write .loop/context.md
     (git log, health, last night, the live site's home page, FOUNDER_TODO, decisions)
     for the read-only architect
  5. run the session: --restricted (file tools confined to the worktree), dontAsk with
     the allow-list, project settings only, no MCP servers, 2 h wall clock; the full
     stream-json transcript goes to out/daily/<date>T<hour>.jsonl
  6. merge only if: the reviewer's verdict in the transcript is PASS, nothing is left
     uncommitted, no protected file is touched, CLAUDE.md changed only by added Lessons
     lines, it rebased cleanly on master, and the full test suite is green -- then master
     is fast-forwarded. Otherwise the branch waits, and a failed session writes ALERT.md
  7. write DAILY.md on master from the session's record, and record tokens and time

The token cap is enforced after the fact: claude -p has no token limit for an agentic
session, so a session that used more than TOKEN_CAP blocks the next one from starting.
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
            "meta",
            "ablation_14/done")     # P5's gate: only the marker, not the ablation's evidence


# The session's only input (founder, 2026-10-16), verbatim. It runs inside the Ralph loop
# plugin (/ralph-loop), capped at RALPH_ITERATIONS, as the in-session runner.
PROMPT = ("Read CLAUDE.md. Look at the repository, the git log, the live site and last "
          "night\u2019s league log as if for the first time. Do the single most valuable thing "
          "for the goal, or nothing. Commit. Exit without asking anything.")
RALPH_ITERATIONS = 2
RALPH_PROMISE = "SESSION DONE"
# Since launch every merge to master is public the next night, so a session may not touch
# what publishes, audits, sandboxes or admits code; the wrapper refuses to merge a branch
# that does (finish(), "protected").
PROTECTED = ("scripts/publish.sh", "scripts/rewrite_identity.sh", "scripts/audit_secrets.py",
             "scripts/public_identity", "scripts/daily_allowlist.txt",
             "scripts/daily_allowlist.sha256", "colosseum/daily.py", "colosseum/foldback.py",
             "colosseum/ops.py", "colosseum/sandbox.py", "colosseum/sandbox_runner.py",
             "colosseum/submit.py", "colosseum/submit_pr.py", "colosseum/policy.py",
             "colosseum/rules.py", "colosseum/sim.py", "colosseum/season.py",
             "colosseum/boundary.py", "colosseum/tournament.py", "scripts/nightly.sh",
             "SEASON.md", ".github/", "CHARTER.md",
             # the loop's own setup: agents, hooks, settings, plugin, schedule
             ".claude/", "scripts/daily.sh", "scripts/cron_install.sh", "scripts/crontab.txt",
             "scripts/fmt.py", "scripts/stop_check.sh", "scripts/public_private_since",
             "DAILY.md")              # the wrapper writes it, on master, from the record
# CLAUDE.md is the one file the loop may grow: by lines added to its Lessons section only.
LESSONS = "## Lessons"


class Refused(RuntimeError):
    pass


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=check)


def _dirty(wt: Path):
    return [l[3:] for l in git(wt, "status", "--porcelain").stdout.splitlines()
            if not l[3:].startswith(("out/", ".loop/", ".claude/ralph-loop"))]


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
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)


# --- 5. the session --------------------------------------------------------------------

def session_command(binary: str, root: Path = ROOT, wt: Path = None):
    """Fresh and headless: a new session that carries nothing over. --restricted confines
    the file tools to the worktree and ignores every settings file, so the project's setup
    is passed explicitly, from the worktree: .claude/settings.json (hooks, permissions),
    the four agents (.loop/agents.json, from .claude/agents/), the vendored Ralph loop
    plugin and the project's commands as a plugin (.loop/plugin). Nothing from the user's
    settings, so no other plugin or hook; no MCP servers; the allow-list under dontAsk.
    The session's own transcript is kept (the Ralph loop's Stop hook reads it)."""
    wt = wt or WORKTREE
    return [binary, "-p", "--output-format", "stream-json", "--verbose", "--model", "opus",
            "--restricted", "--tools", "Read,Edit,Write,Glob,Grep,Bash,Agent",
            "--allowedTools", ",".join(allowed_tools(root)),
            "--permission-mode", "dontAsk",
            "--settings", str(wt / ".claude" / "settings.json"),
            "--agents", str(wt / ".loop" / "agents.json"),
            "--plugin-dir", str(wt / ".claude" / "plugins" / "ralph-loop"),
            "--plugin-dir", str(wt / ".loop" / "plugin"),
            "--max-budget-usd", str(RUNAWAY_USD), "--strict-mcp-config"]


def write_setup(wt: Path):
    """What --restricted won't read from .claude/ itself: the agents as --agents JSON, and
    the commands as a plugin folder. Both generated from the worktree's .claude/ each time."""
    import re as _re
    agents = {}
    for p in sorted((wt / ".claude" / "agents").glob("*.md")):
        m = _re.match(r"---\n(.*?)\n---\n(.*)", p.read_text(), _re.S)
        if not m:
            continue
        fm = {k.strip(): v.strip() for k, v in
              (l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)}
        agents[fm["name"]] = {"description": fm["description"], "prompt": m.group(2).strip(),
                              "tools": [t.strip() for t in fm["tools"].split(",")]}
    loop = wt / ".loop"
    loop.mkdir(exist_ok=True)
    (loop / "agents.json").write_text(json.dumps(agents, indent=1))
    plugin = loop / "plugin"
    if plugin.exists():
        shutil.rmtree(plugin)
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "loop-commands", "version": "1.0.0",
         "description": "Swarm Colosseum's repo commands (.claude/commands)"}))
    if (wt / ".claude" / "commands").is_dir():
        shutil.copytree(wt / ".claude" / "commands", plugin / "commands")
    return sorted(agents)


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

def _report(text: str) -> str:
    """A subagent's own report, without the harness's hand-back preamble (which ends with
    "The report follows:") and without the indentation the harness adds."""
    if "The report follows:" in text:
        text = text.split("The report follows:", 1)[1]
    return "\n".join(l.strip() for l in text.strip().splitlines())


def reviewer_verdict(transcript: Path):
    """The last reviewer subagent's verdict in a stream-json transcript: "PASS", "BLOCK"
    or None (never ran). Read from the Agent tool's result, not from anything the session
    writes, so a session cannot pass itself."""
    calls, verdict = {}, None
    if not transcript.exists():
        return None
    for line in transcript.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        for block in ((msg.get("content") if isinstance(msg, dict) else None) or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                calls[block.get("id")] = (block.get("input") or {}).get("subagent_type")
            elif block.get("type") == "tool_result" and calls.get(block.get("tool_use_id")) == "reviewer":
                content = block.get("content")
                text = content if isinstance(content, str) else " ".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
                report = _report(text)
                first = report.splitlines()[0] if report else ""
                verdict = "PASS" if first.startswith("PASS") else "BLOCK"
    return verdict


def architect_signal(transcript: Path):
    """The architect's SIGNAL line, for the record and DAILY.md: the first one that names a
    number (a later Ralph pass that finds nothing more to do says "none")."""
    calls, signal = {}, None
    if not transcript.exists():
        return None
    for line in transcript.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        for block in ((msg.get("content") if isinstance(msg, dict) else None) or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                calls[block.get("id")] = (block.get("input") or {}).get("subagent_type")
            elif block.get("type") == "tool_result" and calls.get(block.get("tool_use_id")) == "architect":
                content = block.get("content")
                text = content if isinstance(content, str) else " ".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
                for l in _report(text).splitlines():
                    if l.startswith("SIGNAL:"):
                        found = l[7:].strip()
                        if signal is None or (signal == "none" and found != "none"):
                            signal = found
    return signal


def claude_md_ok(root: Path, branch: str = BRANCH):
    """CLAUDE.md may change only by lines added inside its Lessons section."""
    old = git(root, "show", f"master:CLAUDE.md", check=False).stdout
    new = git(root, "show", f"{branch}:CLAUDE.md", check=False).stdout
    if old == new:
        return True
    if LESSONS not in old or LESSONS not in new:
        return False
    head_old, tail_old = old.split(LESSONS, 1)
    head_new, tail_new = new.split(LESSONS, 1)
    if head_old != head_new:
        return False
    old_lines = [l for l in tail_old.splitlines() if l.strip()]
    new_lines = [l for l in tail_new.splitlines() if l.strip()]
    it = iter(new_lines)
    return all(any(l == m for m in it) for l in old_lines)      # nothing removed or changed


def finish(root: Path, wt: Path, test_cmd: str, transcript: Path = None):
    """Returns (status, detail). status in merged / nothing / trailer / unreviewed / blocked /
    wip / dirty / protected / claude-md / red / conflict."""
    if (wt / "WIP.md").exists():
        return "wip", "WIP.md present; continuing next session"
    dirty = _dirty(wt)
    if dirty:
        return "dirty", f"uncommitted changes left: {dirty[:5]}"
    ahead = int(git(root, "rev-list", "--count", f"master..{BRANCH}").stdout.strip() or 0)
    if ahead == 0:
        return "nothing", "no commits"
    bodies = git(root, "log", "--format=%B", f"master..{BRANCH}").stdout
    if "co-authored-by" in bodies.lower():
        return "trailer", "a commit carries a Co-Authored-By trailer (none allowed); not merged"
    verdict = reviewer_verdict(transcript) if transcript else None
    if verdict is None:
        return "unreviewed", "commits but no reviewer verdict in the transcript; not merged"
    if verdict != "PASS":
        return "blocked", "the reviewer blocked the change; not merged"
    touched = git(root, "diff", "--name-only", f"master...{BRANCH}").stdout.split()
    hit = sorted(p for p in touched if any(p == x or (x.endswith("/") and p.startswith(x))
                                           for x in PROTECTED))
    if hit:
        return "protected", f"touches {hit[:5]}: protected; not merged"
    if "CLAUDE.md" in touched and not claude_md_ok(root):
        return "claude-md", "CLAUDE.md changed outside added Lessons lines; not merged"
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


def write_daily(root: Path, record: dict):
    """DAILY.md on master, one phone screen, from the session's record (the wrapper writes
    it, so it says only what happened)."""
    lines = [f"# Loop session {record.get('started', '')[:16].replace('T', ' ')} UTC", "",
             f"**Status:** {record.get('status')} — {record.get('detail') or ''}",
             f"**Signal:** {record.get('signal') or 'none'}",
             f"**Reviewer:** {record.get('verdict') or 'did not run'}",
             f"**Tokens:** {record.get('tokens', 0):,} (cap {TOKEN_CAP:,}); "
             f"**time:** {record.get('seconds', 0)} s; exit {record.get('exit')}"]
    if record.get("merged_commits"):
        lines += ["", "**Merged:**"] + [f"- {c}" for c in record["merged_commits"]]
    lines += ["", "Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl."]
    text = "\n".join(lines) + "\n"
    path = root / "DAILY.md"
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    git(root, "add", "--", "DAILY.md")
    git(root, *LEAGUE_AUTHOR, "commit", "-q", "-m",
        f"DAILY.md: loop session {record.get('started', '')[:13]} {record.get('status')}",
        "--", "DAILY.md")
    return True


def write_context(root: Path, wt: Path, out: Path):
    """.loop/context.md in the worktree: what the read-only architect can't run itself."""
    def run(*cmd, cwd=root):
        try:
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                  timeout=60).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            return f"(unavailable: {exc})"
    def tail(p: Path, n: int):
        return "\n".join(p.read_text().splitlines()[-n:]) if p.exists() else "(none)"
    home = out / "site" / "index.html"
    site = ""
    if home.exists():
        import html as _h
        import re as _re
        site = _re.sub(r"\s+", " ", _h.unescape(_re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>",
                                                       " ", home.read_text(), flags=_re.S)))[:4000]
    import sys as _sys
    parts = [("git log (master, newest first)", run("git", "log", "--oneline", "-30", "master")),
             ("health", run(_sys.executable, "-m", "colosseum.health")),
             ("last night's league log (tail)", tail(out / "house_league.log", 40)),
             ("last night's ledger record", tail(out / "nights.jsonl", 1)),
             ("last publish", (out / "publish.json").read_text().strip()
              if (out / "publish.json").exists() else "(none)"),
             ("the live site's home page, as text (out/site/index.html)", site or "(not built)"),
             ("FOUNDER_TODO.md", (root / "FOUNDER_TODO.md").read_text()
              if (root / "FOUNDER_TODO.md").exists() else "(none)"),
             ("DECISIONS.local.md (tail)", tail(root / "DECISIONS.local.md", 30)),
             ("the last five loop sessions", tail(out / "daily" / "sessions.jsonl", 5))]
    d = wt / ".loop"
    d.mkdir(exist_ok=True)
    (d / "context.md").write_text("\n\n".join(f"## {k}\n\n{v}" for k, v in parts) + "\n")


def session_input() -> str:
    """The founder's PROMPT, run by the Ralph loop plugin as the in-session runner."""
    return (f'/ralph-loop:ralph-loop "{PROMPT}" --max-iterations {RALPH_ITERATIONS} '
            f'--completion-promise "{RALPH_PROMISE}"')


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
        env = dict(env, ENABLE_CLAUDEAI_MCP_SERVERS="false")     # no claude.ai connectors
        write_context(root, wt, out)
        record["agents"] = write_setup(wt)
        transcript = out / "daily" / f"{record['started'][:16].replace(':', '')}.jsonl"
        before = git(root, "rev-parse", "master").stdout.strip()
        record.update(run_session(session_command(binary, root, wt), session_input(), wt,
                                  transcript, env, timeout))
        record["verdict"] = reviewer_verdict(transcript)
        record["signal"] = architect_signal(transcript)
        status, detail = finish(root, wt, test_cmd, transcript)
        record.update(status=status, detail=detail)
        if status == "merged":
            record["merged_commits"] = git(root, "log", "--format=%h %s",
                                           f"{before}..master").stdout.splitlines()
        record["daily_published"] = write_daily(root, record)
        _write_record(out, record, alert=status in (
            "red", "conflict", "dirty", "protected", "claude-md", "unreviewed", "trailer")
            or record.get("exit") not in (0, None))
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
