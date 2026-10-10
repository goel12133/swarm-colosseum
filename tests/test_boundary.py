"""The scripted season boundary (post-launch, 2026-10-10), on a scratch clone of this repo.

The clone gets the working tree's boundary code committed into it and a fake next-season
branch; the real `season2` branch and the real master are never touched.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from colosseum import boundary, season

ROOT = Path(__file__).resolve().parents[1]
LEAGUE = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    live, out = tmp_path / "live", tmp_path / "out"
    subprocess.run(["git", "clone", "-q", "-b", "master", str(ROOT), str(live)], check=True)
    for rel in ("colosseum/boundary.py", "colosseum/ops.py", "colosseum/season.py",
                "colosseum/meta_report.py"):
        shutil.copy2(ROOT / rel, live / rel)
    git(live, "add", "-A")
    git(live, *LEAGUE, "commit", "-q", "--allow-empty", "-m", "test: current code")
    # the next season's branch: one rules-shaped change, as season2 will carry
    git(live, "checkout", "-q", "-b", boundary.NEXT_BRANCH)
    (live / "NEXT_SEASON.txt").write_text("season two rules\n")
    git(live, "add", "NEXT_SEASON.txt")
    git(live, *LEAGUE, "commit", "-q", "-m", "next season")
    git(live, "checkout", "-q", "master")
    (out / "meta").mkdir(parents=True)
    (out / "leaderboard.json").write_text('{"attackers": [], "defenders": []}')
    (out / "matrix.json").write_text('{"matrix": {}}')
    (out / "meta" / "WEEK_1.md").write_text("# Week 1\n")
    return live, out


def run(live, out, verify=lambda root: True):
    return boundary.run(root=live, out=out, verify=verify, season_report=lambda: None)


def test_due_only_from_the_first_night_of_the_next_season(tmp_path):
    assert not boundary.due(tmp_path, season.LAST_NIGHT)
    assert boundary.due(tmp_path, season.ENDS)
    (tmp_path / "seasons" / f"S{season.NUMBER}").mkdir(parents=True)
    assert not boundary.due(tmp_path, season.ENDS)                 # already done


def test_the_season_is_frozen_and_the_next_one_merged(world):
    live, out = world
    before = git(live, "rev-parse", "master")
    msg = run(live, out)
    assert msg.startswith(f"season {season.NUMBER} frozen")
    s = live / "seasons" / f"S{season.NUMBER}"
    for rel in ("leaderboard.json", "matrix.json", "BALANCE.md", "SEASON.md",
                "SEASON_REPORT.md", "meta/WEEK_1.md"):
        assert (s / rel).exists(), rel
    assert (s / "SEASON_REPORT.md").read_text() == \
        (live / "reports" / f"SEASON_{season.NUMBER}.md").read_text()
    house = sorted((live / "bots" / "house").glob("*.py"))
    assert house and all((s / "bots" / "house" / p.name).exists() for p in house)
    assert (live / "NEXT_SEASON.txt").exists()                      # the next season merged
    git(live, "merge-base", "--is-ancestor", before, "master")
    git(live, "merge-base", "--is-ancestor", boundary.NEXT_BRANCH, "master")
    assert git(live, "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert not git(live, "branch", "--list", "boundary-*")
    assert not git(live, "status", "--porcelain")


def test_a_conflict_leaves_master_alone(world):
    live, out = world
    (live / "NEXT_SEASON.txt").write_text("master wrote this first\n")
    git(live, "add", "NEXT_SEASON.txt")
    git(live, *LEAGUE, "commit", "-q", "-m", "a clash")
    master = git(live, "rev-parse", "master")
    with pytest.raises(RuntimeError, match="conflicted"):
        run(live, out)
    assert git(live, "rev-parse", "master") == master
    assert git(live, "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert not (live / "seasons").exists()


def test_a_red_suite_leaves_master_alone(world):
    live, out = world
    master = git(live, "rev-parse", "master")
    with pytest.raises(RuntimeError, match="suite is red"):
        run(live, out, verify=lambda root: False)
    assert git(live, "rev-parse", "master") == master
    assert git(live, "rev-parse", "--abbrev-ref", "HEAD") == "master"


def test_a_dirty_tree_or_a_missing_branch_is_not_ready(world):
    live, out = world
    (live / "stray.txt").write_text("x")
    with pytest.raises(boundary.NotReady, match="uncommitted"):
        run(live, out)
    (live / "stray.txt").unlink()
    git(live, "branch", "-q", "-D", boundary.NEXT_BRANCH)
    with pytest.raises(boundary.NotReady, match="does not exist"):
        run(live, out)


def test_nightly_runs_the_boundary_before_the_league_and_skips_it_on_failure():
    text = (ROOT / "scripts" / "nightly.sh").read_text()
    assert text.index("colosseum.boundary --if-due") < text.index("colosseum.house_league --once")
    assert "exit 1" in text[text.index("colosseum.boundary"):text.index("colosseum.house_league")]
