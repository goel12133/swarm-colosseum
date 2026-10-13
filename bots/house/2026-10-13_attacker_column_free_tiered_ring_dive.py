"""Idea: Every drone holds on its own bearing just outside radar range, then the whole ring dives together, with neighbouring bearings in three depth tiers about 14 units apart, so no bearing carries a stacked column and no two drones ever sit within one blast radius.

Plan: 27 strikers and 12 decoys (60 budget) on 39 evenly spaced bearings.
Decoys are spread evenly through the ring. Drones launch at 4 per tick. Each
holds just outside radar range (radii 462, 476 and 490, set by tier) by
oscillating radially with waypoints. Once every drone is in place, all
waypoints are cleared on the same tick.

The engine's bearing convention is learned from two probe launches on tick 0
(radians or degrees, which direction, where zero is). After that, each drone is
matched by its observed angle to the nearest free slot of its own type, so a
wrong guess about convention cannot scatter the ring.

How it fares against each kind of defender:
- Nearest-first, gun-only and layered: the shell-ring attackers lose to these
  because shells arrive one after another. Here the whole ring lands inside
  about 7 ticks. One gun shot per tick and 2 launches per tick cannot clear a
  wave that arrives all at once.
- Cluster/column breakers, which beat depth-interleave: there are no columns
  to break. Each bearing carries exactly one drone.
- Convergence-blast, contracting-ring and loiter-collapse: these wait for drones
  to bunch up. Angular neighbours are always at least 14 units apart in
  radius, and drones three slots apart in the same tier only come within 10
  units inside about r=30, right at the asset. A single interceptor almost
  never kills two drones.
- Discriminating and ID-gated defenders: they ignore the decoys, which cost
  only 6 budget. Even if all 20 interceptors are fired, they kill about 17 of
  27 strikers, and the gun's short window cannot cover the remaining 10.
  Three hits destroy the asset.
- Eager and annealed assigners: they see 39 unidentified tracks appear at once
  at 450 range and spend interceptors on the 12 cheap decoys.
- Magazine-drain-resistant and hover-bank defenders: there is no trickle to
  wait out. The defender's first look at the attack is the attack itself.
"""
import math

NAME = "column_free_tiered_ring_dive"
ROLE = "attacker"

N_STRIKE = 27
N_DECOY = 12
N = N_STRIKE + N_DECOY
HOLD_R = [462.0, 476.0, 490.0]
GO_DEADLINE = 48

_st = {}


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a <= -math.pi:
        a += 2 * math.pi
    return a


