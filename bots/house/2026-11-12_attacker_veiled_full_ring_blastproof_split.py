"""Idea: Hide a full 30-striker ring outside radar range, spaced so no blast can kill two, then release it in two depth-staggered half-rings so the 20-round magazine runs dry while strikers are still arriving.

Target: the magazine and cluster accounting in convergent_deadline_packer.

The packer assumes it wins by firing one blast at several strikers ("cluster rule") and by
never wasting rounds on decoys. Two things in its replays show where that fails:

- Both close calls end with stock_left == 0. In the first, 26 strikers drained all 20 rounds
  and 3 strikers hit together at tick 141. In the second, 30 strikers drained the magazine
  and 5 strikers hit together at tick 448. The gun adds only 2 to 4 kills because it fires
  once per tick. The binding limit is magazine count, not launch scheduling.
- In the hidden-orbit replay, 16 decoys (8 budget) hit the asset harmlessly. The packer never
  fires at identified decoys, and in-range unknowns cannot exist because gun range (100) is
  shorter than id range (150). Decoys therefore buy nothing against it.

So this bot puts the entire budget into strikers and stages them invisibly at radius ~475,
beyond the radar's 450. Each striker holds a slot 12 degrees from its neighbours. Half the
ring is released 3 ticks after the other half. That gives a ~12-unit radial offset, and
neighbouring strikers stay more than one blast radius apart down to the commit radius. The
cluster rule then finds nothing and the packer gets at most one kill per round.

Noisy tracks can still make the packer believe two strikers share a blast. It then marks the
second as collateral-covered and stops serving it. If an interceptor closes in while another
striker is within 18 units, both strikers jink apart, so that collateral is never actually
paid. The result is 20 rounds at pk 0.85, about 17 kills, plus a few gun kills, against 30
strikers arriving almost together. Three hits are enough.

Bearing convention is calibrated from one probe launch, so the ring spacing is correct
whatever angle convention the engine uses.
"""

import math

NAME = "veiled_full_ring_blastproof_split"
ROLE = "attacker"

_S = {}


def reset(seed=None):
    _S.clear()


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


_MAPS = {
    "rad": lambda b: b,
    "rad_cmp": lambda b: math.pi / 2 - b,
    "rad_cw": lambda b: -b,
    "deg": lambda b: math.radians(b),
    "deg_cmp": lambda b: math.pi / 2 - math.radians(b),
    "deg_cw": lambda b: -math.radians(b),
}


