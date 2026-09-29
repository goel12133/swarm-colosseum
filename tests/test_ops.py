"""Operations: rotation rule, alerts, backups, the reports phase, and the health check."""
import json
import os
import tarfile
import time
from datetime import date

from colosseum import health, ops

DAY = 86400


def replay(out, a, d, seed, score_def, age_days, now):
    p = out / "replays" / f"{a}__{d}__s{seed}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"meta": {"score_defender": score_def}}))
    os.utime(p, (now - age_days * DAY, now - age_days * DAY))
    return p


def test_rotation_keeps_recent_clips_and_each_bots_best_and_worst(tmp_path):
    now = time.time()
    out = tmp_path
    recent = replay(out, "rush", "layered", 0, 0.5, 3, now)            # this week: kept
    # an old bot with three old matches: best (0.1 -> attacker 0.9) and worst kept
    best = replay(out, "old_att", "layered", 0, 0.1, 20, now)
    mid = replay(out, "old_att", "layered", 1, 0.5, 20, now)
    worst = replay(out, "old_att", "layered", 2, 0.9, 20, now)
    clipped = replay(out, "old_att", "gun_only", 0, 0.5, 20, now)
    (out / "meta").mkdir()
    (out / "meta" / "clips.json").write_text(json.dumps([clipped.name]))
    raw_old = out / "house_raw" / "old.md"
    raw_old.parent.mkdir()
    raw_old.write_text("x")
    os.utime(raw_old, (now - 40 * DAY, now - 40 * DAY))
    raw_new = out / "house_raw" / "new.md"
    raw_new.write_text("x")

    delete, kept = ops.rotation_plan(out, now)
    names = {p.name for p in delete}
    assert names == {mid.name, "old.md"}
    assert kept[clipped.name] == "meta-report clip"
    assert best.name in kept and worst.name in kept
    result = ops.rotate(out, now)
    assert result["deleted"] == 2 and recent.exists() and not mid.exists()
    assert raw_new.exists() and not raw_old.exists()


def test_alert_written_then_cleared(tmp_path):
    log = tmp_path / "log"
    log.write_text("\n".join(f"line {i}" for i in range(50)))
    alert = ops.write_alert("claude CLI failed", log, tmp_path / "ALERT.md")
    text = alert.read_text()
    assert "claude CLI failed" in text and "line 49" in text and "line 19" not in text
    assert ops.clear_alert(alert) and not alert.exists()


def test_backup_contents_and_keeps_the_last_14(tmp_path):
    root = tmp_path / "repo"
    (root / "bots" / "house" / "__pycache__").mkdir(parents=True)
    (root / "bots" / "house" / "b.py").write_text("x")
    (root / "bots" / "house" / "__pycache__" / "b.pyc").write_text("x")
    (root / "out").mkdir()
    (root / "out" / "leaderboard.json").write_text("{}")
    (root / "BALANCE.md").write_text("x")
    (root / ".house_league.env").write_text("SECRET")
    dest = tmp_path / "backups"
    for day in range(1, 17):
        ops.backup(dest, root, today=f"2026-10-{day:02d}")
    kept = sorted(p.name for p in dest.iterdir())
    assert len(kept) == 14 and kept[0] == "swarm-colosseum-2026-10-03.tar.gz"
    with tarfile.open(dest / kept[-1]) as tar:
        names = tar.getnames()
    assert "bots/house/b.py" in names and "out/leaderboard.json" in names
    assert not any("__pycache__" in n or "house_league" in n for n in names)


def test_reports_phase_is_added_to_the_last_night(tmp_path):
    nights = tmp_path / "nights.jsonl"
    nights.write_text(json.dumps({"date": "a", "phases": {"tournament": 90}}) + "\n"
                      + json.dumps({"date": "b", "phases": {"tournament": 91}}) + "\n")
    ops.record_phase(12.345, nights)
    rows = [json.loads(l) for l in nights.read_text().splitlines()]
    assert rows[0]["phases"] == {"tournament": 90}
    assert rows[1]["phases"] == {"tournament": 91, "reports": 12.35}


def test_health_last_night_and_alert(tmp_path):
    (tmp_path / "nights.jsonl").write_text(
        json.dumps({"date": "2026-10-01", "status": "ok"}) + "\n"
        + json.dumps({"date": "2026-10-02", "status": "error", "reason": "Not logged in"})
        + "\n")
    ok, detail = health.check_last_night(tmp_path, today=date(2026, 10, 2))
    assert not ok and "Not logged in" in detail
    (tmp_path / "nights.jsonl").write_text(json.dumps({"date": "2026-09-20",
                                                       "status": "ok"}) + "\n")
    ok, detail = health.check_last_night(tmp_path, today=date(2026, 10, 2))
    assert not ok and "more than a day old" in detail
    assert health.check_alert(tmp_path)[0]
    (tmp_path / "ALERT.md").write_text("x")
    assert not health.check_alert(tmp_path)[0]
    text = health.report_text([("docker", True, "fine"), ("cron", False, "missing")])
    assert text.splitlines() == ["ok  docker     fine", "BAD cron       missing"]


def test_watch_verdicts():
    def row(d, rate):
        return dict(date=d, overall=0.95, best_defender="x", best_rate=rate,
                    under=["x"] if rate < 0.9 else [], per={"x": rate})
    before = [row("2026-09-29", 0.8)]                  # before the watch: does not count
    nights = [row(f"2026-10-0{i}", 1.0) for i in range(1, 7)]
    assert "Undecided: 0 of 7" in ops.watch_text(before)
    assert "Undecided: 6 of 7" in ops.watch_text(before + [row("2026-09-30", 0.9)]
                                                 + nights[:5])
    seven = [row("2026-09-30", 0.9)] + nights
    assert "Verdict: structural" in ops.watch_text(before + seven)
    seven[3] = row(seven[3]["date"], 0.8)
    assert "Verdict: a meta" in ops.watch_text(before + seven)
