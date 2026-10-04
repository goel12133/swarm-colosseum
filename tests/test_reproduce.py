"""make reproduce: rebuilt results match the committed ones byte for byte, or it says so."""
import json
import subprocess
from pathlib import Path

from colosseum import ops
from colosseum import reproduce as R


def fake_tournament(content):
    def run(**kw):
        for f in R.FILES:
            (kw["out"] / f).write_text(content)
        assert kw["sandbox"] and kw["cache"] is False and kw["seeds"] == 10
    return run


def test_identical_results_reproduce(tmp_path, monkeypatch):
    for f in R.FILES:
        (tmp_path / f).write_text("same")
    monkeypatch.setattr(R, "run_tournament", fake_tournament("same"))
    report, _ = R.reproduce(results=tmp_path)
    assert report == {f: True for f in R.FILES}


def test_a_changed_byte_is_caught(tmp_path, monkeypatch):
    for f in R.FILES:
        (tmp_path / f).write_text("same")
    monkeypatch.setattr(R, "run_tournament", fake_tournament("samE"))
    report, _ = R.reproduce(results=tmp_path)
    assert report == {f: False for f in R.FILES}


def test_the_night_commits_results_and_new_house_bots_together(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    (repo / "bots" / "house").mkdir(parents=True)
    out.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
    (repo / "README").write_text("x")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "i"], check=True)
    for f in R.FILES:
        (out / f).write_text(json.dumps({"f": f}))
    (repo / "bots" / "house" / "2026-10-04_attacker_x.py").write_text("NAME='x'\n")
    paths = ops.commit_results(repo, out, when="2026-10-04")
    assert "bots/house/2026-10-04_attacker_x.py" in paths
    log = subprocess.run(["git", "-C", str(repo), "show", "--stat", "--format=%s"],
                         capture_output=True, text=True).stdout
    assert "Night 2026-10-04: results and house bots" in log
    assert "results/leaderboard.json" in log and "2026-10-04_attacker_x.py" in log
    assert ops.commit_results(repo, out) == []          # nothing new: no empty commit
