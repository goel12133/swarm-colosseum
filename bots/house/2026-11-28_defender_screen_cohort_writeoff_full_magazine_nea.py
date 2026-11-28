"""Idea: Write off the whole first radar-entry cohort as a screen, put every interceptor on a separate later-cohort track the tick it appears, and use the gun only on the nearest striker that no interceptor is about to reach.

Which part of the attacker this targets:
The attacker always releases its decoys on a fixed timer (DECOY_RELEASE=14).
Its strikers release later, at SHELL_A_RELEASE=27 and SHELL_B_RELEASE=31.
All of them stage on the same r~482 orbit, so the decoys always cross the
450 radar ring about 13 ticks before the first striker does. That gap is
fixed, so radar-entry order is a reliable label well before the 150 ID ring.
The attacker counts on defenders that either:
  - fire at unknowns and spend interceptors on the screen, or
  - wait for ID at 150 and then hit the 2-per-tick launch cap against 26
    strikers arriving together.

What the replays show:
In its two closest calls (hover_bank_double_lattice, seeds 3 and 5), every
striker died: 17 or 19 to interceptors and 9 or 7 to the gun. All 16 decoys
reached the asset harmlessly at tick 128. The asset took no damage. So the
attacker loses when the defender:
  - spends nothing on the screen,
  - gets one interceptor onto each early striker track, and
  - lets the gun finish the remainder.
Defenders that waited for ID or wasted rounds on the screen stayed near 0.1-0.3.

How this bot does it:
  - The screen cohort is confirmed as soon as a second cohort shows up after
    a lull. Its unknown tracks are never engaged.
  - Interceptors launch at 2 per tick at uncovered later-cohort or confirmed
    striker tracks. Each target gets one interceptor, nearest first.
  - An interceptor whose target vanished or turned out to be a decoy is
    retargeted to an uncovered striker it can still reach.
  - The gun fires every tick at the nearest live striker in range. It skips
    a striker that an interceptor is about to reach, as long as another
    target exists.
"""
import math

NAME = "screen_cohort_writeoff_full_magazine_nearest_gun"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cls"] = {}
    _s["t0"] = None


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = _f(ap[0]), _f(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    gun_range = _f(rules.get("gun_range", 100.0), 100.0)
    i_speed = _f(rules.get("interceptor_speed", 12.0), 12.0)
    life = _f(rules.get("interceptor_lifetime", 90), 90.0)
    cap = int(rules.get("interceptor_launches_per_tick", 2) or 2)

    fs = _s["first_seen"]
    cmem = _s["cls"]
    tmap = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        tmap[tid] = t
        if tid not in fs:
            fs[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            cmem[tid] = c
        if _s["t0"] is None:
            _s["t0"] = tick
    t0 = _s["t0"]

    # Cohort logic: the first cohort is a screen once a later cohort follows a lull.
    lull_confirmed = False
    if t0 is not None:
        for tid, ft in fs.items():
            if ft >= t0 + 8:
                lull_confirmed = True
                break

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0, 0])
            return math.hypot(_f(p[0]) - ax, _f(p[1]) - ay)
        return _f(r, 1e9)

    def threat(tid):
        t = tmap[tid]
        c = cmem.get(tid, t.get("cls", "unknown"))
        if c == "striker":
            return 2
        if c == "decoy":
            return 0
        first_cohort = fs.get(tid, tick) <= (t0 if t0 is not None else tick) + 5
        if first_cohort:
            if lull_confirmed:
                return 0
            return 1 if rng(t) < 260.0 else 0
        return 1

    thr = {tid: threat(tid) for tid in tmap}

    # Coverage from interceptors already in flight.
    covered = {}
    retarget = {}
    free_inters = []
    for it in inters:
        iid = it.get("id")
        tg = it.get("target")
        if tg in tmap and thr.get(tg, 0) > 0 and covered.get(tg, 0) == 0:
            covered[tg] = 1
        else:
            free_inters.append(it)

    # Retarget interceptors whose target is gone, is a decoy, or is already covered.
    for it in free_inters:
        iid = it.get("id")
        ip = it.get("pos", [0, 0]) or [0, 0]
        ix, iy = _f(ip[0]), _f(ip[1])
        age = _f(it.get("age", 0))
        left = max(0.0, life - age)
        best = None
        bestk = None
        for tid, t in tmap.items():
            if thr[tid] <= 0 or covered.get(tid, 0) > 0:
                continue
            p = t.get("pos", [0, 0])
            d = math.hypot(_f(p[0]) - ix, _f(p[1]) - iy)
            if d / max(1e-6, i_speed + 4.0) > left - 1:
                continue
            k = (-thr[tid], d)
            if bestk is None or k < bestk:
                bestk = k
                best = tid
        if best is not None:
            retarget[iid] = best
            covered[best] = 1

    # New launches.
    intercept = []
    cands = [tid for tid in tmap if thr[tid] > 0 and covered.get(tid, 0) == 0]
    cands.sort(key=lambda tid: (-thr[tid], rng(tmap[tid])))
    n = min(cap, stock)
    for tid in cands:
        if len(intercept) >= n:
            break
        if rng(tmap[tid]) < 30.0:
            continue
        intercept.append(tid)
        covered[tid] = 1

    # Gun: nearest live threat in range, preferring ones no interceptor is about to reach.
    gun = None
    if ammo > 0:
        imminent = set()
        for it in inters:
            tg = it.get("target")
            if tg in tmap:
                ip = it.get("pos", [0, 0]) or [0, 0]
                p = tmap[tg].get("pos", [0, 0])
                if math.hypot(_f(ip[0]) - _f(p[0]), _f(ip[1]) - _f(p[1])) < 2.0 * (i_speed + 4.0):
                    imminent.add(tg)
        for tid in retarget:
            pass
        gc = []
        for tid, t in tmap.items():
            c = cmem.get(tid, t.get("cls", "unknown"))
            if c == "decoy":
                continue
            r = rng(t)
            if r > gun_range:
                continue
            if c != "striker" and thr[tid] <= 0:
                continue
            gc.append((1 if tid in imminent else 0, 0 if c == "striker" else 1, r, tid))
        if gc:
            gc.sort(key=lambda x: (x[0], x[1], x[2]))
            gun = gc[0][3]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
