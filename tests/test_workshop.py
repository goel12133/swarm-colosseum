"""Workshop kit (3.11): every exercise solvable, starters unsolved, and the student wrapper
only ever loads the student's own file plus a baseline picked by name."""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from colosseum.submit import check_source

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "workshop"
sys.path.insert(0, str(W))


def _load(name):
    spec = importlib.util.spec_from_file_location(f"workshop_{name}", W / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kit = _load("kit")
check = _load("check")
play = _load("play")

STARTERS = sorted((W / "starters").rglob("*.py"))
SOLUTIONS = sorted((W / "solutions").glob("*.py"))


def test_make_workshop_passes(capsys):
    """What `make workshop` runs: each solution passes, each unedited starter does not."""
    assert check.main([]) == 0
    out = capsys.readouterr().out
    assert "all exercises solvable" in out
    assert out.count("ok   exercise") == len(kit.EXERCISES) == 5


def test_three_starters_per_side_each_with_one_todo():
    sides = [p.parent.name for p in STARTERS]
    assert sides.count("attackers") == 3 and sides.count("defenders") == 3
    for p in STARTERS:
        assert p.read_text().count("# TODO") == 1, p.name


@pytest.mark.parametrize("path", STARTERS + SOLUTIONS, ids=lambda p: p.name)
def test_bundled_bots_pass_the_arena_checks(path):
    src = path.read_text()
    side = "attacker" if 'ROLE = "attacker"' in src else "defender"
    check_source(src, side)


def test_exercises_point_at_real_files_and_opponents():
    for ex in kit.EXERCISES:
        assert (W / "starters" / ex.starter).is_file()
        assert (W / "solutions" / ex.solution).is_file()
        assert ex.want in ("breached", "defended")
        side = "attacker" if ex.starter.startswith("attackers/") else "defender"
        assert ex.vs in kit.OPPONENTS[kit.OTHER[side]]


def test_check_one_exercise(capsys):
    assert check.main(["3"]) == 1                                 # the unedited starter
    assert "Not yet" in capsys.readouterr().out
    assert check.main(["3", str(W / "solutions" / "ex3_look_before_firing.py")]) == 0
    assert "Solved!" in capsys.readouterr().out
    assert check.main(["9"]) == 2


def test_play_writes_an_offline_replay(tmp_path, capsys):
    out = tmp_path / "m.html"
    rc = play.main([str(W / "starters" / "attackers" / "straight_line.py"),
                    "--vs", "nearest_first", "--seed", "3", "--replay", str(out)])
    assert rc == 0
    html = out.read_text()
    assert "straight_line" in html and "__SAMPLE_REPLAY__" not in html
    assert "straight_line vs nearest_first, seed 3" in capsys.readouterr().out


def test_play_lists_opponents_without_vs(capsys):
    assert play.main([str(W / "starters" / "defenders" / "gun_line.py")]) == 2
    out = capsys.readouterr().out
    assert "rush" in out and "nearest_first" not in out


def test_same_match_twice_is_identical():
    bot = W / "solutions" / "ex5_many_sides.py"
    assert kit.play(bot, "layered", 2) == kit.play(bot, "layered", 2)


# --- what the wrapper refuses (inert inputs; nothing here is ever loaded) ----------

def _bot(tmp_path, body, name="mine.py"):
    p = tmp_path / name
    p.write_text('NAME = "mine"\nROLE = "attacker"\n' + body
                 + "\ndef act(obs):\n    return {}\n")
    return p


def test_refuses_a_league_bot():
    house = sorted((ROOT / "bots" / "house").glob("*.py"))[0]
    with pytest.raises(kit.NotAllowed, match="league bot"):
        kit.student_bot(house)


def test_refuses_what_the_arena_refuses(tmp_path):
    with pytest.raises(kit.NotAllowed, match="not allowed"):
        kit.student_bot(_bot(tmp_path, "import os\n"))
    with pytest.raises(kit.NotAllowed, match="not allowed"):
        kit.student_bot(_bot(tmp_path, "X = open\n"))


def test_refuses_odd_files(tmp_path):
    with pytest.raises(kit.NotAllowed, match="not a Python file"):
        kit.student_bot(tmp_path / "mine.txt")
    with pytest.raises(kit.NotAllowed, match="can find"):
        kit.student_bot(tmp_path / "missing.py")
    real = _bot(tmp_path, "")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    with pytest.raises(kit.NotAllowed, match="can find"):
        kit.student_bot(link)
    with pytest.raises(kit.NotAllowed, match="KB"):
        kit.student_bot(_bot(tmp_path, "# " + "x" * (70 * 1024) + "\n", "big.py"))
    no_role = tmp_path / "norole.py"
    no_role.write_text('NAME = "mine"\ndef act(obs):\n    return {}\n')
    with pytest.raises(kit.NotAllowed, match="ROLE"):
        kit.student_bot(no_role)


def test_opponent_by_name_only():
    with pytest.raises(kit.NotAllowed, match="no defender"):
        kit.opponent("../house/anything", "defender")
    with pytest.raises(kit.NotAllowed, match="no defender"):
        kit.opponent("rush", "defender")                     # wrong side
    assert kit.opponent("nearest_first", "defender").name == "nearest_first"


def test_workshop_code_imports_only_stdlib_and_the_engine():
    """It has to run on a school laptop with nothing installed."""
    allowed = {"argparse", "ast", "importlib", "sys", "dataclasses", "pathlib",
               "colosseum", "kit"}
    for p in sorted(W.rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module]
            else:
                continue
            for n in names:
                assert n.split(".")[0] in allowed, f"{p.name} imports {n}"
