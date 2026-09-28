"""Information leakage: outside id range a defender must not be able to tell strikers from decoys.

The rules say the radar "sees position but only reveals a drone's type inside a close range".
test_engine.py already pins that `cls` is masked. This file pins everything else: if any
other field of a track -- or the order of tracks, or the ids -- carries type information
before that range, a defender can skip decoys early and the game's central trade-off is
gone. Two tests:

  1. Counterfactual, exact. Run a launch plan, then the same plan with every striker swapped
     for a decoy and vice versa. Everything the defender sees about a drone outside id range
     must be bit-identical between the two runs. This covers every field at once, including
     ones nobody has thought of yet, plus track order and id assignment.
  2. Statistical. A mixed attacker with a seeded random type order; per-type distributions
     of speed, closing speed, heading error, sensor residuals, id rank, id parity and list
     position must be indistinguishable (two-sample Kolmogorov-Smirnov, alpha = 0.001).
     One sample per drone -- its mean over the ticks it is out of range -- because a
     drone's consecutive ticks are not independent draws, and counting them separately
     inflates the sample size about 75x and makes KS flag chance structure in the plan.
     Tracks must carry exactly the documented fields, so there is no hp or radius to read.

The defender is idle, so no kill roll ever draws from the match RNG and the noise sequence
depends on nothing but the drones present.
"""
import math
import random
from pathlib import Path

import pytest

from colosseum.policy import load_policy
from colosseum.rules import SEASON0
from colosseum.sim import Match

F = Path(__file__).resolve().parent / "fixtures"
TRACK_KEYS = {"id", "pos", "vel", "range", "cls"}


class RecordingMatch(Match):
    """Stores every defender observation next to the ground truth it was built from."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen = []

    def _defender_obs(self):
        truth = {d.id: (d.type, math.hypot(d.x, d.y), (d.x, d.y), (d.vx, d.vy))
                 for d in self._alive_drones()}
        obs = super()._defender_obs()
        self.seen.append((obs, truth))
        return obs


def plan_attacker(tmp_path, name, plan):
    """An attacker that launches `plan` = [(tick, type, bearing), ...] and never steers."""
    src = (f'NAME = "{name}"\nROLE = "attacker"\nPLAN = {plan!r}\n'
           'def act(obs):\n'
           '    t = obs["tick"]\n'
           '    return {"launch": [{"type": k, "bearing": b} for (tt, k, b) in PLAN if tt == t],\n'
           '            "steer": {}}\n')
    path = tmp_path / f"{name}.py"
    path.write_text(src)
    return path


def run_recorded(attacker_path, seed):
    m = RecordingMatch(load_policy(attacker_path, "attacker"),
                       load_policy(F / "idle_def.py", "defender"), seed,
                       rules=SEASON0, record=False)
    m.run()
    return m.seen


def mixed_plan(seed, n=24):
    """Random types in random order at random bearings, a few per tick, within budget."""
    rng = random.Random(seed)
    types = ["striker"] * (n // 2) + ["decoy"] * (n // 2)
    rng.shuffle(types)
    plan, tick = [], 1
    while types:
        for _ in range(rng.randint(1, SEASON0.attacker_launches_per_tick)):
            if types:
                plan.append((tick, types.pop(), round(rng.uniform(0, 360), 3)))
        tick += rng.randint(1, 6)
    assert sum(SEASON0.cost_of(k) for _, k, _ in plan) <= SEASON0.attacker_budget
    return plan


def swapped(plan):
    other = {"striker": "decoy", "decoy": "striker"}
    return [(t, other[k], b) for t, k, b in plan]


def out_of_range_view(seen):
    """Per tick: the full track list, with only in-range tracks' cls masked."""
    view = []
    for obs, truth in seen:
        rows = []
        for tr in obs["tracks"]:
            row = dict(tr)
            if truth[tr["id"]][1] <= SEASON0.id_range:
                row["cls"] = "<in range>"
            rows.append(row)
        view.append(rows)
    return view


# --- 1. counterfactual, exact -------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_swapping_every_drone_type_changes_nothing_the_defender_sees_out_of_range(
        tmp_path, seed):
    plan = mixed_plan(seed)
    a = run_recorded(plan_attacker(tmp_path, "plan_a", plan), seed)
    b = run_recorded(plan_attacker(tmp_path, "plan_b", swapped(plan)), seed)
    va, vb = out_of_range_view(a), out_of_range_view(b)
    n = min(len(va), len(vb))
    assert n > 50 and sum(map(len, va[:n])) > 500
    for tick in range(n):
        assert va[tick] == vb[tick], f"defender view differs at tick {tick + 1}"


# --- 2. statistical -----------------------------------------------------------

def ks_statistic(xs, ys):
    xs, ys = sorted(xs), sorted(ys)
    i = j = 0
    d = 0.0
    while i < len(xs) and j < len(ys):
        v = min(xs[i], ys[j])
        while i < len(xs) and xs[i] <= v:
            i += 1
        while j < len(ys) and ys[j] <= v:
            j += 1
        d = max(d, abs(i / len(xs) - j / len(ys)))
    return d


def ks_critical(n, m, alpha=0.001):
    return math.sqrt(-0.5 * math.log(alpha / 2)) * math.sqrt((n + m) / (n * m))


def features(seen):
    """Per drone, by true type: the mean over its out-of-range ticks of every number a
    defender could compute from its track."""
    per_drone = {}
    for obs, truth in seen:
        tracks = obs["tracks"]
        ids = sorted(truth)
        for pos_in_list, tr in enumerate(tracks):
            dtype, true_range, (tx, ty), (tvx, tvy) = truth[tr["id"]]
            if true_range <= SEASON0.id_range:
                continue
            assert set(tr) == TRACK_KEYS, f"unexpected track fields: {sorted(tr)}"
            (px, py), (vx, vy) = tr["pos"], tr["vel"]
            speed = math.hypot(vx, vy)
            closing = -(px * vx + py * vy) / max(tr["range"], 1e-9)
            per_drone.setdefault(tr["id"], (dtype, []))[1].append(dict(
                speed=speed, closing=closing,
                heading_err=math.acos(max(-1.0, min(1.0, closing / max(speed, 1e-9)))),
                range_resid=tr["range"] - true_range,
                pos_resid=math.hypot(px - tx, py - ty),
                vel_resid=math.hypot(vx - tvx, vy - tvy),
                id_rank=ids.index(tr["id"]) / max(1, len(ids) - 1),
                id_parity=tr["id"] % 2,
                list_pos=pos_in_list / max(1, len(tracks) - 1),
                n_tracks=len(tracks),
            ))
    out = {"striker": [], "decoy": []}
    for dtype, rows in per_drone.values():
        out[dtype].append({k: sum(r[k] for r in rows) / len(rows) for k in rows[0]})
    return out


def test_out_of_range_tracks_are_statistically_indistinguishable_by_type(tmp_path):
    rows = {"striker": [], "decoy": []}
    for seed in range(40):
        seen = run_recorded(plan_attacker(tmp_path, f"mix{seed}", mixed_plan(100 + seed)),
                            seed)
        for k, v in features(seen).items():
            rows[k] += v
    s, d = rows["striker"], rows["decoy"]
    assert len(s) >= 400 and len(d) >= 400
    crit = ks_critical(len(s), len(d))
    for feat in s[0]:
        stat = ks_statistic([r[feat] for r in s], [r[feat] for r in d])
        assert stat < crit, f"{feat} separates strikers from decoys: KS {stat:.3f} >= {crit:.3f}"
