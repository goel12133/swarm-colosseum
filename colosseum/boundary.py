"""The season boundary, scripted (post-launch, founder, 2026-10-10; charter section 2).

Runs from scripts/nightly.sh before the league, on the first night of the next season
(season.ENDS, 2026-10-26 for season one: SEASON.md says candidate A merges "on 2026-10-26,
not before"). In the live repo, on a branch:
  0. write the final season report (reports/SEASON_<n>.md, with clips) and commit it
  1. freeze seasons/S<n>/: the final ladders, matrix and breaches, BALANCE.md, SEASON.md,
     every meta report and its clips, the season report, and every bot's final source and
     metadata
  2. merge the prepared, already-tested next-season branch (NEXT_BRANCH: candidate A plus
     the season and rules version bumps); the rules hash and engine version change with
     it, so every cached result misses and every match replays under the new rules, and
     Elo, rebuilt from START each night, starts again at 1000 for everyone; every live bot
     is kept
  3. run the full suite, then fast-forward master
Anything unexpected (a dirty tree, the next-season branch missing, a merge conflict, a red
suite) stops it with master untouched, and nightly.sh then skips that
night's league and alerts, so no stray night runs on the old rules. Rerun by hand once fixed:
    python -m colosseum.boundary --if-due
"""
import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import season
from .tournament import DEFAULT_OUT, ROOT

NEXT_BRANCH = "season2"
LEAGUE = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]
BOT_DIRS = ("attackers", "defenders", "house", "submitted/attacker", "submitted/defender")


class NotReady(RuntimeError):
    pass


def _git(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=check)


def archive(root: Path) -> Path:
    return root / "seasons" / f"S{season.NUMBER}"


def due(root: Path = ROOT, today: date = None) -> bool:
    today = today or date.today()
    return today >= season.ENDS and not archive(root).exists()


def check_ready(root: Path, out: Path):
    if _git(root, "status", "--porcelain").stdout.strip():
        raise NotReady("the live repo has uncommitted changes")
    if _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "master":
        raise NotReady("the live repo is not on master")
    if _git(root, "rev-parse", "--verify", "-q", NEXT_BRANCH, check=False).returncode:
        raise NotReady(f"branch {NEXT_BRANCH} does not exist")


def freeze(root: Path, out: Path) -> list:
    """Copy the season's record into seasons/S<n>/. Returns the paths written."""
    dest = archive(root)
    written = []

    def put(src: Path, rel: str):
        if src.exists():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
            written.append(rel)

    for name in ("leaderboard.json", "matrix.json", "breaches.json"):
        put(out / name, name)
    put(root / "BALANCE.md", "BALANCE.md")
    put(root / "SEASON.md", "SEASON.md")
    put(root / "reports" / f"SEASON_{season.NUMBER}.md", "SEASON_REPORT.md")
    for p in sorted((out / "meta").glob("WEEK_*")):
        if p.suffix in (".md", ".mp4", ".gif"):
            put(p, f"meta/{p.name}")
    for p in sorted((out / "meta").glob(f"SEASON_{season.NUMBER}_*")):
        if p.suffix in (".mp4", ".gif"):
            put(p, f"meta/{p.name}")
    for folder in BOT_DIRS:
        for p in sorted((root / "bots" / folder).glob("*")):
            if p.suffix in (".py", ".json") and p.is_file() and not p.is_symlink():
                put(p, f"bots/{folder}/{p.name}")
    return written


def run(root: Path = ROOT, out: Path = DEFAULT_OUT, verify=None, season_report=None) -> str:
    check_ready(root, out)
    n = season.NUMBER
    # the final season report, with its clips, committed to master (a night may have been
    # missed, so this doesn't wait for 28 of them; the report counts the nights it has)
    from . import ops
    (season_report or (lambda: ops.season_report_step(root=root, out=out, final=True)))()
    branch = f"boundary-s{n}"
    _git(root, "checkout", "-q", "-b", branch, "master")
    try:
        written = freeze(root, out)
        _git(root, "add", "--", str(archive(root).relative_to(root)))
        _git(root, *LEAGUE, "commit", "-q", "-m",
             f"Season boundary: freeze seasons/S{n}/ ({len(written)} files)")
        merge = _git(root, *LEAGUE, "merge", "-q", "--no-ff", "-m",
                     f"Season boundary: merge {NEXT_BRANCH} (season {n + 1} rules)",
                     NEXT_BRANCH, check=False)
        if merge.returncode:
            _git(root, "merge", "--abort", check=False)
            raise RuntimeError(f"merging {NEXT_BRANCH} conflicted: "
                               f"{(merge.stdout + merge.stderr).strip()[-300:]}")
        if not (verify or full_suite)(root):
            raise RuntimeError(f"the suite is red on {branch}; master unchanged, branch kept")
    except Exception:
        _git(root, "checkout", "-q", "-f", "master", check=False)
        raise
    _git(root, "checkout", "-q", "master")
    _git(root, "merge", "-q", "--ff-only", branch)
    _git(root, "branch", "-q", "-d", branch)
    return f"season {n} frozen ({len(written)} files) and {NEXT_BRANCH} merged"


def full_suite(root: Path) -> bool:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x"], cwd=root,
                          capture_output=True, timeout=1800).returncode == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--if-due", action="store_true", help="do nothing (exit 0) unless due")
    args = ap.parse_args(argv)
    if args.if_due and not due():
        return 0
    try:
        print(run())
        return 0
    except Exception as exc:                     # nightly.sh alerts and skips the league
        print(f"boundary failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
