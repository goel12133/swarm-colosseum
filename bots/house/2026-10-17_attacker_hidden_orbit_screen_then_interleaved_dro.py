"""Idea: Park the whole swarm on a hidden orbit just outside radar range, send a decoy screen in first, then drop the strikers in two angle-interleaved shells that cross the ID ring together.

Why it holds up across the defender field:
- Hidden staging: drones spawn at r=490 and orbit at r~482, outside the 450 radar.
  Every defender sees nothing until the swarm is fully built. Hover-bank and
  parked-ring defenders cannot pre-position against single arrivals, and ledger
  or scheduler defenders cannot spread their magazine over a long trickle.
- Decoy screen (16 decoys, 8 budget) goes in about 50 units ahead. Defenders that
  fire at unknowns (nearest_first, layered, eager or annealed assigners) spend
  interceptors on it. Defenders that hold fire until ID lose only that cheap bait.
- 26 strikers (52 budget) are more than the 20-round magazine at pk 0.85 plus the
  gun can stop. All strikers reach the 150 ID ring within a few ticks of each other.
  That compresses the defender's ID-then-engage window against a 2-per-tick
  launch cap.
- Blast-proof geometry: the two shells are interleaved by angle and offset about
  16 units in depth. Neighbours stay roughly 25 units or more apart down to r~60.
  One 10-unit blast, or a convergence or cluster packer, rarely kills two strikers.
- Unit-agnostic: tick-1 positions show whether bearings are radians or degrees.
  Orbit and release use only observed positions, so spacing survives either
  convention.
"""
import math

NAME = "hidden_orbit_screen_then_interleaved_drop"
ROLE = "attacker"

N_DECOY = 16
N_STRIKER = 26
ORBIT_R = 482.0
AHEAD = 0.05
DECOY_RELEASE = 14
SHELL_A_RELEASE = 27
SHELL_B_RELEASE = 31

_s = {}


def reset(seed=None):
    _s.clear()
    _s["queue"] = None
    _s["deg"] = False
    _s["checked"] = False
    _s["released"] = set()
    _s["shell"] = {}


def _build_queue():
    q = []
    off = math.pi / N_DECOY
    # first tick: maximally spread decoys (also used for unit detection)
    order = [0, 4, 8, 12, 2, 6, 10, 14, 1, 5, 9, 13, 3, 7, 11, 15]
    for i in order:
        q.append(("decoy", 2 * math.pi * i / N_DECOY + off))
    for j in range(N_STRIKER):
        q.append(("striker", 2 * math.pi * j / N_STRIKER))
    return q


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "queue" not in _s:
        reset(None)
    if _s["queue"] is None:
        _s["queue"] = _build_queue()
    tick = obs.get("tick", 0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    rules = obs.get("rules", {}) or {}
    drones = obs.get("drones", []) or []

    # unit detection from the first spread batch
    if not _s["checked"] and drones:
        sx = sy = 0.0
        n = 0
        for d in drones:
            px, py = d["pos"][0] - ax, d["pos"][1] - ay
            r = math.hypot(px, py)
            if r > 1e-6:
                sx += px / r
                sy += py / r
                n += 1
        if n >= 3:
            _s["deg"] = math.hypot(sx, sy) / n > 0.9
            _s["checked"] = True

    # launches
    launch = []
    budget = float(obs.get("budget", 0.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    costs = {"striker": float(rules.get("striker_cost", 2.0)),
             "decoy": float(rules.get("decoy_cost", 0.5))}
    q = _s["queue"]
    while q and len(launch) < cap:
        typ, b = q[0]
        if costs[typ] > budget + 1e-9:
            if typ == "striker" and budget + 1e-9 >= costs["decoy"]:
                q[0] = ("decoy", b)
                continue
            q.pop(0)
            continue
        budget -= costs[typ]
        q.pop(0)
        launch.append({"type": typ,
                       "bearing": math.degrees(b) if _s["deg"] else b})

    # shell assignment for strikers by angular order (interleaved)
    strikers = [d for d in drones if d.get("type") == "striker"]
    unassigned = [d for d in strikers if d["id"] not in _s["shell"]]
    if unassigned:
        allang = sorted(strikers, key=lambda d: math.atan2(d["pos"][1] - ay, d["pos"][0] - ax))
        for k, d in enumerate(allang):
            if d["id"] not in _s["shell"]:
                _s["shell"][d["id"]] = k % 2

    steer = {}
    for d in drones:
        did = d["id"]
        if did in _s["released"]:
            continue
        if d.get("type") == "decoy":
            rel = DECOY_RELEASE
        else:
            rel = SHELL_A_RELEASE if _s["shell"].get(did, 0) == 0 else SHELL_B_RELEASE
        if tick >= rel and not q:
            steer[did] = None
            _s["released"].add(did)
            continue
        px, py = d["pos"][0] - ax, d["pos"][1] - ay
        a = math.atan2(py, px) + AHEAD
        steer[did] = [ax + ORBIT_R * math.cos(a), ay + ORBIT_R * math.sin(a)]

    return {"launch": launch, "steer": steer}
