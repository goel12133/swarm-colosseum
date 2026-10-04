"""Content check: generated bots in game terms only; a hit is rejected, logged CONTENT:."""
import glob
import json
from pathlib import Path

from colosseum import content_check as cc
from colosseum import house_league as hl

ROOT = Path(__file__).resolve().parents[1]


def test_game_terms_pass_and_real_world_vocabulary_is_caught():
    assert cc.check('"""Idea: strikers wait outside radar range, then arrive together."""\n')[0]
    for text in ('"""Idea: a missile screen."""', "# the army would do this",
                 "NOTE = 'see model XY-300'", '"""On the battlefield"""'):
        ok, why = cc.check(text)
        assert not ok and "real-world reference" in why, text
    assert not cc.check("x = 1", meta={"note": "nuclear"})[0]          # metadata too


def test_no_existing_bot_or_kit_file_is_a_false_positive():
    files = glob.glob(str(ROOT / "bots" / "*" / "*.py")) + \
        glob.glob(str(ROOT / "workshop" / "**" / "*.py"), recursive=True)
    flagged = [f for f in files if not cc.check(Path(f).read_text())[0]]
    assert flagged == []
    assert cc.check("text.encode('UTF-8')")[0]                         # not a designation


def test_a_flagged_bot_is_rejected_logged_and_the_night_continues(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for f in ("leaderboard.json", "matrix.json", "BALANCE.md"):
        (out / f).write_text((hl.DEFAULT_OUT / f).read_text())
    for name, val in [("HOUSE", tmp_path / "house"), ("RAW", tmp_path / "raw"),
                      ("HISTORY", tmp_path / "history.json"), ("LOG", tmp_path / "log"),
                      ("NIGHTS", tmp_path / "nights.jsonl"), ("ALERT", tmp_path / "A.md")]:
        monkeypatch.setattr(hl, name, val)
    monkeypatch.setattr(hl, "smoke_test", lambda path, role: (True, "ok"))
    flagged = ('```python\n"""Idea: a warhead screen."""\nNAME = "bad_one"\nROLE = "attacker"\n'
               'def act(obs):\n    return {"launch": [], "steer": {}}\n```')
    clean = ('```python\n"""Idea: hold, then commit."""\nNAME = "good_one"\nROLE = "defender"\n'
             'def act(obs):\n    return {"intercept": [], "retarget": {}, "gun": None}\n```')
    monkeypatch.setattr(hl, "call_model",
                        lambda prompt, *a, **k: flagged if "an attacker" in prompt else clean)
    monkeypatch.setattr(hl, "run_tournament", lambda **kw: (_ for _ in ()).throw(
        RuntimeError("stop here")))
    hl.run_night(caps=hl.Caps(), out=out)
    names = [p.name for p in (tmp_path / "house").glob("*.py")]
    assert names and all("good_one" in n for n in names)               # flagged one never written
    log = (tmp_path / "log").read_text()
    assert "CONTENT: rejected attacker" in log and "warhead" in log
