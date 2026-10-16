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
    # what the fake session does inside the worktree, then which verdict its reviewer gives
    "commit": ('echo work > feature.txt && git add feature.txt && git -c user.name=s -c user.email=s@s commit -q -m feature', "PASS"),
    "blocked": ('echo work > feature.txt && git add feature.txt && git -c user.name=s -c user.email=s@s commit -q -m feature', "BLOCK: does more than the action"),
    "unreviewed": ('echo work > feature.txt && git add feature.txt && git -c user.name=s -c user.email=s@s commit -q -m feature', None),
    "wip": ("echo half > half.txt && echo 'state: halfway' > WIP.md && git add -A && "
            "git -c user.name=s -c user.email=s@s commit -q -m wip", "PASS"),
    "dirty": ("echo forgot > forgot.txt", None),
    "nothing": ("true", None),
    "protected": ("mkdir -p scripts && echo x >> scripts/publish.sh && git add scripts/publish.sh && "
                  "git -c user.name=s -c user.email=s@s commit -q -m p", "PASS"),
    "dotclaude": ("mkdir -p .claude && echo '{}' > .claude/settings.json && git add .claude && "
                  "git -c user.name=s -c user.email=s@s commit -q -m c", "PASS"),
    "lesson": ("printf -- '- a new lesson\\n' >> CLAUDE.md && git add CLAUDE.md && "
               "git -c user.name=s -c user.email=s@s commit -q -m lesson", "PASS"),
    "rewrite_rules": ("sed -i 's/Rule one/Rule ONE/' CLAUDE.md && git add CLAUDE.md && "
                      "git -c user.name=s -c user.email=s@s commit -q -m rules", "PASS"),
}


def transcript_lines(verdict, tokens):
    """stream-json the way claude -p writes it: the architect's and reviewer's Agent calls."""
    lines = [{"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "a1", "name": "Agent",
                 "input": {"subagent_type": "architect", "prompt": "plan"}}]}},
             {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "a1",
                 "content": [{"type": "text", "text": "SIGNAL: 5, nights run\nACTION: x"}]}]}}]
    if verdict:
        lines += [{"type": "assistant", "message": {"content": [
                     {"type": "tool_use", "id": "r1", "name": "Agent",
                      "input": {"subagent_type": "reviewer", "prompt": "review"}}]}},
                  {"type": "user", "message": {"content": [
                     {"type": "tool_result", "tool_use_id": "r1",
                      "content": [{"type": "text", "text": verdict + "\nreasons"}]}]}}]
    lines.append({"type": "result", "usage": {"input_tokens": tokens, "output_tokens": 0}})
    return lines


def fake_claude(tmp_path, scenario, tokens=1234):
    script = tmp_path / f"fake_claude_{scenario}.sh"
    action, verdict = SCENARIOS[scenario]
    out = "\n".join("echo " + repr(json.dumps(l)) for l in transcript_lines(verdict, tokens))
    script.write_text(f"#!/bin/sh\ncat > /dev/null\n{action}\n{out}\n")
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


def test_reviewed_green_work_is_fast_forwarded_and_daily_says_what_happened(repo, tmp_path):
    rec = day(repo, tmp_path, "commit")
    assert rec["status"] == "merged", rec
    assert rec["verdict"] == "PASS" and rec["signal"] == "5, nights run"
    assert (repo / "feature.txt").exists()
    text = (repo / "DAILY.md").read_text()
    assert "merged" in text and "5, nights run" in text and "feature" in text
    assert git(repo, "branch", "--show-current").strip() == "master"


def test_red_tests_never_reach_master(repo, tmp_path):
    rec = day(repo, tmp_path, "commit", test_cmd="echo '1 failed' && false")
    assert rec["status"] == "red" and "1 failed" in rec["detail"]
    assert not (repo / "feature.txt").exists()
    assert git(repo, "rev-list", "--count", "master..daily-wip").strip() == "1"
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


def test_nothing_merges_without_the_reviewers_pass(repo, tmp_path):
    rec = day(repo, tmp_path, "blocked")
    assert rec["status"] == "blocked" and not (repo / "feature.txt").exists()
    rec = day(repo, tmp_path, "unreviewed")
    assert rec["status"] == "unreviewed" and (repo / "out" / "ALERT.md").exists()
    assert not (repo / "feature.txt").exists()


