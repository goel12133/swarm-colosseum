"""Operations: failure alerts, disk rotation, backups, and the steps after each night.

    python -m colosseum.ops after-night      # what nightly.sh runs after the league
    python -m colosseum.ops rotate [--dry-run]
    python -m colosseum.ops backup

ALERT.md.  A failed night writes out/ALERT.md (reason + last 30 log lines). It stays until
           the next successful night deletes it. `ls out/ALERT.md` is the whole check.

Rotation.  Replays: every replay from the last ROTATE_DAYS days is kept, and every replay
           of the current roster whatever its age (the result cache means a live pairing
           may not have been replayed in weeks). Older replays are kept only if a weekly
           meta report made a clip of them, or they are some bot's best or worst match
           among all its replays on disk; everything else older is deleted.
           Replays are reproducible from bots and seeds, so this loses no information.
           Raw generator responses (out/house_raw/) are kept RAW_DAYS days.

Backups.   One tar.gz a night in ~/backups/: bots/, reports/, out/leaderboard.json,
           out/matrix.json, BALANCE.md, SEASON.md. That is everything needed to rebuild the
           season. The last BACKUP_KEEP are kept. No secrets: .house_league.env* is outside
           every path in the list and is excluded by name anyway.

after-night runs the weekly report (if due), the tactic library, the site bundle (which
links the library and the season archive), 500 engine fuzz trajectories
(3.9; out/fuzz.jsonl), rotation and the backup, times
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
        f"# Alert\n\n{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n"
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
    # With the result cache a pairing that doesn't rerun never rewrites its replay, so every
    # replay of the current roster is kept whatever its age.
    lb_path = out / "leaderboard.json"
    if lb_path.exists():
        lb = json.loads(lb_path.read_text())
        live = {r["name"] for role in ("attackers", "defenders") for r in lb[role]}
        for p in replays:
            a, d, _ = p.stem.split("__")
            if a in live and d in live:
                keep[p.name] = "current roster"
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


# --- the watch ---------------------------------------------------------------------
# Founder's decision, 2026-09-29: S0-2 is deferred a week. Each night, does any defender
# hold synchronized_ring under a 90% win rate? None after seven nights -> structural, and
# season two fixes the economy. One does -> it was a meta and the rules were fine.

WATCH_BOT = "2026-09-29_attacker_synchronized_ring"
WATCH_FROM = "2026-09-30"            # first night after the decision
WATCH_NIGHTS = 7
WATCH_BAR = 0.90

# Every watch the founder has opened. Same rule each time: seven nights for the league to
# hold the bot under WATCH_BAR; if something does, it was a meta, otherwise it's structural.
#   S0-2 (2026-09-29): an attacker beating every defender.
#   S0-3 (2026-10-04): a defender at 91% while defenders win 62% of matches.
WATCHES = (
    dict(bot=WATCH_BOT, role="attacker", start=WATCH_FROM, nights=WATCH_NIGHTS,
         bar=WATCH_BAR, stem="WATCH", finding="S0-2"),
    dict(bot="2026-10-01_defender_convergence_blast_scheduler", role="defender",
         start="2026-10-05", nights=7, bar=0.90, stem="WATCH_S0-3", finding="S0-3"),
)


def watch_row(out: Path = DEFAULT_OUT, when: str = None, watch: dict = WATCHES[0]):
    """This night's numbers for the watched bot from breaches.json and leaderboard.json.
    rate = how often the watched bot wins against each opponent."""
    b = json.loads((out / "breaches.json").read_text())
    lb = json.loads((out / "leaderboard.json").read_text())
    bot, seeds = watch["bot"], b["seeds"]
    if watch["role"] == "attacker":
        row = b["breaches"].get(bot)
        if row is None:
            return None
        per = {d: n / seeds for d, n in row.items()}
    else:
        if not any(bot in r for r in b["breaches"].values()):
            return None
        per = {a: (seeds - r.get(bot, seeds)) / seeds for a, r in b["breaches"].items()}
    best = min(per, key=lambda o: (per[o], o))
    ladder = lb["attackers" if watch["role"] == "attacker" else "defenders"]
    overall = next((r["win_rate"] for r in ladder if r["name"] == bot), None)
    return dict(date=when or date.today().isoformat(), overall=overall,
                best_defender=best, best_rate=per[best],
                under=sorted(o for o, r in per.items() if r < watch["bar"]), per=per)


def update_watch(out: Path = DEFAULT_OUT, when: str = None):
    """Update every watch; returns the first watch's row (kept for older callers)."""
    first = None
    for watch in WATCHES:
        row = watch_row(out, when, watch)
        path = out / ("watch.jsonl" if watch["stem"] == "WATCH" else
                      f"{watch['stem'].lower()}.jsonl")
        rows = [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        if row:
            rows = [r for r in rows if r["date"] != row["date"]] + [row]
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        (out / f"{watch['stem']}.md").write_text(watch_text(rows, watch))
        first = first or row
    return first


def watch_text(rows, watch: dict = WATCHES[0]):
    bot, start, nights, bar = watch["bot"], watch["start"], watch["nights"], watch["bar"]
    opp = "defender" if watch["role"] == "attacker" else "attacker"
    counted = [r for r in rows if r["date"] >= start][:nights]
    lines = [f"# Watch: {bot}", "",
             f"Finding {watch['finding']}. Does any {opp} hold it under {bar:.0%}? Nights "
             f"from {start}, {nights} to decide.", "",
             f"| night | its win rate | best {opp} against it | its rate there | under 90%? |",
             "|---|---|---|---|---|"]
    for r in rows:
        mark = "" if r["date"] >= start else " (before)"
        overall = f"{r['overall']:.0%}" if r.get("overall") is not None else "—"
        lines.append(f"| {r['date']}{mark} | {overall} | {r['best_defender']} | "
                     f"{r['best_rate']:.0%} | {', '.join(r['under']) or 'no'} |")
    found = [r for r in counted if r["under"]]
    lines.append("")
    if found:
        lines.append(f"**Verdict: a meta.** {found[0]['under'][0]} held it under "
                     f"{bar:.0%} on {found[0]['date']}.")
    elif len(counted) >= nights:
        lines.append(f"**Verdict: structural.** No {opp} held it under {bar:.0%} in "
                     f"{nights} nights.")
    else:
        lines.append(f"Undecided: {len(counted)} of {nights} nights so far, none under "
                     f"{bar:.0%}.")
    return "\n".join(lines) + "\n"


# --- committed results (make reproduce) ---------------------------------------------

RESULT_FILES = ("leaderboard.json", "matrix.json", "breaches.json")


def commit_results(root: Path = ROOT, out: Path = DEFAULT_OUT, when: str = None):
    """Commit the night's results/ and its new house bots together, so any commit holds
    both the bots and the results they produce (colosseum.reproduce checks this)."""
    import shutil
    import subprocess

    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, check=True).stdout
    results = root / "results"
    results.mkdir(exist_ok=True)
    for f in RESULT_FILES:
        if (out / f).exists():
            shutil.copy2(out / f, results / f)
    new_bots = [l[3:] for l in git("status", "--porcelain", "--untracked-files=all", "--",
                                   "bots/house").splitlines() if l.startswith("??")]
    paths = [f"results/{f}" for f in RESULT_FILES if (results / f).exists()] + new_bots
    git("add", "--", *paths)
    if not git("diff", "--cached", "--name-only", "--", *paths).strip():
        return []
    git("-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost",
        "commit", "-q", "-m",
        f"Night {when or date.today().isoformat()}: results and house bots", "--", *paths)
    return paths


