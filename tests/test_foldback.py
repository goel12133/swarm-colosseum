"""Fold-back of merged PRs (post-launch, 2026-10-10), only ever against a local bare remote.

The "live" repo is a scratch clone of this one with the working tree's publish scripts and
fold-back code committed into it; the "public" repo is a bare remote that the first publish
fills. A fake contributor commits a bot on a branch of the public repo and a fake founder
merges it with a merge commit, as GitHub's merge button does.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from colosseum import foldback, ops

ROOT = Path(__file__).resolve().parents[1]
LEAGUE = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]
BOT = ROOT / "workshop" / "solutions" / "ex1_closest_first.py"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    live, remote, out = tmp_path / "live", tmp_path / "public.git", tmp_path / "out"
    subprocess.run(["git", "clone", "-q", "-b", "master", str(ROOT), str(live)], check=True)
    for rel in ("scripts/publish.sh", "scripts/rewrite_identity.sh", "scripts/audit_secrets.py",
                "scripts/public_identity", "colosseum/foldback.py", "colosseum/ops.py"):
        shutil.copy2(ROOT / rel, live / rel)
    git(live, "add", "-A")
    git(live, *LEAGUE, "commit", "-q", "--allow-empty", "-m", "test: current scripts")
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    (out / "site").mkdir(parents=True)
    (out / "site" / "index.html").write_text("<!doctype html><title>t</title>")
    key = tmp_path / "dummy_key"
    key.write_text("")

    def fake_intake(root):
        """Stands in for submit_pr.intake (which plays a sandboxed test match): accept every
        PR bot by copying it where intake would put it."""
        results = []
        for p in sorted((root / "bots" / "submitted" / "pr").glob("*/*.py")):
            dest = root / "bots" / "submitted" / "defender" / f"{p.parent.name}__{p.name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
            results.append((p, {"status": "accepted"}))
        return results

    def publish(**kw):
        kw.setdefault("intake", fake_intake)
        return ops.publish_step(root=live, out=out, remote=str(remote), key=key, **kw)

    assert publish().startswith("published:")
    return dict(live=live, remote=remote, out=out, publish=publish, tmp=tmp_path)


def merge_pr(w, files: dict, branch="pr"):
    """A contributor's commit on a branch, merged into main with a merge commit."""
    c = w["tmp"] / f"contrib-{branch}"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(w["remote"]), str(c)], check=True)
    git(c, "checkout", "-q", "-b", branch)
    for rel, text in files.items():
        (c / rel).parent.mkdir(parents=True, exist_ok=True)
        (c / rel).write_text(text)
        git(c, "add", rel)
    git(c, "-c", "user.name=alice", "-c", "user.email=alice@example.invalid", "commit", "-q",
        "-m", "add my bot")
    git(c, "checkout", "-q", "main")
    git(c, "-c", "user.name=founder", "-c", "user.email=founder@example.invalid", "merge",
        "-q", "--no-ff", branch, "-m", f"Merge pull request #1 from alice/{branch}")
    git(c, "push", "-q", "origin", "main")
    return git(w["remote"], "rev-parse", "main")


def test_a_merged_bot_is_folded_into_master_and_main_keeps_growing(world):
    w = world
    rel = "bots/submitted/pr/alice/alice_closest.py"
    merged = merge_pr(w, {rel: BOT.read_text()})
    before = git(w["live"], "rev-parse", "master")
    msg = w["publish"](foldback_enabled=True, verify=lambda root: True)
    assert msg.startswith("folded 2 commit(s): " + rel) and "intake: 1 accepted" in msg, msg
    # master gained a fold-back commit carrying the file byte for byte, and an intake commit
    assert git(w["live"], "rev-list", "--count", f"{before}..master") == "2"
    assert (w["live"] / rel).read_text() == BOT.read_text()
    assert (w["live"] / "bots/submitted/defender/alice__alice_closest.py").exists()
    assert git(w["live"], "log", "-1", "--format=%s", "master").startswith("Intake: 1 accepted")
    assert git(w["live"], "log", "-2", "--format=%ae", "master").split() == ["league@localhost"] * 2
    assert not git(w["live"], "branch", "--list", "foldback-*")
    # public main still contains the merged PR, and its tree now equals master's (rewritten)
    main = git(w["remote"], "rev-parse", "main")
    git(w["remote"], "merge-base", "--is-ancestor", merged, main)
    assert git(w["remote"], "show", f"main:{rel}") == BOT.read_text().rstrip("\n")
    assert json.loads((w["out"] / "publish.json").read_text())["main"] == main
    # the next night (a new league commit) publishes onto main again, with no fold-back
    (w["live"] / "night.txt").write_text("night 2\n")
    git(w["live"], "add", "night.txt")
    git(w["live"], *LEAGUE, "commit", "-q", "-m", "Night 2")
    assert w["publish"]().startswith("published:")
    git(w["remote"], "merge-base", "--is-ancestor", main, "main")      # still only grows
    assert git(w["remote"], "show", "main:night.txt") == "night 2"


def test_a_commit_outside_the_submission_folder_is_rejected_and_nothing_applied(world):
    w = world
    merge_pr(w, {"bots/submitted/pr/alice/ok_bot.py": BOT.read_text(),
                 "colosseum/sim.py": "# changed\n"})
    master, main = git(w["live"], "rev-parse", "master"), git(w["remote"], "rev-parse", "main")
    with pytest.raises(RuntimeError, match="not republishing"):          # fold-back off
        w["publish"]()
    with pytest.raises(foldback.Rejected, match="colosseum/sim.py"):
        w["publish"](foldback_enabled=True, verify=lambda root: True)
    assert git(w["live"], "rev-parse", "master") == master
    assert git(w["live"], "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert not (w["live"] / "bots/submitted/pr/alice/ok_bot.py").exists()
    assert git(w["remote"], "rev-parse", "main") == main                 # nothing pushed


def test_failing_tests_leave_master_alone_and_keep_the_branch(world):
    w = world
    merge_pr(w, {"bots/submitted/pr/alice/alice_closest.py": BOT.read_text()})
    master, main = git(w["live"], "rev-parse", "master"), git(w["remote"], "rev-parse", "main")
    with pytest.raises(RuntimeError, match="tests failed"):
        w["publish"](foldback_enabled=True, verify=lambda root: False)
    assert git(w["live"], "rev-parse", "master") == master
    assert git(w["live"], "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert git(w["live"], "branch", "--list", "foldback-*")
    assert git(w["remote"], "rev-parse", "main") == main


@pytest.mark.parametrize("status,mode,path,ok", [
    ("A", "100644", "bots/submitted/pr/alice/x.py", True),
    ("D", "000000", "bots/submitted/pr/alice/x.py", True),
    ("A", "120000", "bots/submitted/pr/alice/x.py", False),           # symlink
    ("A", "100755", "bots/submitted/pr/alice/x.py", False),
    ("A", "100644", "bots/submitted/attacker/x.py", False),            # skips intake
    ("A", "100644", "bots/submitted/pr/alice/x.txt", False),
    ("A", "100644", "bots/submitted/pr/alice/deep/x.py", False),
    ("M", "100644", ".github/workflows/submission.yml", False),
])
def test_the_path_rule(status, mode, path, ok):
    assert foldback.allowed(status, mode, path) is ok


def test_fold_back_ships_switched_off():
    assert ops.FOLDBACK_ENABLED is False