def test_the_verdict_is_read_from_the_reviewer_agent_not_from_files(tmp_path):
    t = tmp_path / "t.jsonl"
    lines = transcript_lines("PASS", 1)
    lines[2]["message"]["content"][0]["input"]["subagent_type"] = "builder"   # not the reviewer
    t.write_text("\n".join(json.dumps(l) for l in lines))
    assert daily.reviewer_verdict(t) is None
    t.write_text("\n".join(json.dumps(l) for l in transcript_lines("BLOCK: x", 1)))
    assert daily.reviewer_verdict(t) == "BLOCK"


def test_a_session_that_touches_a_protected_file_is_never_merged(repo, tmp_path):
    rec = day(repo, tmp_path, "protected")
    assert rec["status"] == "protected" and "scripts/publish.sh" in rec["detail"]
    assert not (repo / "scripts" / "publish.sh").exists()
    assert (repo / "out" / "ALERT.md").exists()


def test_the_loops_own_setup_is_protected(repo, tmp_path):
    rec = day(repo, tmp_path, "dotclaude")
    assert rec["status"] == "protected" and ".claude/settings.json" in rec["detail"]
    for path in (".claude/", "scripts/cron_install.sh", "scripts/fmt.py", "scripts/stop_check.sh",
                 "scripts/publish.sh", "colosseum/daily.py", "colosseum/rules.py"):
        assert path in daily.PROTECTED, path


def test_claude_md_may_only_grow_by_lessons(repo, tmp_path):
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\n\nRule one.\n\n## Lessons\n\n- old lesson\n")
    git(repo, "add", "CLAUDE.md")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "claude")
    rec = day(repo, tmp_path, "lesson")
    assert rec["status"] == "merged", rec
    assert "- a new lesson" in (repo / "CLAUDE.md").read_text()
    rec = day(repo, tmp_path, "rewrite_rules")
    assert rec["status"] == "claude-md" and "Rule one." in (repo / "CLAUDE.md").read_text()


def test_the_session_gets_only_the_founders_prompt_inside_the_ralph_loop():
    assert daily.PROMPT == ("Read CLAUDE.md. Look at the repository, the git log, the live site "
                            "and last night\u2019s league log as if for the first time. Do the "
                            "single most valuable thing for the goal, or nothing. Commit. Exit "
                            "without asking anything.")
    text = daily.session_input()
    assert text.startswith('/ralph-loop "' + daily.PROMPT + '"')
    assert f"--max-iterations {daily.RALPH_ITERATIONS}" in text


def test_the_session_is_fresh_project_scoped_and_has_no_mcp():
    cmd = daily.session_command("claude", ROOT)
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--no-session-persistence" in cmd and "--strict-mcp-config" in cmd
    assert "--mcp-config" not in cmd and "--dangerously-skip-permissions" not in cmd
    assert "Agent" in cmd[cmd.index("--tools") + 1]
    assert "Agent" in daily.allowed_tools(ROOT)


def test_the_architect_gets_its_context_written_first(repo, tmp_path):
    day(repo, tmp_path, "nothing")
    ctx = (tmp_path / "wt" / ".loop" / "context.md").read_text()
    for section in ("git log", "health", "last night's league log", "the live site's home page",
                    "FOUNDER_TODO.md"):
        assert f"## {section}" in ctx, section


def test_the_snapshot_carries_p5s_gate_but_not_the_ablation_evidence(tmp_path):
    """Regression (2026-10-13): out/ablation_14/done was never copied, so P5 could not open."""
    src, dest = tmp_path / "out", tmp_path / "snap"
    (src / "ablation_14" / "evidence").mkdir(parents=True)
    (src / "ablation_14" / "done").write_text("2026-10-15\n")
    (src / "ablation_14" / "evidence" / "big.json").write_text("{}")
    daily.copy_out(src, dest)
    assert (dest / "ablation_14" / "done").read_text() == "2026-10-15\n"
    assert not (dest / "ablation_14" / "evidence").exists()
    daily.copy_out(src, dest)                      # a second copy replaces, doesn't fail
    assert (dest / "ablation_14" / "done").exists()