# --- the 14-night persona ablation (sprint L3), its own session ------------------------

ABLATION_NIGHTS = 14
ABLATION_FROM = "2026-09-29"           # the first night with personas
ABLATION_TOKEN_CAP = 200_000           # the league's nightly cap, shared with that night


def ablation_session(out: Path = DEFAULT_OUT, root: Path = ROOT):
    """Run by its own cron entry after the league, never inside the nightly run.

    Due from real night 14. Each run generates as many slots as fit under the nightly token
    cap after that night's league spend (the script projects each call conservatively and
    stops cleanly before one that could cross it), and continues next time. Once every slot
    is filled the script plays both arms, re-renders research/03 and commits it."""
    import subprocess
    from . import meta_report
    work = out / "ablation_14"
    if (work / "done").exists():
        return "done"
    nights = [d for d, _ in meta_report.load_nights(out)]
    if len(nights) < ABLATION_NIGHTS:
        return f"not due ({len(nights)} of {ABLATION_NIGHTS} nights)"
    use = [d for d in nights[:ABLATION_NIGHTS] if d >= ABLATION_FROM]
    today = date.today().isoformat()
    league = sum(((r.get("spend") or {}).get("input_tokens", 0) or 0)
                 + ((r.get("spend") or {}).get("output_tokens", 0) or 0)
                 for d, runs in meta_report.load_nights(out) if d == today for r in runs)
    gen = work / "generation.json"
    earlier_today = sum(r.get("tokens") or 0 for r in
                        (json.loads(gen.read_text()) if gen.exists() else [])
                        if r.get("day") == today)
    budget = ABLATION_TOKEN_CAP - league - earlier_today
    if budget <= 0:
        return f"no budget left tonight (league {league:,}, ablation {earlier_today:,})"
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "run.log", "a") as log:
        proc = subprocess.run([sys.executable, str(root / "scripts" / "ablation_personas.py"),
                               "--nights", *use, "--out", str(work), "--max-tokens",
                               str(budget), "--render",
                               str(root / "research" / "03_persona_ablation.md"), "--commit"],
                              cwd=root, stdout=log, stderr=log)
    if proc.returncode == 0:
        (work / "done").write_text(today + "\n")
        return "complete: research/03 re-rendered and committed"
    if proc.returncode == 3:
        return f"partial: stopped cleanly at the token budget ({budget:,}); continues next run"
    write_alert(f"persona ablation session failed (exit {proc.returncode}); see "
                f"{work / 'run.log'}")
    return f"failed (exit {proc.returncode})"


