"""Engine tests. Each one pins a rule from the brief that a bot could otherwise cheat."""
import json
import math
from pathlib import Path

import pytest

from colosseum.policy import load_policy
from colosseum.rules import SEASON0
from colosseum.sim import Match, replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "bots" / "attackers"
D = ROOT / "bots" / "defenders"
F = ROOT / "tests" / "fixtures"


# --- determinism ------------------------------------------------------------

@pytest.mark.parametrize("attacker,defender,seed", [
    ("rush", "nearest_first", 0),
    ("flanker", "layered", 3),
    ("trickle", "identify_then_engage", 7),
])
def test_same_inputs_give_byte_identical_replays(attacker, defender, seed):
    a, b = (replay_json(run_match(A / f"{attacker}.py", D / f"{defender}.py", seed))
            for _ in range(2))
    assert a == b


def test_different_seeds_give_different_replays():
    """Determinism must not be the trivial kind where the seed is ignored."""
    a = replay_json(run_match(A / "trickle.py", D / "layered.py", 1))
    b = replay_json(run_match(A / "trickle.py", D / "layered.py", 2))
    assert a != b


def test_no_state_leaks_between_matches():
    """A fresh module instance per match: running another match in between changes nothing."""
    first = replay_json(run_match(A / "trickle.py", D / "layered.py", 5))
    run_match(A / "rush.py", D / "gun_only.py", 99)
    again = replay_json(run_match(A / "trickle.py", D / "layered.py", 5))
    assert first == again


# --- resource limits --------------------------------------------------------

def test_attacker_cannot_overspend_its_budget():
    r = run_match(A / "rush.py", F / "idle_def.py", 0)["meta"]
    spent = (r["drones_launched"]["striker"] * SEASON0.striker_cost
             + r["drones_launched"]["decoy"] * SEASON0.decoy_cost)
    assert spent <= SEASON0.attacker_budget + 1e-9
    assert r["budget_left"] >= -1e-9


def test_launch_rate_is_capped_and_the_excess_is_counted():
    """The garbage bot asks for 8 launches a tick against a cap of 4."""
    res = run_match(F / "garbage.py", F / "idle_def.py", 0)
    meta = res["meta"]
    launched = sum(meta["drones_launched"].values())
    assert launched <= SEASON0.attacker_launches_per_tick * meta["ticks"]
    assert meta["attacker_errors"]["invalid_actions"] > 0
    assert meta["attacker_errors"]["policy_errors"] == 0


def test_interceptor_stock_and_launch_rate_are_capped():
    res = run_match(A / "rush.py", F / "spam_intercept.py", 0)
    meta = res["meta"]
    assert meta["interceptors_launched"] <= SEASON0.interceptor_stock
    assert meta["stock_left"] >= 0
    assert meta["defender_errors"]["invalid_actions"] > 0


def test_ammo_is_capped():
    res = run_match(A / "trickle.py", D / "gun_only.py", 0)["meta"]
    assert res["shots_fired"] <= SEASON0.gun_ammo
    assert res["ammo_left"] == SEASON0.gun_ammo - res["shots_fired"]


# --- sensing ----------------------------------------------------------------

def test_identity_is_masked_outside_the_id_range():
    """cls is 'unknown' beyond 150 u, and never a lie inside it."""
    attacker = load_policy(A / "multi_axis.py", "attacker")
    defender = load_policy(F / "idle_def.py", "defender")
    m = Match(attacker, defender, seed=0)
    seen_unknown = seen_known = 0
    for _ in range(200):
        m.tick += 1
        m._apply_attacker(attacker.act(m._attacker_obs()))
        obs = m._defender_obs()
        for t in obs["tracks"]:
            true_range = math.hypot(m.drones[t["id"]].x, m.drones[t["id"]].y)
            if true_range > SEASON0.id_range:
                assert t["cls"] == "unknown"
                seen_unknown += 1
            else:
                assert t["cls"] == m.drones[t["id"]].type
                seen_known += 1
        m._move_drones()
    assert seen_unknown > 0 and seen_known > 0


def test_tracks_are_noisy_but_only_within_radar_range():
    attacker = load_policy(A / "rush.py", "attacker")
    defender = load_policy(F / "idle_def.py", "defender")
    m = Match(attacker, defender, seed=0)
    for _ in range(30):
        m.tick += 1
        m._apply_attacker(attacker.act(m._attacker_obs()))
        obs = m._defender_obs()
        for t in obs["tracks"]:
            d = m.drones[t["id"]]
            assert math.hypot(d.x, d.y) <= SEASON0.radar_range
            assert [t["pos"][0], t["pos"][1]] != [d.x, d.y]      # noise was applied
        m._move_drones()


