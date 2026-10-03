"""Engine fuzzing and invariants (3.9), and the sanitiser fix it found.

The fuzz policies live in colosseum/fuzz.py and are trusted code, so these run in-process.
The full 10,000-trajectory run was done once by hand (PROGRESS.md); the nightly run is 500;
this suite runs a small slice so it stays well under the five-minute budget.
"""
import json
import math
from pathlib import Path

import pytest

from colosseum import fuzz
from colosseum.policy import clean_attacker_action, clean_defender_action
from colosseum.rules import SEASON0
from colosseum.sandbox import SandboxLimits, docker_available
from colosseum.sim import Interceptor, replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "tests" / "fixtures"
D = ROOT / "bots" / "defenders"

NONFINITE = [float("nan"), float("inf"), float("-inf"), 10 ** 400, -10 ** 400]
NAMES = ["nan", "inf", "-inf", "big", "-big"]


# --- the sanitiser bug --------------------------------------------------------

@pytest.mark.parametrize("v", NONFINITE, ids=NAMES)
def test_a_non_finite_bearing_is_invalid_not_a_drone(v):
    launches, _, bad = clean_attacker_action({"launch": [{"type": "striker", "bearing": v}]},
                                             SEASON0)
    assert launches == [] and bad == 1


@pytest.mark.parametrize("v", NONFINITE, ids=NAMES)
def test_a_non_finite_waypoint_is_invalid(v):
    _, steer, bad = clean_attacker_action({"steer": {"1": [0.0, v], "2": [v, 0.0]}}, SEASON0)
    assert steer == {} and bad == 2


@pytest.mark.parametrize("v", NONFINITE + ["1e999", "NaN"],
                         ids=["nan", "inf", "-inf", "big", "-big", "s1e999", "sNaN"])
def test_non_finite_ids_are_invalid_and_never_raise(v):
    intercept, retarget, gun, bad = clean_defender_action(
        {"intercept": [v], "retarget": {"1": v}, "gun": v})
    if isinstance(v, int):
        # a huge int is still an int id; no drone has it, so the engine counts it later
        assert (intercept, retarget, gun, bad) == ([v], {1: v}, v, 0)
    else:
        assert (intercept, retarget, gun, bad) == ([], {}, None, 3)
    _, steer, _ = clean_attacker_action({"steer": {v if not isinstance(v, int) else str(v):
                                                   [1.0, 1.0]}}, SEASON0)
    assert all(isinstance(k, int) for k in steer)


def test_finite_actions_are_cleaned_exactly_as_before():
    """The fix must not change any action a real bot sends (determinism, rule 5)."""
    action = {"launch": [{"type": "striker", "bearing": 370},
                         {"type": "decoy", "bearing": -45.5},
                         {"type": "striker", "bearing": True}],
              "steer": {"3": [10, -20.5], "4": None}}
    launches, steer, bad = clean_attacker_action(action, SEASON0)
    assert launches == [("striker", 10.0), ("decoy", 314.5), ("striker", 1.0)]
    assert steer == {3: (10.0, -20.5), 4: None} and bad == 0
    assert clean_defender_action({"intercept": [1, "2", 3.9], "retarget": {"5": "6"},
                                  "gun": "7"}) == ([1, 2, 3], {5: 6}, 7, 0)


def test_a_bot_sending_non_finite_numbers_cannot_crash_a_match():
    res = run_match(F / "nonfinite_att.py", F / "nonfinite_def.py", 3)
    meta = res["meta"]
    assert meta["attacker_errors"]["invalid_actions"] > 0
    assert meta["defender_errors"]["invalid_actions"] > 0
    assert meta["drones_launched"]["decoy"] == 0       # every bad bearing was rejected
    assert meta["drones_launched"]["striker"] > 0
    json.dumps(res, allow_nan=False)                   # no NaN reached the replay


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_non_finite_numbers_through_the_sandbox_are_contained():
    """The real path: the container's JSON reply carries NaN and Infinity to the host."""
    lim = SandboxLimits(tick_timeout=0.5, start_timeout=25.0, max_restarts=2)
    boxed = run_match(F / "nonfinite_att.py", F / "nonfinite_def.py", 3, sandbox=True,
                      limits=lim)
    local = run_match(F / "nonfinite_att.py", F / "nonfinite_def.py", 3)
    assert replay_json(boxed) == replay_json(local)