# --- the season report, kept current (sprint L14) -----------------------------------

def season_report_step(root: Path = ROOT, out: Path = DEFAULT_OUT, commit: bool = True):
    """Rewrite reports/SEASON_1.md every night: a marked draft until night 28, then the
    finished report (with its clips), so it completes itself on the boundary night."""
    import subprocess
    from . import meta_report, season
    nights = len(meta_report.season_nights(meta_report.load_nights(out)))
    final = nights >= season.LENGTH_NIGHTS
    meta_report.write_season(out, with_clip=final)
    if not commit:
        return f"written ({nights} of {season.LENGTH_NIGHTS} nights)"
    rel = "reports/SEASON_1.md"
    subprocess.run(["git", "-C", str(root), "add", "--", rel], check=True)
    changed = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet", "--",
                              rel]).returncode != 0
    if changed:
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Swarm Colosseum league",
                        "-c", "user.email=league@localhost", "commit", "-q", "-m",
                        f"Season report: {'final' if final else 'draft'}, {nights} of "
                        f"{season.LENGTH_NIGHTS} nights", "--", rel], check=True)
    return f"{'final' if final else 'draft'}, {nights} nights, {'committed' if changed else 'unchanged'}"


# --- republishing the public repo and site (launch, 2026-10-10) ---------------------

PUBLIC_REMOTE = "git@github.com:goel12133/swarm-colosseum.git"
DEPLOY_KEY = Path.home() / ".ssh" / "swarm_colosseum_deploy"


def _ssh_env(key: Path) -> dict:
    import os
    return dict(os.environ, GIT_SSH_COMMAND=f"ssh -i {key} -o IdentitiesOnly=yes "
                "-o StrictHostKeyChecking=accept-new")


