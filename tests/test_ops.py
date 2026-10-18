"""Operations: rotation rule, alerts, backups, the reports phase, and the health check."""
import json
import os
import tarfile
import time
from datetime import date

import pytest

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


def test_a_backup_restores_byte_identical_into_a_scratch_copy(tmp_path):
    root = tmp_path / "repo"
    files = {"bots/house/b.py": "x = 1\n", "reports/FOUNDER_WEEK_1.md": "week\n",
             "out/leaderboard.json": '{"attackers": []}', "out/matrix.json": "{}",
             "BALANCE.md": "balance\n", "SEASON.md": "season\n"}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    archive = ops.backup(tmp_path / "backups", root, today="2026-10-03")
    scratch = tmp_path / "scratch"
    with tarfile.open(archive) as tar:
        tar.extractall(scratch, filter="data")
    restored = {str(p.relative_to(scratch)): p.read_text()
                for p in scratch.rglob("*") if p.is_file()}
    assert restored == files


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


def test_health_disk_fails_at_70_percent_used(tmp_path, monkeypatch):
    from types import SimpleNamespace as usage
    monkeypatch.setattr(health.shutil, "disk_usage",
                        lambda p: usage(total=100e9, used=69e9, free=31e9))
    ok, detail = health.check_disk(tmp_path)
    assert ok and detail.startswith("69% used, 31 GB free")
    monkeypatch.setattr(health.shutil, "disk_usage",
                        lambda p: usage(total=100e9, used=70e9, free=30e9))
    ok, detail = health.check_disk(tmp_path)
    assert not ok and detail.startswith("70% used")


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


def test_rotation_never_deletes_a_current_roster_replay(tmp_path):
    now = time.time()
    live = replay(tmp_path, "rush", "layered", 0, 0.5, 60, now)        # old but live
    gone = replay(tmp_path, "retired_bot", "layered", 0, 0.5, 60, now)
    gone2 = replay(tmp_path, "retired_bot", "layered", 1, 0.6, 60, now)
    gone3 = replay(tmp_path, "retired_bot", "layered", 2, 0.4, 60, now)
    (tmp_path / "leaderboard.json").write_text(json.dumps(
        {"attackers": [{"name": "rush"}], "defenders": [{"name": "layered"}]}))
    delete, kept = ops.rotation_plan(tmp_path, now)
    assert kept[live.name] == "current roster"
    # retired_bot (attacker side): best s2, worst s1 kept; s1 is also layered's best. The
    # middle match is the only one that goes.
    assert {p.name for p in delete} == {gone.name}


def test_the_ablation_session_is_due_at_14_nights_and_budgets_tonight(tmp_path, monkeypatch):
    import subprocess as sp
    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        return sp.CompletedProcess(cmd, 3)          # stopped cleanly at the budget
    monkeypatch.setattr(sp, "run", fake_run)
    today = date.today().isoformat()
    from datetime import timedelta
    start = date(2026, 9, 29)
    days = [(start + timedelta(days=i)).isoformat() for i in range(40)]
    days = [d for d in days if d != today][:13]                 # 13 nights, today not among them
    (tmp_path / "nights.jsonl").write_text("".join(
        json.dumps({"date": d, "status": "ok"}) + "\n" for d in days))
    assert ops.ablation_session(tmp_path).startswith("not due (13 of 14")
    with open(tmp_path / "nights.jsonl", "a") as f:
        f.write(json.dumps({"date": today, "status": "ok",
                            "spend": {"input_tokens": 40_000, "output_tokens": 20_000}}) + "\n")
    status = ops.ablation_session(tmp_path)
    assert status.startswith("partial") and "140,000" in status
    cmd = runs[0]
    assert cmd[cmd.index("--max-tokens") + 1] == "140000"         # 200k - tonight's league
    assert cmd[cmd.index("--nights") + 1] == "2026-09-29" and "--commit" in cmd
    (tmp_path / "ablation_14").mkdir(exist_ok=True)
    (tmp_path / "ablation_14" / "done").write_text("x")
    assert ops.ablation_session(tmp_path) == "done"


def test_the_ablation_is_not_part_of_the_nightly_run():
    import inspect
    assert "ablation" not in inspect.getsource(ops.after_night)


def test_the_ablation_page_renders_from_the_result_alone():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "abl", Path(__file__).resolve().parents[1] / "scripts" / "ablation_personas.py")
    abl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abl)
    arm = dict(mean_score=0.6, top_five=["a"], unique_coverage=0, unique_coverage_5=1,
               unique_coverage_8=2)
    text = abl.render(dict(persona=arm, generalist=arm, nights=["2026-09-29", "2026-10-11"],
                           slots=26, real_league=dict(written=22, slots=26),
                           generation=dict(written=24, calls=26), retired_persona=[3, 22]))
    assert "(2-night run)" in text and "22 / 26" in text and "3 of 22" in text
    # Regression (2026-10-14): the page said "preliminary" in its header, so the site
    # (paper_info) labelled the final run preliminary.
    assert "preliminary" not in text[:600].lower()
    assert "**Bottom line:**" in text