# --- weapons ----------------------------------------------------------------

def test_blast_kills_several_clumped_drones():
    """With pk forced to 1, one interceptor reaching a clump should take more than one."""
    rules = SEASON0.tuned(interceptor_kill_prob=1.0, gun_ammo=0)
    res = run_match(F / "clump.py", D / "nearest_first.py", 0, rules=rules)
    meta = res["meta"]
    blasts = [e for e in res["events"] if e["kind"] == "blast"]
    assert blasts, "no interceptor ever reached a target"
    kills_by_blast = [e for e in res["events"] if e["kind"] == "kill" and e["by"] == "interceptor"]
    assert meta["shots_fired"] == 0
    assert len(kills_by_blast) > len(blasts), (
        f"{len(kills_by_blast)} kills from {len(blasts)} blasts: clumping was not punished")


def test_striker_impact_costs_ten_hp_and_a_decoy_costs_nothing():
    quiet = SEASON0.tuned(interceptor_stock=0, gun_ammo=0)
    striker = run_match(F / "one_striker.py", F / "idle_def.py", 0, rules=quiet)["meta"]
    decoy = run_match(F / "one_decoy.py", F / "idle_def.py", 0, rules=quiet)["meta"]
    assert striker["asset_hp"] == SEASON0.asset_hp - SEASON0.striker_damage
    assert striker["drones_impacted"]["striker"] == 1
    assert decoy["asset_hp"] == SEASON0.asset_hp
    assert decoy["drones_impacted"]["decoy"] == 1


def test_drones_that_reach_the_asset_are_not_counted_as_value_destroyed():
    quiet = SEASON0.tuned(interceptor_stock=0, gun_ammo=0)
    meta = run_match(F / "one_striker.py", F / "idle_def.py", 0, rules=quiet)["meta"]
    assert meta["drones_impacted"]["striker"] == 1
    assert meta["value_destroyed"] == 0.0


# --- robustness -------------------------------------------------------------

def test_a_bot_that_always_raises_does_not_crash_the_match():
    res = run_match(F / "raiser.py", D / "layered.py", 0)
    meta = res["meta"]
    assert meta["ticks"] > 0
    assert meta["attacker_errors"]["policy_errors"] > 0
    assert meta["outcome"] == "defended"          # it never launched anything


def test_both_bots_raising_still_produces_a_result():
    meta = run_match(F / "raiser.py", F / "raiser_def.py", 0)["meta"]
    assert meta["ticks"] == SEASON0.max_ticks
    assert meta["attacker_errors"]["policy_errors"] > 0
    assert meta["defender_errors"]["policy_errors"] > 0


# --- scoring ----------------------------------------------------------------

def test_scoring_matches_a_hand_computation():
    """Hand case: 5 interceptors and 10 shots spent, 12 credits destroyed, 20 HP left.

        defender_spent = 5*4 + 10*0.1               = 21.0
        cost_exchange_ratio = 12 / 21               = 0.571428...
        economy = 12 / (12 + 21)                    = 0.363636...
        score_defender = 0.6*(20/30) + 0.4*0.363636 = 0.4 + 0.145454 = 0.545454...
    """
    attacker = load_policy(F / "one_striker.py", "attacker")
    defender = load_policy(F / "idle_def.py", "defender")
    m = Match(attacker, defender, seed=0)
    m.interceptors_launched = 5
    m.shots_fired = 10
    m.value_destroyed = 12.0
    m.hp = 20
    s = m._score()
    assert s["defender_spent"] == pytest.approx(21.0)
    assert s["cost_exchange_ratio"] == pytest.approx(12 / 21, abs=1e-6)
    assert s["score_defender"] == pytest.approx(0.6 * (20 / 30) + 0.4 * (12 / 33), abs=1e-6)
    assert s["score_attacker"] == pytest.approx(1 - s["score_defender"], abs=1e-6)
    assert s["outcome"] == "defended"


def test_economy_term_is_a_half_when_nothing_was_spent_or_destroyed():
    attacker = load_policy(F / "one_striker.py", "attacker")
    defender = load_policy(F / "idle_def.py", "defender")
    m = Match(attacker, defender, seed=0)
    m.hp = SEASON0.asset_hp
    s = m._score()
    assert s["score_defender"] == pytest.approx(0.6 + 0.4 * 0.5)
    assert s["cost_exchange_ratio"] == 0.0


def test_breached_outcome_when_hp_reaches_zero():
    meta = run_match(A / "rush.py", F / "idle_def.py", 0)["meta"]
    assert meta["asset_hp"] == 0
    assert meta["outcome"] == "breached"
    assert meta["end_reason"] == "asset_destroyed"