def publish_step(root: Path = ROOT, out: Path = DEFAULT_OUT, remote: str = PUBLIC_REMOTE,
                 key: Path = DEPLOY_KEY):
    """Republish after the night: fetch the public main, and push only if it is still what
    we last published (or the repo is empty, on the first publish). If main has moved (a
    commit or merged PR made on GitHub) this refuses and raises, so after_night writes
    ALERT.md; folding merged submission PRs back into master is built with 3.8, before
    submissions open. Not armed until the deploy key exists (the founder creates it)."""
    import subprocess
    if not key.exists():
        return f"not armed: no deploy key at {key}"
    record = out / "publish.json"
    last = json.loads(record.read_text())["main"] if record.exists() else None
    env = _ssh_env(key)
    ls = subprocess.run(["git", "ls-remote", remote, "refs/heads/main"], env=env,
                        capture_output=True, text=True, timeout=120)
    if ls.returncode != 0:
        raise RuntimeError(f"cannot reach {remote}: {ls.stderr.strip()[:200]}")
    public = ls.stdout.split()[0] if ls.stdout.strip() else None
    if public != last:
        raise RuntimeError(f"public main is {public or 'empty'} but we last published "
                           f"{last or 'nothing'}: not republishing until a person looks")
    proc = subprocess.run([str(root / "scripts" / "publish.sh"), "--live", "--site",
                           str(out / "site"), remote, str(key)], cwd=root,
                          capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"publish.sh exit {proc.returncode}: {proc.stderr.strip()[-300:]}")
    line = proc.stdout.strip().splitlines()[-1]      # "published: main <short>, gh-pages <short>"
    ls = subprocess.run(["git", "ls-remote", remote, "refs/heads/main", "refs/heads/gh-pages"],
                        env=env, capture_output=True, text=True, timeout=120, check=True)
    refs = {r.split("/")[-1]: sha for sha, r in (l.split() for l in ls.stdout.splitlines())}
    record.write_text(json.dumps(dict(refs, when=datetime.now(timezone.utc).isoformat(
        timespec="seconds")), sort_keys=True) + "\n")
    return line


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


FUZZ_NIGHTLY = 500


def nightly_fuzz(out: Path = DEFAULT_OUT, when: str = None, n: int = FUZZ_NIGHTLY):
    """Engine fuzzer (3.9): n new trajectories a night, numbered from the date so a failure
    is reproducible with `python -m colosseum.fuzz --start <first failing> --n 1`. One line
    a night in out/fuzz.jsonl; any failure raises, which after_night turns into ALERT.md."""
    from . import fuzz
    when = when or date.today().isoformat()
    report = fuzz.run(int(when.replace("-", "")) * 10000, n)
    with (out / "fuzz.jsonl").open("a") as f:
        f.write(json.dumps(dict(date=when, **report), sort_keys=True) + "\n")
    if report["failed"]:
        first = report["failures"][0]
        raise RuntimeError(f"{report['failed']}/{n} fuzz trajectories failed; first "
                           f"{first['trajectory']}: {first['error']}")
    return f"{n} trajectories ok in {report['seconds']} s"


def after_night(commit: bool = True):
    """Weekly report if due, tactic library, site bundle, publish, fuzz, rotation, backup.
    Returns (problems, results)."""
    problems, results = [], {}
    t0 = time.monotonic()

    def meta_report():
        from . import meta_report as mr
        week = mr.due_week()
        return str(mr.write(week, commit=commit)) if week else "not due"

    def tactic_library():
        from . import library
        try:
            return library.build()
        except SystemExit as exc:          # "no ladder": an alert, not the end of the steps
            raise RuntimeError(str(exc)) from None

    def site_bundle():
        from . import site
        info = site.build()
        size = site.bundle_bytes(info["site"])
        if size > site.SIZE_BUDGET:          # still published; the alert says to trim more
            raise RuntimeError(f"site is {size / 1e6:.1f} MB, over the "
                               f"{site.SIZE_BUDGET / 1e6:.0f} MB budget")
        return dict(info, mb=round(size / 1e6, 1))

    def results_step():
        return commit_results() if commit else "skipped (--no-commit)"

    for label, fn in (("results", results_step), ("watch", update_watch),
                      ("meta report", meta_report),
                      ("season report", lambda: season_report_step(commit=commit)),
                      ("library", tactic_library), ("site", site_bundle),
                      ("publish", lambda: publish_step() if commit else "skipped (--no-commit)"),
                      ("fuzz", nightly_fuzz),
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
    sub.add_parser("ablation-session", help="the 14-night persona ablation (own cron entry)")
    sub.add_parser("publish", help="publish the repo and out/site, as after-night does; the "
                   "first publish goes through here so out/publish.json records it")
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
    if args.cmd == "ablation-session":
        print(ablation_session())
        return 0
    if args.cmd == "publish":
        print(publish_step())
        return 0
    if args.cmd == "alert":
        print(write_alert(args.reason))
        return 0


if __name__ == "__main__":
    sys.exit(main())