def test_the_committed_persona_page_is_the_final_run():
    from pathlib import Path
    from colosseum import site
    page = Path(__file__).resolve().parents[1] / "research" / "03_persona_ablation.md"
    assert "preliminary" not in page.read_text().lower()
    assert site.paper_info(page)["status"] == "final"


def test_the_committed_annealing_page_is_final():
    from pathlib import Path
    from colosseum import site
    page = Path(__file__).resolve().parents[1] / "research" / "04_annealed_defenders.md"
    assert "preliminary" not in page.read_text()[:600].lower()
    assert site.paper_info(page)["status"] == "final"


def test_after_night_runs_every_step_and_returns_their_results(tmp_path, monkeypatch):
    """Regression: a step function named like the results dict shadowed it (2026-10-04)."""
    from colosseum import meta_report, site
    calls = []
    for name in ("commit_results", "update_watch", "rotate", "season_report_step",
                 "backup", "record_phase", "nightly_fuzz", "publish_step"):
        monkeypatch.setattr(ops, name, lambda *a, _n=name, **k: calls.append(_n) or _n)
    monkeypatch.setattr(meta_report, "due_week", lambda *a, **k: None)
    monkeypatch.setattr(site, "build", lambda *a, **k: calls.append("site") or {"site": "x"})
    monkeypatch.setattr(site, "bundle_bytes", lambda *a: 1)
    from colosseum import library
    monkeypatch.setattr(library, "build", lambda *a, **k: calls.append("library") or "lib")
    monkeypatch.setattr(ops, "write_alert", lambda *a, **k: calls.append("ALERT"))
    problems, results = ops.after_night(commit=True)
    assert problems == [] and "ALERT" not in calls
    assert set(results) == {"results", "watch", "meta report", "season report", "library",
                            "site", "publish", "fuzz", "rotation", "backup"}


def test_a_defender_watch_counts_attackers_that_get_through(tmp_path):
    w = ops.WATCHES[1]
    assert w["finding"] == "S0-3" and w["role"] == "defender"
    D = w["bot"]
    (tmp_path / "breaches.json").write_text(json.dumps({"seeds": 10, "breaches": {
        "a_weak": {D: 0, "x": 5}, "a_strong": {D: 3, "x": 9}}}))
    (tmp_path / "leaderboard.json").write_text(json.dumps({
        "attackers": [], "defenders": [{"name": D, "win_rate": 0.91}]}))
    row = ops.watch_row(tmp_path, "2026-10-05", w)
    assert row["per"] == {"a_weak": 1.0, "a_strong": 0.7}       # it holds a_strong 7/10
    assert row["under"] == ["a_strong"] and row["overall"] == 0.91
    text = ops.watch_text([row], w)
    assert "S0-3" in text and "any attacker hold it" in text and "Verdict: a meta" in text


def test_update_watch_writes_every_watch(tmp_path):
    D = ops.WATCHES[1]["bot"]
    (tmp_path / "breaches.json").write_text(json.dumps({"seeds": 10, "breaches": {
        ops.WATCH_BOT: {D: 4}, "a2": {D: 0}}}))
    (tmp_path / "leaderboard.json").write_text(json.dumps({
        "attackers": [{"name": ops.WATCH_BOT, "win_rate": 0.83}],
        "defenders": [{"name": D, "win_rate": 0.91}]}))
    ops.update_watch(tmp_path, "2026-10-05")
    assert (tmp_path / "WATCH.md").exists() and (tmp_path / "WATCH_S0-3.md").exists()
    assert (tmp_path / "watch_s0-3.jsonl").exists()


def test_the_ablation_generation_stops_before_a_call_it_cannot_afford_and_resumes(tmp_path,
                                                                                 monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "abl", Path(__file__).resolve().parents[1] / "scripts" / "ablation_personas.py")
    abl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abl)
    calls = []
    monkeypatch.setattr(abl.hl, "call_model", lambda *a, **k: calls.append(1) or "no code")
    monkeypatch.setattr(abl, "slots", lambda night: ["attacker", "defender"])
    monkeypatch.setattr(abl, "evidence_dir", lambda night, scratch: tmp_path / "ev")
    monkeypatch.setattr(abl.hl, "gather_context", lambda *a, **k: {})
    monkeypatch.setattr(abl.hl, "build_prompt", lambda *a, **k: "x" * 7000)
    import pytest
    with pytest.raises(abl.OutOfBudget):
        abl.generate(["2026-09-29"], tmp_path, max_tokens=1000)
    assert calls == []                                           # nothing was spent
    (tmp_path / "generation.json").write_text(json.dumps(
        [{"night": "2026-09-29", "slot": 0, "role": "attacker", "status": "written"}]))
    log = abl.generate(["2026-09-29"], tmp_path, max_tokens=None)
    assert len(calls) == 1 and [r["slot"] for r in log] == [0, 1]   # slot 0 skipped


