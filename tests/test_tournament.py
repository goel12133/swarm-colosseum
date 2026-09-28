"""Tournament and Elo tests."""
import json
from pathlib import Path

import pytest

from colosseum.elo import Ladders, expected, update
from colosseum.tournament import run_tournament

ROOT = Path(__file__).resolve().parents[1]


def test_elo_expected_is_symmetric_and_even_at_equal_ratings():
    assert expected(1000, 1000) == pytest.approx(0.5)
    assert expected(1200, 1000) + expected(1000, 1200) == pytest.approx(1.0)


def test_elo_update_is_zero_sum_and_moves_toward_the_result():
    a, b = update(1000, 1000, 1.0)
    assert a > 1000 > b
    assert (a - 1000) == pytest.approx(1000 - b)
    assert a == pytest.approx(1000 + 12.0)          # K=24, expected 0.5


def test_elo_uses_the_continuous_score():
    strong, _ = update(1000, 1000, 0.9)
    weak, _ = update(1000, 1000, 0.6)
    assert strong > weak > 1000


def test_ladders_keep_the_two_roles_separate():
    lad = Ladders(["a1"], ["d1", "d2"])
    lad.record("a1", "d1", 1.0)
    assert lad.attackers["a1"] > 1000
    assert lad.defenders["d1"] < 1000
    assert lad.defenders["d2"] == 1000


def test_tournament_smoke_with_two_seeds(tmp_path):
    lb, matrix, results = run_tournament(seeds=2, out=tmp_path, write_replays=True,
                                         quiet=True)
    n_attackers = len(lb["attackers"])
    n_defenders = len(lb["defenders"])
    assert len(results) == n_attackers * n_defenders * 2

    for name in ("leaderboard.json", "matrix.json", "BALANCE.md"):
        assert (tmp_path / name).exists(), f"{name} was not written"
    replays = list((tmp_path / "replays").glob("*.json"))
    assert len(replays) == len(results)

    body = json.loads((tmp_path / "leaderboard.json").read_text())
    assert {r["name"] for r in body["attackers"]} == set(matrix)
    for row in body["attackers"] + body["defenders"]:
        assert 0.0 <= row["mean_score"] <= 1.0
        assert 0.0 <= row["win_rate"] <= 1.0

    one = json.loads(replays[0].read_text())
    assert {"meta", "frames", "events"} <= set(one)
    assert one["meta"]["season"] == 0


def test_tournament_is_deterministic(tmp_path):
    """Same seeds, same ladder -- Elo is path dependent, so match order must be fixed."""
    first, _, _ = run_tournament(seeds=2, out=tmp_path / "a", write_replays=False,
                                 quiet=True)
    second, _, _ = run_tournament(seeds=2, out=tmp_path / "b", write_replays=False,
                                  quiet=True)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
