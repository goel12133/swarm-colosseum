"""Daily engineering session wrapper: refusals, merges only when green, never discards."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from colosseum import daily

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A small repo shaped like ours: allow-list + sha, charter, backlog, daily, out/."""
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "bots" / "house").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "daily_allowlist.txt", r / "scripts")
    shutil.copy(ROOT / "scripts" / "daily_allowlist.sha256", r / "scripts")
    for f, text in (("CHARTER.md", "charter"), ("BACKLOG.md", "| 3.7 | library | todo |"),
                    ("DAILY.md", "yesterday"), ("PROGRESS.md", "progress\n"),
                    (".gitignore", "out/\n")):
        (r / f).write_text(text)
    git(tmp_path, "init", "-q", "-b", "master", str(r))
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    (r / "out").mkdir()
    return r


SCENARIOS = {
    # what the fake session does inside the worktree
    "commit": "echo work > feature.txt && git add feature.txt && "
              "git -c user.name=s -c user.email=s@s commit -q -m feature && "
              "echo 'today: did the feature' > DAILY.md && git add DAILY.md && "
              "git -c user.name=s -c user.email=s@s commit -q -m daily",
    "wip": "echo half > half.txt && echo 'state: halfway' > WIP.md && git add -A && "
           "git -c user.name=s -c user.email=s@s commit -q -m wip",
    "dirty": "echo forgot > forgot.txt",
    "nothing": "true",
}


def fake_claude(tmp_path, scenario, tokens=1234):
    script = tmp_path / f"fake_claude_{scenario}.sh"
    result = json.dumps({"type": "result", "usage": {"input_tokens": tokens,
                                                     "output_tokens": 0}})
    script.write_text(f"#!/bin/sh\ncat > /dev/null\n{SCENARIOS[scenario]}\n"
                      f"echo '{result}'\n")
    script.chmod(0o755)
    return str(script)


def day(repo, tmp_path, scenario, test_cmd="true", tokens=1234):
    return daily.run_day(root=repo, wt=tmp_path / "wt", out=repo / "out",
                         binary=fake_claude(tmp_path, scenario, tokens), test_cmd=test_cmd,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})


def test_refuses_when_the_allowlist_changed_since_it_was_approved(repo, tmp_path):
    with open(repo / "scripts" / "daily_allowlist.txt", "a") as f:
        f.write("Bash(docker *)\n")
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "refused" and "changed since it was approved" in rec["detail"]
    assert not (tmp_path / "wt").exists()
    assert "daily session" in (repo / "out" / "ALERT.md").read_text()


def test_the_real_allowlist_matches_its_approved_sha_and_has_no_raw_docker():
    daily.check_allowlist(ROOT)
    tools = daily.allowed_tools(ROOT)
    assert not any("docker" in t for t in tools)
    assert not any(t.startswith(("Bash(git push", "Bash(git checkout", "Bash(git reset",
                                 "Bash(git rebase", "Bash(git merge", "Bash(crontab",
                                 "Bash(python3 -c", "Bash(sudo")) for t in tools)
    assert "--restricted" in daily.session_command("claude", ROOT)
    assert "dontAsk" in daily.session_command("claude", ROOT)


def test_refuses_after_a_session_over_the_token_cap(repo, tmp_path):
    rec = day(repo, tmp_path, "nothing", tokens=daily.TOKEN_CAP + 1)
    assert rec["tokens"] == daily.TOKEN_CAP + 1
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "refused" and "over the" in rec["detail"]


def test_green_work_is_fast_forwarded_onto_master_and_daily_is_published(repo, tmp_path):
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "merged", rec
    assert (repo / "feature.txt").exists()
    assert (repo / "DAILY.md").read_text().strip() == "today: did the feature"
    assert git(repo, "branch", "--show-current").strip() == "master"


def test_red_tests_never_reach_master(repo, tmp_path):
    rec = day(repo, tmp_path, "commit", test_cmd="echo '1 failed' && false")
    assert rec["status"] == "red" and "1 failed" in rec["detail"]
    assert not (repo / "feature.txt").exists()
    assert git(repo, "rev-list", "--count", "master..daily-wip").strip() == "2"
    assert (repo / "out" / "ALERT.md").exists()


def test_wip_waits_and_is_continued_the_next_day(repo, tmp_path):
    rec = day(repo, tmp_path, "wip")
    assert rec["status"] == "wip" and not (repo / "half.txt").exists()
    rec = day(repo, tmp_path, "nothing")
    assert rec["branch"] == "continued"
    assert (tmp_path / "wt" / "half.txt").exists()


def test_uncommitted_leftovers_block_the_merge_and_are_never_discarded(repo, tmp_path):
    rec = day(repo, tmp_path, "dirty")
    assert rec["status"] == "dirty"
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "refused" and "uncommitted changes" in rec["detail"]
    assert (tmp_path / "wt" / "forgot.txt").exists()          # still there for review


def test_new_house_bots_are_committed_on_master_first(repo, tmp_path):
    (repo / "bots" / "house" / "2026-10-04_attacker_x.py").write_text("NAME='x'\n")
    rec = day(repo, tmp_path, "nothing")
    assert rec["house_bots_committed"] == ["bots/house/2026-10-04_attacker_x.py"]
    assert "House bots" in git(repo, "log", "--format=%s", "-3")


def test_a_second_session_cannot_start_while_one_holds_the_lock(repo, tmp_path):
    (repo / "out" / "daily").mkdir(parents=True)
    (repo / "out" / "daily" / "lock").write_text("123")
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "refused" and "holds" in rec["detail"]


def test_the_prompt_forbids_attribution_trailers(repo, tmp_path):
    prompt = daily.build_prompt(repo, tmp_path / "wt", repo / "out")
    assert "no Co-Authored-By" in prompt and "WIP.md" in prompt