def test_the_season_report_step_writes_a_draft_until_night_28(tmp_path, monkeypatch):
    from colosseum import meta_report
    calls = []
    monkeypatch.setattr(meta_report, "season_nights", lambda n: [("d", [])] * 11)
    monkeypatch.setattr(meta_report, "load_nights", lambda out: [])
    monkeypatch.setattr(meta_report, "write_season",
                        lambda out, with_clip: calls.append(with_clip))
    assert ops.season_report_step(out=tmp_path, commit=False) == "written (11 of 28 nights)"
    monkeypatch.setattr(meta_report, "season_nights", lambda n: [("d", [])] * 28)
    ops.season_report_step(out=tmp_path, commit=False)
    assert calls == [False, True]                    # clips only for the finished report


# --- nightly republish, only ever against a local bare remote ------------------------

@pytest.fixture
def bare(tmp_path):
    import subprocess
    r = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(r)], check=True)
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("<!doctype html><title>t</title>")
    key = tmp_path / "dummy_key"          # arms the step; unused for a local remote
    key.write_text("")
    return r, key


def test_publish_is_not_armed_without_the_deploy_key(tmp_path):
    msg = ops.publish_step(out=tmp_path, remote=str(tmp_path / "nowhere.git"),
                           key=tmp_path / "missing")
    assert msg.startswith("not armed")


def test_publish_records_what_it_pushed_and_republishes_on_top(tmp_path, bare):
    import subprocess
    r, key = bare
    assert ops.publish_step(out=tmp_path, remote=str(r), key=key).startswith("published:")
    rec = json.loads((tmp_path / "publish.json").read_text())
    main = subprocess.run(["git", "-C", str(r), "rev-parse", "main"], capture_output=True,
                          text=True, check=True).stdout.strip()
    assert rec["main"] == main and "gh-pages" in rec
    assert ops.publish_step(out=tmp_path, remote=str(r), key=key).startswith("published:")


def test_publish_refuses_when_public_main_moved_without_us(tmp_path, bare):
    import subprocess
    r, key = bare
    ops.publish_step(out=tmp_path, remote=str(r), key=key)
    w = tmp_path / "w"                    # someone merges a commit on the public side
    subprocess.run(["git", "clone", "-q", "-b", "main", str(r), str(w)], check=True)
    (w / "x.txt").write_text("x")
    subprocess.run(["git", "-C", str(w), "add", "x.txt"], check=True)
    subprocess.run(["git", "-C", str(w), "-c", "user.name=a", "-c", "user.email=a@a",
                    "commit", "-q", "-m", "merged on github"], check=True)
    subprocess.run(["git", "-C", str(w), "push", "-q", "origin", "main"], check=True)
    moved = subprocess.run(["git", "-C", str(r), "rev-parse", "main"], capture_output=True,
                           text=True, check=True).stdout.strip()
    with pytest.raises(RuntimeError, match="not republishing"):
        ops.publish_step(out=tmp_path, remote=str(r), key=key)
    assert subprocess.run(["git", "-C", str(r), "rev-parse", "main"], capture_output=True,
                          text=True, check=True).stdout.strip() == moved


def test_a_site_over_budget_is_an_alert_but_the_other_steps_still_run(monkeypatch):
    from colosseum import library, meta_report, site
    calls = []
    for name in ("commit_results", "update_watch", "rotate", "season_report_step",
                 "backup", "record_phase", "nightly_fuzz", "publish_step"):
        monkeypatch.setattr(ops, name, lambda *a, _n=name, **k: calls.append(_n) or _n)
    monkeypatch.setattr(meta_report, "due_week", lambda *a, **k: None)
    monkeypatch.setattr(library, "build", lambda *a, **k: "lib")
    monkeypatch.setattr(site, "build", lambda *a, **k: {"site": "x"})
    monkeypatch.setattr(site, "bundle_bytes", lambda *a: site.SIZE_BUDGET + 1)
    monkeypatch.setattr(ops, "write_alert", lambda *a, **k: calls.append("ALERT"))
    problems, results = ops.after_night(commit=True)
    assert len(problems) == 1 and problems[0].startswith("site:") and "budget" in problems[0]
    assert "ALERT" in calls and "publish_step" in calls


def test_health_boundary_reports_a_clean_or_conflicting_next_season(tmp_path):
    import subprocess
    from colosseum import boundary
    r = tmp_path / "r"

    def g(*a):
        subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "master", str(r)], check=True)
    (r / "f.txt").write_text("base\n")
    g("add", "f.txt"); g("commit", "-q", "-m", "base")
    assert health.check_boundary(r) == (False, f"branch {boundary.NEXT_BRANCH} is missing")
    g("checkout", "-q", "-b", boundary.NEXT_BRANCH)
    (r / "f.txt").write_text("next season\n")
    g("commit", "-q", "-am", "next")
    g("checkout", "-q", "master")
    assert health.check_boundary(r)[0] is True
    (r / "f.txt").write_text("master moved\n")
    g("commit", "-q", "-am", "clash")
    ok, detail = health.check_boundary(r)
    assert not ok and "f.txt" in detail
    boundary.archive(r).mkdir(parents=True)
    assert health.check_boundary(r)[0] is True
