"""Idea: Classify by when a track first crosses the radar edge, so all 20 interceptors go to strikers at r~450, long before they are identified.

Target: the staging logic of hidden_orbit_screen_then_interleaved_drop.
- It parks every drone on a hidden orbit at r~482, outside radar range.
- It releases the decoy screen alone at tick 14 and the striker shells at ticks
  27 and 31. All drones in a group start inward from the same radius.
- So the decoys cross the 450 radar edge together, about 13 ticks before any
  striker. The strikers then arrive as one later cohort.

How we exploit it:
- The first tight cohort is presumed decoy as soon as a second cohort appears.
  We never shoot at it.
- Every later unknown track is presumed a striker. We engage these at the radar
  edge, before identification at 150.
- One interceptor goes to each striker, nearest first, at 2 per tick.
- An interceptor whose target dies, or turns out to be a decoy, is retargeted to
  an uncovered striker.
- The gun takes the nearest striker that has no interceptor about to hit it.
  This leaves gun shots for the misses and the 6 strikers left uncovered.

Evidence from the replays:
- Its two closest calls were against hover_bank_double_lattice. That defender
  let all 16 decoys impact at tick 128, which correctly ignored the screen.
- It still finished with stock_left 1. It needed 9 and 7 gun kills to stop all
  26 strikers.
- Every defender that spends on unknowns (nearest_first 0.08, layered 0.10,
  annealed 0.09-0.13) loses magazine to the screen.
- Every ID-gated defender compresses its launches into the short 150-ring window.
- Timing-based classification avoids both failures. It spends the whole magazine
  early and only on strikers.

Fallbacks:
- If no second cohort appears, the first cohort is engaged once it passes r<250.
- A revealed cls always overrides the guess.
"""
import math

NAME = "radar_edge_cohort_timing_full_magazine"
ROLE = "defender"

COHORT_GAP = 6
SOLO_ENGAGE_R = 250.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cls"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = obs.get("tick", 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    first = _s["first"]
    known = _s["cls"]
    tmap = {}
    for t in tracks:
        tid = t["id"]
        tmap[tid] = t
        if tid not in first:
            first[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            known[tid] = c

    # cohorts by first-detection tick
    ticks_sorted = sorted(set(first.values()))
    cmap = {}
    ci = 0
    prev = None
    for tk in ticks_sorted:
        if prev is not None and tk - prev >= COHORT_GAP:
            ci += 1
        cmap[tk] = ci
        prev = tk
    n_cohorts = ci + 1
    c0_ids = [i for i, tk in first.items() if cmap[tk] == 0]
    c0_has_striker = any(known.get(i) == "striker" for i in c0_ids)
    c0_size = len(c0_ids)

    def rng(t):
        r = t.get("range")
        if r is None:
            r = _d(t["pos"], ap)
        return float(r)

    def is_threat(t):
        tid = t["id"]
        c = known.get(tid)
        if c is not None:
            return c == "striker"
        coh = cmap.get(first.get(tid, tick), 0)
        if coh >= 1:
            return True
        if c0_has_striker:
            return True
        if n_cohorts >= 2 and c0_size >= 4:
            return False
        return rng(t) < SOLO_ENGAGE_R

    threats = [t for t in tracks if is_threat(t)]
    threats.sort(key=rng)
    threat_ids = set(t["id"] for t in threats)

    assigned = {}
    for it in inters:
        tg = it.get("target")
        if tg in threat_ids:
            assigned[tg] = assigned.get(tg, 0) + 1

    # retarget interceptors whose target is gone or not a threat
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg in threat_ids:
            continue
        ip = it.get("pos", ap) or ap
        best = None
        bd = 1e18
        for t in threats:
            if assigned.get(t["id"], 0) > 0:
                continue
            dd = _d(ip, t["pos"])
            if dd < bd:
                bd = dd
                best = t["id"]
        if best is None:
            for t in threats:
                dd = _d(ip, t["pos"])
                if dd < bd:
                    bd = dd
                    best = t["id"]
        if best is not None:
            retarget[it["id"]] = best
            assigned[best] = assigned.get(best, 0) + 1

    # launches: one per uncovered threat, nearest first
    launch = []
    for t in threats:
        if len(launch) >= cap or stock <= 0:
            break
        if assigned.get(t["id"], 0) == 0:
            launch.append(t["id"])
            assigned[t["id"]] = 1
            stock -= 1
    if len(launch) < cap and stock > 0:
        for t in threats:
            if len(launch) >= cap or stock <= 0:
                break
            if rng(t) < 200.0 and assigned.get(t["id"], 0) < 2:
                launch.append(t["id"])
                assigned[t["id"]] = assigned.get(t["id"], 0) + 1
                stock -= 1

    # gun
    gun = None
    if ammo > 0:
        cands = []
        for t in tracks:
            if known.get(t["id"]) == "decoy":
                continue
            if t.get("cls") == "decoy":
                continue
            r = rng(t)
            if r > gun_range:
                continue
            covered = False
            for it in inters:
                if it.get("target") == t["id"] and _d(it.get("pos", ap) or ap, t["pos"]) < 30.0:
                    covered = True
                    break
            cands.append((1 if covered else 0, r, t["id"]))
        if cands:
            cands.sort()
            gun = cands[0][2]

    return {"intercept": launch, "retarget": retarget, "gun": gun}
