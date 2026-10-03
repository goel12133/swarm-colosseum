"""One line per subsystem; exit 1 if any is bad.

    python -m colosseum.health

    docker      the daemon answers (the sandbox needs it)
    cli-login   `claude auth status` says logged in (only loggedIn/authMethod are read;
                nothing under ~/.claude is opened, and the account email is never printed)
    cron        the nightly entry is in root's crontab
    disk        % used and free space on the filesystem holding out/ (bad at 70% or more),
                and the size of out/
    last-night  the newest line of out/nights.jsonl: status, and whether it is recent
    alert       out/ALERT.md is absent
"""
import json
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from .tournament import DEFAULT_OUT, ROOT

MIN_FREE_GB = 5.0
MAX_OUT_GB = 20.0
MAX_USED_PCT = 70.0     # charter section 4: disk under 70%


def _run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def check_docker():
    p = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    return (p.returncode == 0, f"server {p.stdout.strip()}" if p.returncode == 0
            else "daemon not answering")


def check_cli_login():
    from .house_league import BackendError, find_claude
    try:
        binary = find_claude()
    except BackendError as exc:
        return False, str(exc)
    p = _run([binary, "auth", "status", "--json"])
    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError:
        return False, f"auth status unreadable (exit {p.returncode})"
    ok = bool(info.get("loggedIn"))
    return ok, f"logged in via {info.get('authMethod')}" if ok else "NOT logged in"


def check_cron():
    p = _run(["crontab", "-l"])
    lines = [l for l in p.stdout.splitlines()
             if "scripts/nightly.sh" in l and not l.lstrip().startswith("#")]
    return (bool(lines), lines[0].strip() if lines else "no nightly.sh entry in crontab")


def _size(path: Path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def check_disk(out: Path = DEFAULT_OUT):
    usage = shutil.disk_usage(out if out.exists() else ROOT)
    free = usage.free / 1e9
    pct = 100 * usage.used / usage.total
    used = _size(out) / 1e9
    ok = free >= MIN_FREE_GB and used <= MAX_OUT_GB and pct < MAX_USED_PCT
    return ok, f"{pct:.0f}% used, {free:.0f} GB free, out/ is {used * 1000:.0f} MB"


def check_last_night(out: Path = DEFAULT_OUT, today: date = None):
    today = today or date.today()
    path = out / "nights.jsonl"
    if not path.exists() or not path.read_text().strip():
        return False, "no nights recorded"
    rec = json.loads(path.read_text().strip().splitlines()[-1])
    recent = date.fromisoformat(rec["date"]) >= today - timedelta(days=1)
    ok = rec.get("status") == "ok" and recent
    why = rec.get("status") + (f" ({rec.get('reason')})" if rec.get("reason") else "")
    return ok, f"{rec['date']}: {why}" + ("" if recent else ", and more than a day old")


def check_alert(out: Path = DEFAULT_OUT):
    alert = out / "ALERT.md"
    return (not alert.exists(), "none" if not alert.exists() else "out/ALERT.md is present")


CHECKS = (("docker", check_docker), ("cli-login", check_cli_login), ("cron", check_cron),
          ("disk", check_disk), ("last-night", check_last_night), ("alert", check_alert))


def checks():
    rows = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"check crashed: {type(exc).__name__}: {exc}"
        rows.append((name, ok, detail))
    return rows


def report_text(rows=None) -> str:
    rows = rows if rows is not None else checks()
    return "\n".join(f"{'ok ' if ok else 'BAD'} {name:<10} {detail}" for name, ok, detail in rows)


def main():
    t0 = time.monotonic()
    rows = checks()
    print(report_text(rows))
    print(f"({time.monotonic() - t0:.1f} s)")
    return 0 if all(ok for _, ok, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
