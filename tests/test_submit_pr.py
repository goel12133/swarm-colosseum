"""Submissions by pull request (L9): the CI check is static only, and intake goes through submit."""
import os
import re
from pathlib import Path

import pytest

from colosseum import submit_pr as pr
from colosseum.policy import is_untrusted
from colosseum.tournament import UNTRUSTED_FOLDERS

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "submission.yml"

BOT = '''"""Idea: a steady trickle from rotating bearings."""
NAME = "steady_three"
ROLE = "attacker"


def act(obs):
    if obs["tick"] % 6 or obs["budget"] < obs["rules"]["striker_cost"]:
        return {"launch": [], "steer": {}}
    return {"launch": [{"type": "striker", "bearing": (obs["tick"] * 40) % 360}], "steer": {}}
'''
DEF = BOT.replace('"steady_three"', '"calm_wall"').replace('"attacker"', '"defender"')


def put(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return rel


def run(root, changes, author="Ada"):
    return pr.check_pr(pr.parse_changes(changes), author, root=root)


def test_a_clean_bot_in_the_authors_folder_passes(tmp_path):
    rel = put(tmp_path, "bots/submitted/pr/ada/steady_three.py", BOT)
    ok, lines = run(tmp_path, f"A\t{rel}\n")
    assert ok, lines
    assert "attacker/steady_three" in lines[0]


def test_one_bot_per_side_is_fine_two_on_one_side_is_not(tmp_path):
    a = put(tmp_path, "bots/submitted/pr/ada/steady_three.py", BOT)
    d = put(tmp_path, "bots/submitted/pr/ada/calm_wall.py", DEF)
    assert run(tmp_path, f"A\t{a}\nM\t{d}\n")[0]
    b = put(tmp_path, "bots/submitted/pr/ada/other_one.py", BOT.replace("steady_three", "other_one"))
    ok, lines = run(tmp_path, f"A\t{a}\nA\t{b}\n")
    assert not ok and "one bot per side" in lines[-1]


@pytest.mark.parametrize("changes,reason", [
    ("A\tbots/submitted/pr/ada/steady_three.py\nM\tcolosseum/submit_pr.py\n", "only add files"),
    ("M\t.github/workflows/submission.yml\n", "only add files"),
    ("A\tbots/submitted/attacker/ada__steady_three.py\n", "only add files"),
    ("A\tbots/submitted/pr/bob/steady_three.py\n", "isn't yours"),
    ("A\tbots/submitted/pr/ada/wrong_name.py\n", "file name must be NAME"),
    ("A\tbots/submitted/pr/ada/sub/steady_three.py\n", "goes at"),
    ("D\tbots/submitted/pr/ada/steady_three.py\n", "only adding or updating"),
    ("", "changes no files"),
])
def test_changes_outside_the_authors_own_bot_are_refused(tmp_path, changes, reason):
    for rel in re.findall(r"\t(\S+)", changes):
        put(tmp_path, rel, BOT)
    ok, lines = run(tmp_path, changes)
    assert not ok
    assert any(reason in line for line in lines), lines


def test_too_many_files_and_unusable_logins_are_refused(tmp_path):
    many = "".join(f"A\tbots/submitted/pr/ada/b{i}.py\n" for i in range(3))
    assert "at most 2" in run(tmp_path, many)[1][0]
    for login in ("a", "x" * 30, "", "dependabot[bot]"):
        ok, lines = run(tmp_path, "A\tbots/submitted/pr/a/x.py\n", author=login)
        assert not ok and "handle rules" in lines[0]


def test_forbidden_code_and_real_world_terms_fail_with_the_submit_reasons(tmp_path):
    rel = put(tmp_path, "bots/submitted/pr/ada/steady_three.py", "import os\n" + BOT)
    ok, lines = run(tmp_path, f"A\t{rel}\n")
    assert not ok and "`import os` is not allowed" in lines[0]
    put(tmp_path, rel, BOT.replace("a steady trickle", "an artillery trickle"))
    ok, lines = run(tmp_path, f"M\t{rel}\n")
    assert not ok and "game terms only" in lines[0]


def test_a_symlink_is_refused(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text(BOT)
    link = tmp_path / "bots/submitted/pr/ada/steady_three.py"
    link.parent.mkdir(parents=True)
    os.symlink(secret, link)
    ok, lines = run(tmp_path, "A\tbots/submitted/pr/ada/steady_three.py\n")
    assert not ok and "plain file" in lines[0]


def test_the_check_never_executes_the_file(tmp_path):
    marker = tmp_path / "ran"
    src = BOT.replace("def act", f"X = open({str(marker)!r}, 'w')\n\n\ndef act")
    rel = put(tmp_path, "bots/submitted/pr/ada/steady_three.py", src)
    ok, _ = run(tmp_path, f"A\t{rel}\n")
    assert not ok and not marker.exists()


def test_pr_bots_are_untrusted_and_not_played_until_intake():
    assert is_untrusted(pr.PR_DIR / "ada" / "steady_three.py")
    assert all(not pr.PR_DIR.resolve().is_relative_to(f.resolve()) for f in UNTRUSTED_FOLDERS)


def test_intake_sends_each_merged_bot_through_submit(tmp_path):
    put(tmp_path, "ada/steady_three.py", BOT)
    put(tmp_path, "bob/calm_wall.py", DEF)
    put(tmp_path, "Bad Handle/x.py", BOT)
    calls = []

    def fake_submit(path, side, author):                   # stands in for the sandbox path
        calls.append((path.name, side, author))
        return dict(status="accepted", name=f"{author}__{path.stem}")

    results = pr.intake(tmp_path, submit_fn=fake_submit)
    assert calls == [("steady_three.py", "attacker", "ada"), ("calm_wall.py", "defender", "bob")]
    assert [r["status"] for _, r in results] == ["rejected", "accepted", "accepted"]


def test_the_workflow_is_read_only_static_and_injection_safe():
    text = WORKFLOW.read_text()
    assert re.search(r"^  pull_request:", text, re.M)
    assert "pull_request_target" not in text.replace("never `pull_request_target`", "")
    assert re.search(r"^permissions:\n  contents: read\n", text, re.M)
    assert "secrets." not in text and "persist-credentials: false" in text
    assert "docker" not in text.lower().replace("no docker", "")
    for line in text.splitlines():
        if line.strip().startswith("run:"):
            assert "${{" not in line, line                    # PR text only via env
    assert "python -m colosseum.submit_pr check" in text


def test_the_docs_describe_the_pull_request_path():
    doc = (ROOT / "SUBMITTING.md").read_text()
    assert "bots/submitted/pr/<your login>/<NAME>.py" in doc
    assert "colosseum.submit_pr" in (ROOT / "CONTRIBUTING.md").read_text()