# --- the fuzzer ---------------------------------------------------------------

def test_a_slice_of_trajectories_holds_every_invariant():
    report = fuzz.run(0, 60)
    assert report["failed"] == 0, report["failures"]
    assert len(report["end_reasons"]) >= 2, "the slice should end matches in different ways"


def test_trajectories_are_reproducible_from_their_number():
    assert fuzz.run_one(17) == fuzz.run_one(17)
    assert fuzz.trajectory(17) == fuzz.trajectory(17)


def test_every_rules_variant_is_reached():
    seen = {fuzz.VARIANTS.index(fuzz.trajectory(k)[0]) for k in range(200)}
    assert seen == set(range(len(fuzz.VARIANTS)))


def test_the_fuzz_policies_send_malformed_actions():
    """Otherwise the robustness half of the fuzzer is not testing anything."""
    m = fuzz.CheckedMatch(fuzz.FuzzAttacker(1), fuzz.FuzzDefender(2), 0)
    meta = m.run()["meta"]
    assert meta["attacker_errors"]["invalid_actions"] > 0
    assert meta["defender_errors"]["invalid_actions"] > 0


# A fuzzer that never fails proves nothing; each broken engine below must be caught.

class _HealsAsset(fuzz.CheckedMatch):
    def _impacts(self):
        super()._impacts()
        if self.hp < self.rules.asset_hp:
            self.hp += 1


class _FreeAmmo(fuzz.CheckedMatch):
    def _gun(self):
        ammo = self.ammo
        super()._gun()
        self.ammo = ammo


class _NaNDrone(fuzz.CheckedMatch):
    def _move_drones(self):
        super()._move_drones()
        for d in self._alive_drones()[:1]:
            d.x = math.nan


@pytest.mark.parametrize("broken", [_HealsAsset, _FreeAmmo, _NaNDrone])
def test_the_invariants_catch_a_broken_engine(broken):
    caught = 0
    for k in range(40):
        rules, seed, pseed = fuzz.trajectory(k)
        try:
            broken(fuzz.FuzzAttacker(pseed), fuzz.FuzzDefender(pseed + 1), seed,
                   rules=rules).run()
        except fuzz.FuzzError:
            caught += 1
    assert caught > 0


def test_the_launch_cap_check_catches_an_over_launch():
    m = fuzz.CheckedMatch(fuzz.FuzzAttacker(1), fuzz.FuzzDefender(2), 0)
    m.check()
    for i in (1, 2, 3):                        # SEASON0 allows 2 per tick
        m.interceptors[i] = Interceptor(id=i, target=1, x=0.0, y=0.0)
    m.stock -= 3
    m.interceptors_launched += 3
    with pytest.raises(fuzz.FuzzError, match="interceptors launched in one tick"):
        m.check()


def test_the_nightly_run_logs_a_line_and_covers_new_trajectories(tmp_path):
    from colosseum import ops
    ops.nightly_fuzz(tmp_path, "2026-10-04", n=3)
    ops.nightly_fuzz(tmp_path, "2026-10-05", n=3)
    rows = [json.loads(l) for l in (tmp_path / "fuzz.jsonl").read_text().splitlines()]
    assert [r["start"] for r in rows] == [202610040000, 202610050000]
    assert all(r["failed"] == 0 and r["trajectories"] == 3 for r in rows)


def test_a_nightly_fuzz_failure_raises_so_after_night_alerts(tmp_path, monkeypatch):
    from colosseum import ops
    monkeypatch.setattr(fuzz, "run_one", lambda k: (_ for _ in ()).throw(fuzz.FuzzError("x")))
    with pytest.raises(RuntimeError, match="2/2 fuzz trajectories failed"):
        ops.nightly_fuzz(tmp_path, "2026-10-04", n=2)


def test_the_cli_exits_non_zero_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(fuzz, "run_one", lambda k: (_ for _ in ()).throw(fuzz.FuzzError("x")))
    assert fuzz.main(["--start", "0", "--n", "2"]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == 2
