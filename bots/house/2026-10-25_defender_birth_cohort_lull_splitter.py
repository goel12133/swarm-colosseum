"""Idea: Sort radar tracks into birth cohorts by the tick each was first seen, split at quiet gaps, and fire long-range interceptors at every unknown track born after a lull while ignoring the earliest cohort until radar reveals its type.

Swarm Colosseum is an abstract game. Everything here is made-up units.

Why this is not the obvious counter
-----------------------------------
There are two obvious answers to bait_count_then_clear_sky_wave:
  (a) "never fire at unknowns, wait for the id_range reveal", or
  (b) "keep interceptors airborne so the attacker never sees a clear sky".
Option (a) gives up range. A striker identified at 150 is about 31 ticks
from impact, so every engagement gets squeezed into the last moments.
Option (b) burns the magazine and the lifetime clock. That is exactly what
the bait is designed to make us do.

This bot does neither. It fires at unknowns, and it fires early, at long
range. But it chooses its targets by when they were born, not by what
they look like. Any attacker that baits first and then waits must leave a
quiet gap in its launch stream, because that gap is the whole point of the
bait. The first cohort (the bait) gets no interceptors at all, only
classification-gated fire. Every cohort born after a lull is presumed to be
the real wave. It gets interceptors at roughly 300+ range, two per tick,
starting the moment those tracks appear. That leaves time to retarget,
double-cover the close-in leakers, and still have the gun for the end.

Safety nets
-----------
Any track the radar reveals as a striker is engaged no matter its cohort.
Interceptors whose target turns out to be a decoy, or whose target has
vanished, are retargeted to the nearest uncovered threat. The gun never
shoots revealed decoys.
"""

import math

NAME = "birth_cohort_lull_splitter"
ROLE = "defender"

_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "first_seen": {},     # track id -> first tick seen
        "cohort_of": {},      # track id -> cohort index
        "cohort": 0,
        "last_birth": None,
        "known_decoy": set(),
        "known_striker": set(),
    })


reset(0)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _rng(t):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        r = math.hypot(p[0], p[1])
    return float(r)


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    lull_gap = 15

    fs = _state["first_seen"]
    co = _state["cohort_of"]

    # Birth bookkeeping: open a new cohort after a quiet gap in births.
    new_ids = [t.get("id") for t in tracks if t.get("id") not in fs]
    if new_ids:
        lb = _state["last_birth"]
        if lb is not None and tick - lb >= lull_gap:
            _state["cohort"] += 1
        _state["last_birth"] = tick
        for tid in new_ids:
            fs[tid] = tick
            co[tid] = _state["cohort"]

    # Remember revealed types (they persist even if cls flickers).
    for t in tracks:
        c = t.get("cls")
        tid = t.get("id")
        if c == "decoy":
            _state["known_decoy"].add(tid)
        elif c == "striker":
            _state["known_striker"].add(tid)

    by_id = {t.get("id"): t for t in tracks}

    def kind(tid):
        if tid in _state["known_striker"]:
            return "striker"
        if tid in _state["known_decoy"]:
            return "decoy"
        return "unknown"

    def is_threat(tid):
        k = kind(tid)
        if k == "striker":
            return True
        if k == "decoy":
            return False
        return co.get(tid, 0) >= 1

    threats = [t for t in tracks if is_threat(t.get("id"))]
    threats.sort(key=_rng)

    # Count current coverage per target.
    cover = {}
    valid_inters = []
    for it in inters:
        tg = it.get("target")
        if tg in by_id and is_threat(tg):
            cover[tg] = cover.get(tg, 0) + 1
            valid_inters.append(it)

    # Retarget interceptors whose targets are gone or revealed as decoys.
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg in by_id and is_threat(tg):
            continue
        ip = it.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        best, bd = None, None
        for t in threats:
            tid = t.get("id")
            if cover.get(tid, 0) >= 1:
                continue
            p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if bd is None or d < bd:
                best, bd = tid, d
        if best is None:
            # Fall back to any revealed striker, even if it is already covered.
            for t in threats:
                if kind(t.get("id")) == "striker":
                    p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
                    d = math.hypot(p[0] - ip[0], p[1] - ip[1])
                    if bd is None or d < bd:
                        best, bd = t.get("id"), d
        if best is not None and best != tg:
            retarget[it.get("id")] = best
            cover[best] = cover.get(best, 0) + 1

    # New launches.
    intercept = []
    reserve = 3
    avail = stock
    uncovered = [t for t in threats if cover.get(t.get("id"), 0) == 0]
    for t in uncovered:
        if len(intercept) >= per_tick or avail <= 0:
            break
        tid = t.get("id")
        if kind(tid) != "striker" and avail <= reserve:
            continue
        intercept.append(tid)
        cover[tid] = 1
        avail -= 1

    # Double cover close revealed strikers when the magazine is ample.
    if len(intercept) < per_tick and avail > 0:
        n_unc = sum(1 for t in threats if cover.get(t.get("id"), 0) == 0)
        for t in threats:
            if len(intercept) >= per_tick or avail <= n_unc:
                break
            tid = t.get("id")
            if (kind(tid) == "striker" and cover.get(tid, 0) == 1
                    and _rng(t) < 200.0 and tid not in intercept):
                intercept.append(tid)
                cover[tid] = 2
                avail -= 1

    # Gun: nearest revealed striker in range, else nearest non-decoy unknown.
    gun = None
    if ammo > 0:
        best, br = None, None
        for t in tracks:
            tid = t.get("id")
            r = _rng(t)
            if r > gun_range or kind(tid) != "striker":
                continue
            if br is None or r < br:
                best, br = tid, r
        if best is None:
            for t in tracks:
                tid = t.get("id")
                r = _rng(t)
                if r > gun_range or kind(tid) != "unknown":
                    continue
                if br is None or r < br:
                    best, br = tid, r
        gun = best

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