def reset(seed=None):
    _st.clear()
    types = []
    for i in range(N):
        d = (i * N_DECOY) // N != ((i + 1) * N_DECOY) // N
        types.append("decoy" if d else "striker")
    # Fix count exactly
    nd = types.count("decoy")
    if nd != N_DECOY:
        types = ["striker"] * N
        for k in range(N_DECOY):
            types[(k * N) // N_DECOY + 1 if (k * N) // N_DECOY + 1 < N else 0] = "decoy"
    _st["types"] = types
    _st["tier"] = [i % 3 for i in range(N)]
    # launch order: inner tiers first (longest travel to hold point)
    order = sorted(range(N), key=lambda i: (_st["tier"][i], i))
    _st["probe"] = [0, None]
    _st["launch_order"] = order
    _st["launched"] = set()
    _st["map"] = None  # (a0, sign*scale)
    _st["probe_ids"] = None
    _st["assign"] = {}
    _st["slot_used"] = set()
    _st["go"] = False
    _st["spent"] = 0.0


def _slot_angle(k):
    a0 = _st["map"][0] if _st["map"] else 0.0
    return a0 + 2 * math.pi * k / N


def _bearing_for(k):
    if _st["map"] is None:
        return 2 * math.pi * k / N
    a0, f = _st["map"]
    tgt = _slot_angle(k)
    return _wrap(tgt - a0) / f


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "types" not in _st:
        reset(0)
    tick = obs.get("tick", 0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    sc = float(rules.get("striker_cost", 2.0))
    dc = float(rules.get("decoy_cost", 0.5))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    drones = obs.get("drones", []) or []
    types = _st["types"]

    launch = []
    steer = {}

    # Probe slot j about 1.5 rad from slot 0
    j = max(1, int(round(1.5 / (2 * math.pi / N))))
    _st["probe"][1] = j

    # Learn bearing mapping
    if _st["map"] is None and _st["probe_ids"] is None and drones and 0 in _st["launched"]:
        ds = sorted(drones, key=lambda d: str(d.get("id")) if not isinstance(d.get("id"), (int, float)) else "%012d" % int(d.get("id")))
        if len(ds) >= 2:
            p0, p1 = ds[0]["pos"], ds[1]["pos"]
            a0 = math.atan2(p0[1] - ay, p0[0] - ax)
            a1 = math.atan2(p1[1] - ay, p1[0] - ax)
            d = _wrap(a1 - a0)
            br = 2 * math.pi * j / N
            sgn = 1.0 if d >= 0 else -1.0
            if abs(abs(d) - br) < 0.25:
                f = sgn
            elif abs(abs(d) - math.radians(br)) < 0.02:
                f = sgn * math.pi / 180.0
            else:
                f = 1.0
            _st["map"] = (a0, f)
        else:
            if drones:
                p0 = drones[0]["pos"]
                _st["map"] = (math.atan2(p0[1] - ay, p0[0] - ax), 1.0)
        _st["probe_ids"] = True

    # Launches
    if tick == 0 and not _st["launched"]:
        for k in (0, j):
            c = sc if types[k] == "striker" else dc
            if budget >= c - 1e-9:
                launch.append({"type": types[k], "bearing": float(2 * math.pi * k / N)})
                _st["launched"].add(k)
                budget -= c
    elif _st["map"] is not None or tick >= 3:
        if _st["map"] is None:
            _st["map"] = (0.0, 1.0)
        for k in _st["launch_order"]:
            if len(launch) >= cap:
                break
            if k in _st["launched"]:
                continue
            c = sc if types[k] == "striker" else dc
            if budget < c - 1e-9:
                continue
            launch.append({"type": types[k], "bearing": float(_bearing_for(k))})
            _st["launched"].add(k)
            budget -= c

    # Assign drones to slots
    assign = _st["assign"]
    used = _st["slot_used"]
    if _st["map"] is not None:
        for d in drones:
            did = d.get("id")
            if did in assign:
                continue
            p = d["pos"]
            ang = math.atan2(p[1] - ay, p[0] - ax)
            best, bd = None, 1e9
            for k in range(N):
                if k in used or types[k] != d.get("type"):
                    continue
                e = abs(_wrap(ang - _slot_angle(k)))
                if e < bd:
                    bd, best = e, k
            if best is not None:
                assign[did] = best
                used.add(best)

    all_launched = len(_st["launched"]) >= N or budget < dc - 1e-9
    if not _st["go"] and all_launched and tick >= 2:
        ready = True
        for d in drones:
            k = assign.get(d.get("id"))
            if k is None:
                continue
            p = d["pos"]
            r = math.hypot(p[0] - ax, p[1] - ay)
            hr = HOLD_R[_st["tier"][k]]
            ang = math.atan2(p[1] - ay, p[0] - ax)
            if abs(r - hr) > 6.0 or abs(_wrap(ang - _slot_angle(k))) * r > 8.0:
                ready = False
                break
        if ready or tick >= GO_DEADLINE:
            _st["go"] = True

    for d in drones:
        did = d.get("id")
        if _st["go"]:
            steer[did] = None
            continue
        k = assign.get(did)
        p = d["pos"]
        r = math.hypot(p[0] - ax, p[1] - ay)
        if k is None:
            ang = math.atan2(p[1] - ay, p[0] - ax)
            hr = 476.0
        else:
            ang = _slot_angle(k)
            hr = HOLD_R[_st["tier"][k]]
        cx, cy = ax + hr * math.cos(ang), ay + hr * math.sin(ang)
        if math.hypot(p[0] - cx, p[1] - cy) > 6.0:
            # head toward hold point, pushed beyond so it is never "reached"
            dx, dy = cx - p[0], cy - p[1]
            n = math.hypot(dx, dy) or 1.0
            steer[did] = [cx + dx / n * 30.0, cy + dy / n * 30.0]
        else:
            rr = hr + 60.0 if r < hr else hr - 60.0
            steer[did] = [ax + rr * math.cos(ang), ay + rr * math.sin(ang)]

    return {"launch": launch, "steer": steer}
