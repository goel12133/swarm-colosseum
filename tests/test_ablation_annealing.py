"""The optimiser ablation script (3.5) on a synthetic cache and history: nothing runs."""
import importlib.util
import json
import sqlite3
from pathlib import Path

from colosseum.cache import engine_version, rules_hash
from colosseum.rules import SEASON0

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ablation_annealing",
                                              ROOT / "scripts" / "ablation_annealing.py")
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


def make_out(tmp_path, scores, stale=False):
    """scores: {attacker: (opt, greedy)} for seeds 0-1; stale rows use an old engine."""
    (tmp_path / "cache").mkdir()
    db = sqlite3.connect(tmp_path / "cache" / "results.sqlite")
    db.execute("CREATE TABLE results (key TEXT PRIMARY KEY, attacker TEXT, defender TEXT, "
               "seed INTEGER, meta TEXT, replay TEXT)")
    tail = f"{rules_hash(SEASON0)}:{'old' if stale else engine_version()}"
    for att, pair in scores.items():
        for seed in (0, 1):
            for dfn, sc in zip((ab.OPT, ab.GREEDY), pair):
                meta = dict(score_defender=sc, cost_exchange_ratio=1.0, outcome="defended")
                db.execute("INSERT INTO results VALUES (?, ?, ?, ?, ?, ?)",
                           (f"a{att}:d{dfn}:{seed}:{tail}", att, dfn, seed,
                            json.dumps(meta), None))
    db.commit()
    db.close()
    night = tmp_path / "history" / "2026-10-09"
    night.mkdir(parents=True)
    night.joinpath("leaderboard.json").write_text(json.dumps({"defenders": [
        dict(name=ab.GREEDY, elo=1010, mean_score=0.6, mean_cer=1.0),
        dict(name="other", elo=1000, mean_score=0.5, mean_cer=1.0),
        dict(name=ab.OPT, elo=990, mean_score=0.55, mean_cer=0.9)]}))
    return tmp_path


def test_paired_differences_sign_test_and_ladder(tmp_path):
    res = ab.analyse(make_out(tmp_path, {"x": (0.8, 0.6), "y": (0.5, 0.5), "z": (0.2, 0.3)}))
    s = res["summary"]
    assert (s["attackers"], s["pairs"]) == (3, 6)
    assert (s["opt_ahead"], s["greedy_ahead"], s["level"]) == (1, 1, 1)
    assert s["mean_diff"] == round((0.2 + 0 - 0.1) / 3, 4) and s["sign_p"] == 1.0
    assert res["per_attacker"]["x"]["diff"] == 0.2
    assert res["nights"][0][ab.OPT]["rank"] == 3 and res["nights"][0][ab.GREEDY]["rank"] == 1
    assert ab.analyse(tmp_path) == res                     # deterministic, bootstrap included


def test_results_from_another_engine_version_are_ignored(tmp_path):
    assert ab.analyse(make_out(tmp_path, {"x": (0.8, 0.6)}, stale=True))["summary"]["pairs"] == 0


def test_the_exact_sign_test():
    assert ab.sign_test(8, 1) == 0.0391 and ab.sign_test(0, 0) == 1.0
