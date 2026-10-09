"""Idea: Interceptors leave the rail only for tracks the radar has confirmed as strikers, one live interceptor per striker, and the gun is held back for whichever confirmed striker would hit first.

Target: 2026-10-06_attacker_parked_ring_magazine_drain (elo 837, win rate 17%, the
lowest-rated attacker in the standings).

Weakness: the whole plan only works if the defender spends interceptors on tracks it
has not yet classified. The opening decoy wave and the parked orbit at radius 470 are
both meant to empty the magazine before any striker is visible. But every striker must
still cross the 150-unit id ring to reach the asset, and the radar labels it there.

Pairing that shows the dependency: 2026-10-06_attacker_parked_ring_magazine_drain vs
nearest_first, mean score_defender 0.058. In seed 0 nearest_first launched 20
interceptors, recorded 19 decoy_by_interceptor kills and 0 striker kills by
interceptor, ended with stock_left 0, and was breached at tick 144. Every interceptor
went to a decoy.

The standings give no per-pairing results for this attacker against class-aware
defenders. Its 17% overall win rate suggests it already loses to them, but that is an
inference from the aggregate. It is not a measured pairing.

How this bot plays it:
  - It launches no interceptors at "unknown" or "decoy" tracks. The opening wave reaches
    the id ring, is labelled decoy, and is left to the gun or allowed to impact.
    Decoys deal no damage in the logged match.
  - When the strikers are released together, they all cross the id ring at about the
    same time. At 4 units per tick from range 150, that leaves about 30 ticks before
    impact, which is enough to put 20 interceptors in the air at 2 per tick.
  - Each striker gets at most one live interceptor. If that interceptor misses, the
    striker counts as uncovered again and gets a new shot while stock lasts.
  - If an interceptor's target is gone or turns out to be a decoy, the interceptor is
    retargeted to the nearest uncovered striker. If there is none, it is sent toward
    the farthest unknown track to keep it alive for a later rebind.
  - The gun shoots strikers first, starting with the closest and preferring ones with
    no interceptor about to arrive. It fires at decoys only when no striker is in range
    and ammo is above a reserve kept for the final release.
"""

import math

NAME = "class_gated_magazine_keeper"
ROLE = "defender"

_cls_mem = {}


def reset(seed):
    global _cls_mem
    _cls_mem = {}


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def _rng(p):
    try:
        return math.hypot(_f(p[0]), _f(p[1]))
    except Exception:
        return 1e9


def _dist(a, b):
    try:
        return math.hypot(_f(a[0]) - _f(b[0]), _f(a[1]) - _f(b[1]))
    except Exception:
        return 1e9


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(_f(obs.get("stock", 0)))
    ammo = int(_f(obs.get("ammo", 0)))
    launch_cap = int(_f(rules.get("interceptor_launches_per_tick", 2), 2))
    gun_range = _f(rules.get("gun_range", 100.0), 100.0)
    asset_r = _f(rules.get("asset_radius", 25.0), 25.0)
    ammo_total = _f(rules.get("gun_ammo", 120), 120)
    ammo_reserve = int(ammo_total * 0.5)

    # Remember classifications so a label persists if the radar output drops it later.
    by_id = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        by_id[tid] = t
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            _cls_mem[tid] = c

    def cls_of(tid):
        c = _cls_mem.get(tid)
        if c:
            return c
        t = by_id.get(tid)
        return t.get("cls", "unknown") if t else "unknown"

    def trange(t):
        r = t.get("range")
        return _f(r, _rng(t.get("pos", [0, 0]))) if r is not None else _rng(t.get("pos", [0, 0]))

    strikers = [t for t in tracks if cls_of(t.get("id")) == "striker"]
    unknowns = [t for t in tracks if cls_of(t.get("id")) == "unknown"]

    # Count live interceptors on each track.
    cover = {}
    for it in inters:
        tg = it.get("target")
        if tg is not None and tg in by_id and cls_of(tg) != "decoy":
            cover[tg] = cover.get(tg, 0) + 1

    retarget = {}
    for it in inters:
        iid = it.get("id")
        tg = it.get("target")
        if iid is None:
            continue
        if tg is not None and tg in by_id and cls_of(tg) != "decoy":
            continue
        ipos = it.get("pos", [0, 0])
        best = None
        bd = 1e18
        for s in strikers:
            sid = s.get("id")
            if cover.get(sid, 0) > 0:
                continue
            d = _dist(ipos, s.get("pos", [0, 0]))
            if d < bd:
                bd = d
                best = sid
        if best is None:
            # Park the interceptor on the farthest unknown track so it stays alive for a later rebind.
            far = None
            fr = -1.0
            for u in unknowns:
                r = trange(u)
                if r > fr:
                    fr = r
                    far = u.get("id")
            if far is not None and far != tg:
                retarget[iid] = far
            continue
        retarget[iid] = best
        cover[best] = cover.get(best, 0) + 1

    # Launch only at confirmed strikers that have no live interceptor, closest first.
    intercept = []
    if stock > 0:
        cands = []
        for s in strikers:
            sid = s.get("id")
            if cover.get(sid, 0) > 0:
                continue
            r = trange(s)
            if r < asset_r + 12.0:
                continue
            cands.append((r, sid))
        cands.sort()
        for r, sid in cands:
            if len(intercept) >= min(launch_cap, stock):
                break
            intercept.append(sid)
            cover[sid] = cover.get(sid, 0) + 1

    # Gun: confirmed strikers first, then unknowns, then decoys only while ammo is above the reserve.
    gun = None
    if ammo > 0:
        inter_near = {}
        for it in inters:
            tg = it.get("target")
            if tg in by_id:
                d = _dist(it.get("pos", [0, 0]), by_id[tg].get("pos", [0, 0]))
                if d < 20.0:
                    inter_near[tg] = True
        best = None
        bkey = None
        for t in tracks:
            tid = t.get("id")
            r = trange(t)
            if r > gun_range:
                continue
            c = cls_of(tid)
            if c == "striker":
                pri = 0
            elif c == "unknown":
                pri = 1
            else:
                if ammo <= ammo_reserve:
                    continue
                pri = 2
            key = (pri, 1 if inter_near.get(tid) else 0, r)
            if bkey is None or key < bkey:
                bkey = key
                best = tid
        gun = best

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
