"""Idea: Keep a small reserve of interceptors parked at the asset by ping-ponging their targets across the ring, so the attacker's own anti-blast jink stalls every striker in the gun's best range while the gun and the late reserve finish them.

Target: the "jink apart" branch in veiled_full_ring_blastproof_split's release logic.

What its code does: once released, a striker jinks whenever any interceptor is within 50 and
another drone is within 18. It steers to a waypoint 20 units sideways and 8 units inward, and
that waypoint is recomputed every tick. The striker still moves 4 per tick, but its inward
progress drops to about 4*8/21.5 = 1.5 per tick. The rule switches off only below r=30. The
ring is 30 strikers at 12 degrees, with half-rings offset 12 units radially, so cross-wave
neighbours are inside 18 for every r below ~64. Any interceptor sitting near the origin is
within 50 of every striker in r<50. So the whole ring crawls through the 30..50 band. That
takes ~13 ticks instead of ~5, and it happens exactly where the gun is closest and most
accurate.

What the replays show: both of its near-losses end with stock_left 0 and the gun scoring 11
or 13 kills from only 25 shots. Gun shots per tick are the margin it is built to exhaust,
because everything arrives in one 3-tick pulse. The only defenders scoring above the 0.13-0.14
floor keep interceptors alive near the asset. Those are dither_parked_magazine 0.20,
loiter_pool 0.26, parked_hover 0.27 and origin_pingpong 0.23. None of them deliberately holds
interceptors at the origin to trigger the jink.

Plan:
- Fire stock minus 6 early at long range. Those strikers are 70+ units apart, so none of them
  jink, and each round gets a clean 0.85 shot.
- When the ring reaches r<130, launch the 6 reserve rounds and keep each one hovering at the
  asset. Every tick it is retargeted to whichever far track lies opposite its current offset.
- The gun fires every tick at the closest uncommitted track.
- A parked round is committed only when a striker that the gun is not shooting breaks
  inside ~44.
"""

import math

NAME = "origin_parked_jink_stall"
ROLE = "defender"

_S = {}
RESERVE = 6


def reset(seed=None):
    _S.clear()


