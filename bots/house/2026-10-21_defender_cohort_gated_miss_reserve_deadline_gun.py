"""Idea: Shape the leakers instead of just killing strikers: engage only the post-screen cohort, hold a miss-reserve so the first shell's misses are re-engaged before the second shell, and run the gun earliest-deadline-first on what is left.

Target: hidden_orbit_screen_then_interleaved_drop.

Part of its logic attacked: the fixed release schedule (DECOY_RELEASE=14,
SHELL_A_RELEASE=27, SHELL_B_RELEASE=31) from a single orbit radius.
- Every decoy crosses the 450 radar edge together, about 13 ticks before any striker.
  This defender keeps a first-seen tick for every track and never fires at that
  first cohort.
- Shell A crosses every range ring together, and shell B always trails it by 4 ticks
  (16 units). So the attacker hands us a deterministic deadline order.
- Its blast-proof spacing defeats packers. It cannot stop a defender that simply
  sequences single shots well.

What the replays show: in both of its closest calls, against hover_bank_double_lattice,
all 16 decoys flew in untouched at tick 128. The defender won with 17-19 interceptor
kills plus 7-9 gun kills. The asset tolerates 2 hits, so the match is decided by
whether the gun can clean up about 9 leakers in the roughly 23-tick window
before impact.

How this bot widens that margin:
- Interceptors go to the nearest (earliest-deadline) strikers first, so shell A is
  engaged before shell B.
- About 15% of the in-flight count is held back while shots resolve. A shell-A miss
  is re-engaged before any fresh shell-B target, so the leakers that remain are the
  late-arriving ones.
- Once a target is inside 150 units, the reserve is released.
- The gun shoots the closest hostile that no interceptor is already chasing,
  earliest deadline first, from the moment it enters range.
"""
import math

NAME = "cohort_gated_miss_reserve_deadline_gun"
ROLE = "defender"

ENGAGE_R = 280.0
COHORT_W = 5
COHORT_GAP = 8
URGENT_R = 150.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _act(obs):
    if "first" not in _s:
        reset(None)
    first = _s["first"]
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))

    rng = {}
    byid = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        byid[tid] = t
        if tid not in first:
            first[tid] = tick
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0.0, 0.0])
            r = math.hypot(p[0] - ax, p[1] - ay)
        rng[tid] = float(r)

    # cohort detection
    t0 = min(first.values()) if first else None
    later = False
    if t0 is not None:
        for f in first.values():
            if f >= t0 + COHORT_GAP:
                later = True
                break

    def hostile(tid):
        t = byid[tid]
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if later:
            return first.get(tid, tick) > t0 + COHORT_W
        return rng[tid] < 120.0

    hostiles = [tid for tid in byid if hostile(tid)]

    # retarget orphaned interceptors
    targeted = {}
    retarget = {}
    orphans = []
    for it in inters:
        tg = it.get("target")
        if tg in byid and hostile(tg):
            targeted[tg] = targeted.get(tg, 0) + 1
        else:
            orphans.append(it)
    for it in orphans:
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        best = None
        bd = 1e18
        for tid in hostiles:
            if tid in targeted:
                continue
            p = byid[tid].get("pos", [0.0, 0.0])
            d = math.hypot(p[0] - ip[0], p[1] - ip[1]) + 0.5 * rng[tid]
            if d < bd:
                bd = d
                best = tid
        if best is not None and it.get("id") is not None:
            retarget[it["id"]] = best
            targeted[best] = 1

    inflight = sum(targeted.values())
    reserve = int(math.ceil(0.15 * inflight - 1e-9)) if inflight > 0 else 0

    # launches: earliest deadline first, with miss reserve
    launch = []
    avail = stock
    cands = sorted([tid for tid in hostiles if tid not in targeted],
                   key=lambda k: rng[k])
    for tid in cands:
        if len(launch) >= cap or avail <= 0:
            break
        r = rng[tid]
        if r > ENGAGE_R:
            break
        urgent = r < URGENT_R
        if avail - reserve <= 0 and not urgent:
            continue
        launch.append(tid)
        targeted[tid] = 1
        avail -= 1

    # gun: earliest deadline, prefer targets no interceptor is chasing
    gun = None
    if ammo > 0:
        inrange = [tid for tid in hostiles if rng[tid] <= gun_range]
        if inrange:
            gun = min(inrange, key=lambda k: (1 if k in targeted else 0, rng[k]))

    return {"intercept": launch, "retarget": retarget, "gun": gun}
