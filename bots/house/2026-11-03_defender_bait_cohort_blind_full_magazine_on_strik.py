"""Idea: Treat the first-tick birth cohort as zero-value bait, never launch or fire at it, and spend the whole untouched 20-round magazine plus every gun shot only on the post-lull striker wave, re-pointing any interceptor whose target dies.

Weakness attacked
-----------------
bait_count_then_clear_sky_wave always opens the same way. It launches 16
decoys in ticks 0-3 on golden-angle bearings, then holds every striker until
its own count of our launches says the magazine is spent, or until tick 140
with a clear sky. It never reacts to a defender that refuses the bait. If we
launch nothing at the bait, its "spent" test never fires. It then releases at
the soft deadline, tick 140. Its 26 strikers are the only tracks born after
the opening cohort.

The replays show that bait damage is irrelevant and magazine discipline is
what matters. In both closest calls, 10 and 16 decoys hit the asset and
asset_hp stayed at 30, so decoys do no damage. The best result came from
cohort_screen_skip_deadline_reserve (seed 6, score 0.755). It spent all 20
interceptors on strikers (striker_by_interceptor 20) and fired only 18 gun
shots, none at decoys. In contrast, contracting_ring_blaster (0.04) put 20
interceptors into 2 decoy kills. Every point of defender score against this
bot came from saving interceptors for the second cohort.

This bot takes that idea to its limit:
  * Any track first seen in the opening cohort is never given an
    interceptor unless the radar shows cls == "striker".
  * The gun never fires at a decoy, or at an unrevealed opening-cohort track.
  * Strikers get interceptors as soon as they cross radar range, two per
    tick, at most one each. The intercepts happen far out, around r=300.
  * If an interceptor's target dies (gun or blast), it is re-pointed to the
    nearest uncovered striker, so no round is wasted.
  * The gun works on strikers that have no interceptor arriving in time,
    nearest first.
"""

import math

NAME = "bait_cohort_blind_full_magazine_on_strikers"
ROLE = "defender"

_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "first_seen": {},
        "t0": None,
        "launched_at": {},   # track_id -> count of interceptors sent
    })


reset(0)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    i_speed = float(rules.get("interceptor_speed", 12.0)) or 12.0
    life = int(rules.get("interceptor_lifetime", 90))
    max_ticks = int(rules.get("max_ticks", 600))
    asset_r = float(rules.get("asset_radius", 25.0))

    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []

    fs = _state["first_seen"]
    for t in tracks:
        tid = t.get("id")
        if tid not in fs:
            fs[tid] = tick
            if _state["t0"] is None:
                _state["t0"] = tick
    t0 = _state["t0"]

    def opening(tid):
        return t0 is not None and fs.get(tid, tick) <= t0 + 12

    # Candidate threats.
    cand = {}
    for t in tracks:
        tid = t.get("id")
        cls = t.get("cls", "unknown")
        if cls == "decoy":
            continue
        if cls != "striker" and opening(tid):
            continue
        pos = t.get("pos", [0.0, 0.0])
        rng = float(t.get("range", math.hypot(pos[0], pos[1])))
        cand[tid] = (t, rng)

    # Current coverage by live interceptors.
    cover = {}
    free = []
    for it in inters:
        tgt = it.get("target")
        if tgt in cand:
            cover.setdefault(tgt, []).append(it)
        else:
            free.append(it)

    retarget = {}
    # Re-point interceptors whose target is gone or not a threat.
    for it in free:
        age = int(it.get("age", 0))
        ipos = it.get("pos", [0.0, 0.0])
        best = None
        best_d = 1e18
        for tid, (t, rng) in cand.items():
            if tid in cover:
                continue
            d = _dist(ipos, t.get("pos", [0.0, 0.0]))
            if d / i_speed > (life - age) + 5:
                continue
            if d < best_d:
                best_d = d
                best = tid
        if best is not None:
            retarget[it.get("id")] = best
            cover.setdefault(best, []).append(it)

    # Launch new interceptors at uncovered threats, nearest first.
    intercept = []
    uncovered = sorted(
        [(rng, tid) for tid, (t, rng) in cand.items() if tid not in cover],
        key=lambda x: x[0])
    budget = min(per_tick, stock)
    for rng, tid in uncovered:
        if budget <= 0:
            break
        if rng <= asset_r + 8:
            continue
        intercept.append(tid)
        cover.setdefault(tid, []).append(None)
        _state["launched_at"][tid] = _state["launched_at"].get(tid, 0) + 1
        budget -= 1

    # Optional double cover for close threats once nothing is uncovered.
    if budget > 0 and not [1 for r, tid in uncovered if tid not in cover]:
        late = tick > max_ticks * 0.5
        doubles = sorted(
            [(rng, tid) for tid, (t, rng) in cand.items()
             if len(cover.get(tid, [])) == 1 and (rng < 200 or late)
             and rng > gun_range * 0.6],
            key=lambda x: x[0])
        for rng, tid in doubles:
            if budget <= 0:
                break
            if stock - len(intercept) <= 0:
                break
            intercept.append(tid)
            budget -= 1

    # Gun: nearest threat in range without an interceptor arriving in time.
    gun = None
    if ammo > 0:
        best_key = None
        for tid, (t, rng) in cand.items():
            if rng > gun_range:
                continue
            tti = max(0.0, (rng - asset_r) / 4.0)
            covered_in_time = False
            for it in cover.get(tid, []):
                if it is None:
                    continue
                d = _dist(it.get("pos", [0.0, 0.0]), t.get("pos", [0.0, 0.0]))
                if d / (i_speed + 4.0) + 1 < tti:
                    covered_in_time = True
                    break
            key = (1 if covered_in_time else 0, rng)
            if best_key is None or key < best_key:
                best_key = key
                gun = tid

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