def _xy(p):
    try:
        if isinstance(p, dict):
            return float(p.get("x", 0.0)), float(p.get("y", 0.0))
        return float(p[0]), float(p[1])
    except Exception:
        return 0.0, 0.0


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    st = _S
    if "init" not in st:
        st["init"] = True
        st["roles"] = {}
        st["intents"] = []
        st["parked_req"] = 0
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    asset = obs.get("asset", {}) or {}
    ax, ay = _xy(asset.get("pos") or [0.0, 0.0])
    gun_range = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    tracks = []
    for t in obs.get("tracks", []) or []:
        tid = t.get("id")
        x, y = _xy(t.get("pos") or [0.0, 0.0])
        x -= ax
        y -= ay
        r = t.get("range")
        try:
            r = float(r)
        except Exception:
            r = math.hypot(x, y)
        cls = t.get("cls", "unknown")
        if cls == "decoy":
            continue
        tracks.append((tid, x, y, r))
    by_id = {t[0]: t for t in tracks}

    inters = []
    for it in obs.get("interceptors", []) or []:
        iid = it.get("id")
        x, y = _xy(it.get("pos") or [0.0, 0.0])
        inters.append((iid, it.get("target"), x - ax, y - ay, int(it.get("age", 0) or 0)))

    # Register new interceptors by matching their target to launch intents.
    st["intents"] = [i for i in st["intents"] if tick - i[2] <= 3]
    for iid, tgt, _, _, _ in sorted(inters, key=lambda z: str(z[0])):
        if iid in st["roles"]:
            continue
        role = "early"
        for k, (ttid, rl, tk) in enumerate(st["intents"]):
            if ttid == tgt:
                role = rl
                st["intents"].pop(k)
                break
        st["roles"][iid] = role

    engaged = {}
    for iid, tgt, _, _, _ in inters:
        if st["roles"].get(iid) in ("early", "commit") and tgt in by_id:
            engaged[tgt] = engaged.get(tgt, 0) + 1

    retarget = {}
    intercept = []

    # Gun: closest uncommitted track in range.
    gun = None
    inr = [t for t in tracks if t[3] <= gun_range]
    if inr and ammo > 0:
        un = [t for t in inr if t[0] not in engaged]
        pool = un if un else inr
        gun = min(pool, key=lambda t: t[3])[0]

    def nearest_unengaged(ix, iy, maxr=None):
        best, bd = None, None
        for t in tracks:
            if t[0] in engaged or t[0] == gun:
                continue
            if maxr is not None and t[3] > maxr:
                continue
            d = math.hypot(t[1] - ix, t[2] - iy)
            if bd is None or d < bd:
                best, bd = t, d
        return best

    # Early/commit interceptors that lost their target.
    for iid, tgt, ix, iy, age in inters:
        if st["roles"].get(iid) in ("early", "commit") and tgt not in by_id:
            t = nearest_unengaged(ix, iy)
            if t is None and tracks:
                t = min(tracks, key=lambda z: math.hypot(z[1] - ix, z[2] - iy))
            if t is not None:
                retarget[iid] = t[0]
                engaged[t[0]] = engaged.get(t[0], 0) + 1

    parked = [z for z in inters if st["roles"].get(z[0]) == "park"]

    # Commit parked rounds to strikers breaking through.
    urgent = sorted([t for t in tracks if t[3] < 44.0 and t[0] not in engaged
                     and t[0] != gun], key=lambda t: t[3])
    launches_left = cap
    for t in urgent:
        if parked and (len(parked) > 1 or t[3] < 36.0):
            p = min(parked, key=lambda z: math.hypot(z[2] - t[1], z[3] - t[2]))
            parked.remove(p)
            st["roles"][p[0]] = "commit"
            retarget[p[0]] = t[0]
            engaged[t[0]] = 1
        elif t[3] < 36.0 and stock > 0 and launches_left > 0:
            intercept.append(t[0])
            st["intents"].append((t[0], "commit", tick))
            engaged[t[0]] = 1
            stock -= 1
            launches_left -= 1

    # Expiring parked rounds: spend them rather than lose them.
    for p in list(parked):
        if p[4] >= life - 4:
            t = nearest_unengaged(p[2], p[3])
            if t is None and tracks:
                t = min(tracks, key=lambda z: z[3])
            if t is not None:
                parked.remove(p)
                st["roles"][p[0]] = "commit"
                retarget[p[0]] = t[0]
                engaged[t[0]] = engaged.get(t[0], 0) + 1

    # Ping-pong the remaining parked rounds around the asset.
    for iid, tgt, ix, iy, age in parked:
        far = [t for t in tracks if t[3] > 38.0 and math.hypot(t[1] - ix, t[2] - iy) > 24.0]
        if not far:
            far = [t for t in tracks if math.hypot(t[1] - ix, t[2] - iy) > 22.0]
        if not far:
            continue
        d = math.hypot(ix, iy)
        if d > 4.0:
            ux, uy = -ix / d, -iy / d
            best = max(far, key=lambda t: (t[1] * ux + t[2] * uy) / max(t[3], 1e-6))
        else:
            best = max(far, key=lambda t: math.hypot(t[1] - ix, t[2] - iy))
        retarget[iid] = best[0]

    minr = min([t[3] for t in tracks]) if tracks else 1e9
    reserve_left = max(0, RESERVE - st["parked_req"])

    # Early long-range launches, one round per unengaged track.
    early_avail = max(0, stock - reserve_left)
    cands = sorted([t for t in tracks if t[0] not in engaged and t[3] > 60.0],
                   key=lambda t: t[3])
    for t in cands:
        if launches_left <= 0 or early_avail <= 0:
            break
        intercept.append(t[0])
        st["intents"].append((t[0], "early", tick))
        engaged[t[0]] = 1
        early_avail -= 1
        stock -= 1
        launches_left -= 1

    # Launch the parked reserve once the ring approaches.
    if minr < 130.0:
        while launches_left > 0 and stock > 0 and st["parked_req"] < RESERVE and tracks:
            far = max(tracks, key=lambda t: t[3])
            intercept.append(far[0])
            st["intents"].append((far[0], "park", tick))
            st["parked_req"] += 1
            stock -= 1
            launches_left -= 1

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
