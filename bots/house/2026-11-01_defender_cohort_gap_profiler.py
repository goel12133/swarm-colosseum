"""Idea: Sort unidentified tracks into launch cohorts by the silent gaps between first radar sightings, and judge each cohort as a group so the defender can engage a later wave at full radar range, long before any member reaches id_range.

Why this is not the obvious counter
-----------------------------------
The obvious counter to bait_count_then_clear_sky_wave is a class gate:
never fire at an "unknown" track and wait for id_range (150) to reveal the
type. class_gated_magazine_keeper already does this. It saves the magazine
from the bait, but it hands the attacker a different win. The striker wave
is 26 drones released inside 7 ticks. If you only engage at 150 you get
about 10 ticks of closing time, and the 2-per-tick launch cap lets you
commit about 20 interceptors. That leaves no time to see a miss and fire
again, and the gun is swamped.

This bot does not wait for type at all for most tracks. It reads the
attacker's timing. Each track's first radar sighting is logged, and a gap
of several ticks with no new tracks closes a cohort. Every attacker that
uses bait then waits, so it always leaves such a gap. Cohort 0, the
opening burst, is held until one of its members is identified. Its
identified members then decide the class of the rest. A later cohort that
appears after a silence is treated as hostile from the moment it shows on
radar at 450 range, unless its own identified members say decoy.

Early engagement gives roughly 25+ ticks of flight. That makes it possible
to shoot, look and shoot again. A missed or expired shot frees the track,
which is re-engaged, and interceptors whose targets died are retargeted
in flight. The gun takes the closest hostile that no interceptor covers.
The attacker's launch counter only ever sees interceptors aimed at real
strikers.
"""

import math

NAME = "cohort_gap_profiler"
ROLE = "defender"

_S = {}


def reset(seed=0):
    _S.clear()
    _S.update({
        "first_seen": {},
        "cohort_of": {},
        "cohorts": [],      # list of dicts {"s": strikers_ided, "d": decoys_ided, "n": size}
        "last_new": -999,
        "known": {},
    })


reset(0)

_GAP = 6


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _hostile(tid, cls, rng):
    if cls == "striker":
        return True
    if cls == "decoy":
        return False
    ci = _S["cohort_of"].get(tid, 0)
    c = _S["cohorts"][ci] if ci < len(_S["cohorts"]) else {"s": 0, "d": 0, "n": 0}
    s, d = c["s"], c["d"]
    if s + d > 0:
        # Mixed cohorts: treat the unknowns as strikers unless decoys dominate.
        return s >= 0.3 * (s + d)
    if ci == 0:
        # The opening burst is suspect bait; wait for identification,
        # but never let an unknown get dangerously close.
        return rng < 160.0
    return True


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    life = float(rules.get("interceptor_lifetime", 90))
    ispeed = float(rules.get("interceptor_speed", 12.0)) or 12.0
    gun_range = float(rules.get("gun_range", 100.0))
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))

    fs = _S["first_seen"]
    co = _S["cohort_of"]
    cohorts = _S["cohorts"]
    known = _S["known"]

    # Cohort bookkeeping.
    new_ids = [t["id"] for t in tracks if t.get("id") not in fs]
    if new_ids:
        if not cohorts or tick - _S["last_new"] > _GAP:
            cohorts.append({"s": 0, "d": 0, "n": 0})
        ci = len(cohorts) - 1
        for tid in new_ids:
            fs[tid] = tick
            co[tid] = ci
            cohorts[ci]["n"] += 1
        _S["last_new"] = tick

    for t in tracks:
        tid = t.get("id")
        cls = t.get("cls", "unknown")
        if cls in ("striker", "decoy") and known.get(tid) != cls:
            ci = co.get(tid, 0)
            if ci < len(cohorts):
                prev = known.get(tid)
                if prev == "striker":
                    cohorts[ci]["s"] -= 1
                elif prev == "decoy":
                    cohorts[ci]["d"] -= 1
                cohorts[ci]["s" if cls == "striker" else "d"] += 1
            known[tid] = cls

    tmap = {}
    hostile = {}
    for t in tracks:
        tid = t.get("id")
        tmap[tid] = t
        cls = known.get(tid, t.get("cls", "unknown"))
        rng = float(t.get("range", 1e9))
        hostile[tid] = _hostile(tid, cls, rng)

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # Coverage from live interceptors.
    cover = {}
    retarget = {}
    free_inters = []
    for it in inters:
        tgt = it.get("target")
        age = float(it.get("age", 0))
        pos = it.get("pos", [0.0, 0.0])
        t = tmap.get(tgt)
        if t is not None and hostile.get(tgt, False):
            if cover.get(tgt, 0) >= 1:
                free_inters.append(it)
                continue
            eta = dist(pos, t["pos"]) / ispeed
            if age + eta + 1 < life:
                cover[tgt] = cover.get(tgt, 0) + 1
                continue
        free_inters.append(it)

    def uncovered():
        lst = [tid for tid in tmap if hostile.get(tid) and cover.get(tid, 0) == 0]
        lst.sort(key=lambda x: float(tmap[x].get("range", 1e9)))
        return lst

    # Retarget wasted interceptors in flight.
    for it in free_inters:
        cand = uncovered()
        if not cand:
            break
        pos = it.get("pos", [0.0, 0.0])
        age = float(it.get("age", 0))
        best, bd = None, 1e18
        for tid in cand:
            d = dist(pos, tmap[tid]["pos"])
            if age + d / ispeed + 1 < life and d < bd:
                best, bd = tid, d
        if best is not None:
            retarget[it["id"]] = best
            cover[best] = cover.get(best, 0) + 1

    # New launches against the most urgent uncovered hostiles.
    intercept = []
    cand = uncovered()
    n = min(per_tick, stock)
    for tid in cand:
        if len(intercept) >= n:
            break
        intercept.append(tid)
        cover[tid] = cover.get(tid, 0) + 1

    # Gun: closest uncovered hostile in range, else closest hostile in range.
    gun = None
    if ammo > 0:
        inr = [tid for tid in tmap
               if hostile.get(tid) and float(tmap[tid].get("range", 1e9)) <= gun_range]
        if inr:
            unc = [x for x in inr if cover.get(x, 0) == 0]
            pool = unc if unc else inr
            gun = min(pool, key=lambda x: float(tmap[x].get("range", 1e9)))
        else:
            unk = [tid for tid in tmap
                   if known.get(tid) != "decoy"
                   and tmap[tid].get("cls", "unknown") != "decoy"
                   and float(tmap[tid].get("range", 1e9)) <= gun_range * 0.6]
            if unk:
                gun = min(unk, key=lambda x: float(tmap[x].get("range", 1e9)))

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