def _to_bearing(theta, m):
    if m == "rad":
        return _wrap(theta)
    if m == "rad_cmp":
        return _wrap(math.pi / 2 - theta)
    if m == "rad_cw":
        return _wrap(-theta)
    if m == "deg":
        return math.degrees(theta) % 360.0
    if m == "deg_cmp":
        return math.degrees(math.pi / 2 - theta) % 360.0
    if m == "deg_cw":
        return math.degrees(-theta) % 360.0
    return theta


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    st = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    ax, ay = float(ax), float(ay)
    drones = obs.get("drones", []) or []
    inters = obs.get("interceptors", []) or []

    cost = float(rules.get("striker_cost", 2.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    spawn_r = float(rules.get("spawn_radius", 490.0))
    radar_r = float(rules.get("radar_range", 450.0))
    total_budget = float(rules.get("attacker_budget", 60.0))
    if spawn_r > radar_r + 10:
        stage_r = max(radar_r + 12.0, min(spawn_r - 6.0, (radar_r + spawn_r) / 2.0 + 5.0))
    else:
        stage_r = spawn_r

    if "init" not in st:
        st["init"] = True
        st["map"] = None
        st["probed"] = False
        st["probe_tick"] = None
        st["N"] = max(1, int(total_budget / cost + 1e-9))
        st["slots"] = []        # slot angles
        st["next"] = 0          # next slot to launch
        st["launched"] = set()  # slot indices launched
        st["assigned"] = {}     # drone id -> slot
        st["taken"] = set()
        st["release"] = None
        st["launch_end"] = None

    launch = []
    steer = {}

    # Calibration of bearing convention.
    if st["map"] is None:
        if not st["probed"]:
            st["probed"] = True
            st["probe_tick"] = tick
            if budget >= cost:
                return {"launch": [{"type": "striker", "bearing": 1.0}], "steer": {}}
            return {"launch": [], "steer": {}}
        if drones:
            d0 = drones[0]
            p = d0.get("pos") or [0.0, 0.0]
            th = math.atan2(float(p[1]) - ay, float(p[0]) - ax)
            best, bd = "rad", None
            for k, f in _MAPS.items():
                dd = abs(_wrap(f(1.0) - th))
                if bd is None or dd < bd:
                    best, bd = k, dd
            st["map"] = best
            th0 = th
        elif tick - st["probe_tick"] > 5:
            st["map"] = "rad"
            th0 = 1.0
        else:
            return {"launch": [], "steer": {}}
        N = st["N"]
        st["slots"] = [_wrap(th0 + 2 * math.pi * k / N) for k in range(N)]
        st["next"] = 1
        st["launched"].add(0)
        if drones:
            st["assigned"][drones[0].get("id")] = 0
            st["taken"].add(0)

    N = st["N"]
    slots = st["slots"]

    # Launch remaining slots.
    b = budget
    while st["next"] < N and len(launch) < cap and b >= cost - 1e-9:
        k = st["next"]
        launch.append({"type": "striker", "bearing": _to_bearing(slots[k], st["map"])})
        st["launched"].add(k)
        st["next"] += 1
        b -= cost
    if st["launch_end"] is None and (st["next"] >= N or b < cost - 1e-9):
        st["launch_end"] = tick

    # Assign drones to slots.
    pos = {}
    for d in drones:
        did = d.get("id")
        p = d.get("pos") or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        pos[did] = (x, y)
        if did not in st["assigned"]:
            th = math.atan2(y, x)
            best, bd = None, None
            for k in st["launched"]:
                if k in st["taken"]:
                    continue
                dd = abs(_wrap(slots[k] - th))
                if bd is None or dd < bd:
                    best, bd = k, dd
            if best is None:
                best = len(st["assigned"]) % N
            st["assigned"][did] = best
            st["taken"].add(best)

    # Release decision.
    if st["release"] is None and st["launch_end"] is not None:
        ready = True
        for did, (x, y) in pos.items():
            k = st["assigned"].get(did, 0)
            px, py = stage_r * math.cos(slots[k]), stage_r * math.sin(slots[k])
            if math.hypot(x - px, y - py) > 10.0:
                ready = False
                break
        if (ready and tick >= st["launch_end"] + 2) or tick >= st["launch_end"] + 40:
            st["release"] = tick

    ipos = []
    for it in inters:
        try:
            ipos.append((float(it[0]) - ax, float(it[1]) - ay))
        except Exception:
            pass

    rel = st["release"]
    for did, (x, y) in pos.items():
        k = st["assigned"].get(did, 0)
        go = rel is not None and tick >= rel + (3 if k % 2 else 0)
        if not go:
            px, py = stage_r * math.cos(slots[k]), stage_r * math.sin(slots[k])
            steer[did] = [px + ax, py + ay]
            continue
        # Released: jink apart from close neighbours when an interceptor is near.
        wp = None
        if ipos:
            di = min(math.hypot(x - ix, y - iy) for ix, iy in ipos)
            if di < 50.0:
                nn, nd = None, None
                for oid, (ox, oy) in pos.items():
                    if oid == did:
                        continue
                    dd = math.hypot(ox - x, oy - y)
                    if nd is None or dd < nd:
                        nn, nd = (ox, oy), dd
                if nn is not None and nd < 18.0:
                    r = math.hypot(x, y)
                    if r > 30.0:
                        ux, uy = x - nn[0], y - nn[1]
                        un = math.hypot(ux, uy)
                        if un < 1e-6:
                            ux, uy, un = -y, x, max(r, 1e-6)
                        ux, uy = ux / un, uy / un
                        inx, iny = -x / r, -y / r
                        wx = x + ux * 20.0 + inx * 8.0
                        wy = y + uy * 20.0 + iny * 8.0
                        wp = [wx + ax, wy + ay]
        steer[did] = wp

    return {"launch": launch, "steer": steer}
