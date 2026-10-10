"""Tournament and Elo tests."""
import json
from pathlib import Path

import pytest

from colosseum import rules

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
    assert one["meta"]["season"] == rules.SEASON


def test_tournament_is_deterministic(tmp_path):
    """Same seeds, same ladder -- Elo is path dependent, so match order must be fixed."""
    first, _, _ = run_tournament(seeds=2, out=tmp_path / "a", write_replays=False,
                                 quiet=True)
    second, _, _ = run_tournament(seeds=2, out=tmp_path / "b", write_replays=False,
                                  quiet=True)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# --- untrusted bots never run on the host ------------------------------------

TRAP = '''import pathlib
pathlib.Path({marker!r}).write_text("executed on the host")
NAME = "trap"
ROLE = "{role}"
def act(obs):
    return {{}}
'''


def test_untrusted_bots_never_load_in_process(tmp_path, monkeypatch):
    """Regression: test_tournament used to import house bots on the host (2026-09-28)."""
    from colosseum import policy, tournament
    house = tmp_path / "house"
    house.mkdir()
    marker = tmp_path / "executed"
    bot = house / "trap.py"
    bot.write_text(TRAP.format(marker=str(marker), role="attacker"))
    monkeypatch.setattr(policy, "UNTRUSTED_DIRS", [house])
    monkeypatch.setattr(tournament, "UNTRUSTED_FOLDERS", [house])

    with pytest.raises(policy.PolicyError, match="untrusted"):
        policy.load_policy(bot, "attacker")
    lb, _, _ = run_tournament(seeds=1, out=tmp_path / "out", write_replays=False,
                              quiet=True, sandbox=False, workers=1)
    assert "trap" not in {r["name"] for r in lb["attackers"]}
    assert not marker.exists()


def test_real_house_and_submitted_folders_are_untrusted():
    from colosseum import policy
    root = Path(__file__).resolve().parents[1]
    assert policy.is_untrusted(root / "bots" / "house" / "x.py")
    assert policy.is_untrusted(root / "bots" / "house" / "RETIRED" / "x.py")
    assert policy.is_untrusted(root / "bots" / "submitted" / "attacker" / "x.py")
    assert not policy.is_untrusted(root / "bots" / "defenders" / "layered.py")


def test_tournament_writes_breach_counts(tmp_path):
    run_tournament(seeds=2, out=tmp_path, write_replays=False, quiet=True)
    b = json.loads((tmp_path / "breaches.json").read_text())
    assert b["seeds"] == 2
    assert b["breaches"]["rush"]["gun_only"] == 2           # gun_only never stops rush
    assert all(0 <= n <= 2 for row in b["breaches"].values() for n in row.values())
