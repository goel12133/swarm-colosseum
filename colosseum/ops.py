"""Operations: failure alerts, disk rotation, backups, and the steps after each night.

    python -m colosseum.ops after-night      # what nightly.sh runs after the league
    python -m colosseum.ops rotate [--dry-run]
    python -m colosseum.ops backup

ALERT.md.  A failed night writes out/ALERT.md (reason + last 30 log lines). It stays until
           the next successful night deletes it. `ls out/ALERT.md` is the whole check.

Rotation.  Replays: every replay from the last ROTATE_DAYS days is kept. Older replays are
           kept only if a weekly meta report made a clip of them, or they are some bot's best
           or worst match among all its replays on disk; everything else older is deleted.
           Replays are reproducible from bots and seeds, so this loses no information.
           Raw generator responses (out/house_raw/) are kept RAW_DAYS days.

Backups.   One tar.gz a night in ~/backups/: bots/, reports/, out/leaderboard.json,
           out/matrix.json, BALANCE.md, SEASON.md. That is everything needed to rebuild the
           season. The last BACKUP_KEEP are kept. No secrets: .house_league.env* is outside
           every path in the list and is excluded by name anyway.

after-night runs the weekly report (if due), the site bundle, rotation and the backup, times
them, and records the total as the "reports" phase on the night's ledger line. A failure in
any of them writes ALERT.md but never touches the league's own result.
"""
import argparse
import json
import sys
import tarfile
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from .tournament import DEFAULT_OUT, ROOT

ALERT = DEFAULT_OUT / "ALERT.md"
LOG = DEFAULT_OUT / "house_league.log"
NIGHTS = DEFAULT_OUT / "nights.jsonl"
BACKUPS = Path.home() / "backups"
BACKUP_KEEP = 14
ROTATE_DAYS = 14          # "the current and previous week"
RAW_DAYS = 30
BACKUP_PATHS = ("bots", "reports", "out/leaderboard.json", "out/matrix.json", "BALANCE.md",
                "SEASON.md")


# --- alerts -----------------------------------------------------------------------

def write_alert(reason: str, log: Path = None, alert: Path = None):
    log, alert = log or LOG, alert or ALERT
    tail = log.read_text().splitlines()[-30:] if log.exists() else ["(no log)"]
    alert.parent.mkdir(parents=True, exist_ok=True)
    alert.write_text(
        f"# Night failed\n\n{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n"
        f"**Reason:** {reason}\n\nThis file stays until the next successful night.\n\n"
        "## Last 30 log lines\n\n```\n" + "\n".join(tail) + "\n```\n")
    return alert


def clear_alert(alert: Path = None):
    alert = alert or ALERT
    if alert.exists():
        alert.unlink()
        return True
    return False


# --- rotation ---------------------------------------------------------------------

def _own_score(path: Path, name: str):
    meta = json.loads(path.read_text())["meta"]
    a = path.stem.split("__")[0]
    return (1 - meta["score_defender"]) if name == a else meta["score_defender"]


def rotation_plan(out: Path = DEFAULT_OUT, now: float = None):
    """(delete, kept) for replays and raw responses. Pure: deletes nothing."""
    now = time.time() if now is None else now
    replays = sorted((out / "replays").glob("*__*__s*.json"))
    old = {p for p in replays if now - p.stat().st_mtime > ROTATE_DAYS * 86400}
    keep = {}
    clips = out / "meta" / "clips.json"
    if clips.exists():
        for name in json.loads(clips.read_text()):
            keep[name] = "meta-report clip"
    by_bot = {}
    for p in replays:
        a, d, _ = p.stem.split("__")
        for bot in (a, d):
            by_bot.setdefault(bot, []).append(p)
    for bot, paths in by_bot.items():
        if not any(p in old for p in paths):
            continue
        scored = sorted(paths, key=lambda p: (_own_score(p, bot), p.name))
        keep.setdefault(scored[0].name, f"worst match of {bot}")
        keep.setdefault(scored[-1].name, f"best match of {bot}")
    delete = sorted(p for p in old if p.name not in keep)
    raw = sorted((out / "house_raw").glob("*")) if (out / "house_raw").exists() else []
    delete += [p for p in raw if now - p.stat().st_mtime > RAW_DAYS * 86400]
    return delete, keep


def rotate(out: Path = DEFAULT_OUT, now: float = None, dry_run: bool = False):
    delete, kept = rotation_plan(out, now)
    freed = sum(p.stat().st_size for p in delete)
    if not dry_run:
        for p in delete:
            p.unlink()
    return dict(deleted=len(delete), freed_bytes=freed, kept_old=len(kept))


# --- backups ----------------------------------------------------------------------

def backup(dest: Path = None, root: Path = ROOT, keep: int = BACKUP_KEEP, today: str = None):
    dest = dest or BACKUPS
    dest.mkdir(parents=True, exist_ok=True)
    name = dest / f"swarm-colosseum-{today or date.today().isoformat()}.tar.gz"

    def skip(info):
        base = Path(info.name).name
        if base == "__pycache__" or base.endswith(".pyc") or base.startswith(".house_league"):
            return None
        return info
    with tarfile.open(name, "w:gz") as tar:
        for rel in BACKUP_PATHS:
            p = root / rel
            if p.exists():
                tar.add(p, arcname=rel, filter=skip)
    for old in sorted(dest.glob("swarm-colosseum-*.tar.gz"))[:-keep]:
        old.unlink()
    return name


# --- after the night ----------------------------------------------------------------

def record_phase(seconds: float, nights: Path = None):
    """Add the 'reports' phase to the last ledger line (the night just run)."""
    nights = nights or NIGHTS
    if not nights.exists():
        return
    lines = nights.read_text().splitlines()
    if not lines:
        return
    rec = json.loads(lines[-1])
    rec.setdefault("phases", {})["reports"] = round(seconds, 2)
    lines[-1] = json.dumps(rec)
    nights.write_text("\n".join(lines) + "\n")


def after_night(commit: bool = True):
    """Weekly report if due, site bundle, rotation, backup. Returns (problems, results)."""
    problems, results = [], {}
    t0 = time.monotonic()

    def meta_report():
        from . import meta_report as mr
        week = mr.due_week()
        return str(mr.write(week, commit=commit)) if week else "not due"

    def site_bundle():
        from . import site
        return site.build()

    for label, fn in (("meta report", meta_report), ("site", site_bundle),
                      ("rotation", rotate), ("backup", lambda: str(backup()))):
        try:
            results[label] = fn()
        except Exception as exc:
            problems.append(f"{label}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    record_phase(time.monotonic() - t0)
    if problems:
        write_alert("after-night step failed: " + "; ".join(problems))
    return problems, results


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("after-night")
    an.add_argument("--no-commit", action="store_true")
    r = sub.add_parser("rotate")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("backup")
    fail = sub.add_parser("alert", help="write ALERT.md (used by nightly.sh)")
    fail.add_argument("reason")
    args = ap.parse_args()
    if args.cmd == "after-night":
        problems, results = after_night(commit=not args.no_commit)
        print(json.dumps({k: str(v) for k, v in results.items()}))
        for p in problems:
            print(f"PROBLEM: {p}")
        return 1 if problems else 0
    if args.cmd == "rotate":
        print(json.dumps(rotate(dry_run=args.dry_run)))
        return 0
    if args.cmd == "backup":
        print(backup())
        return 0
    if args.cmd == "alert":
        print(write_alert(args.reason))
        return 0


if __name__ == "__main__":
    sys.exit(main())
