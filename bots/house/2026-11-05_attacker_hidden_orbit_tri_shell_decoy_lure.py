"""
Idea: Strikers launch just outside radar range and orbit there unseen while a decoy ring draws interceptors in, then they dive as three angle-interleaved, time-staggered shells, so no single blast can catch two of them.

Why it holds up across the defender field:
- Long-range and eager defenders (greedy, annealed, nearest_first, and the
  cohort/fingerprint "full magazine" family):
  - Only the 12-decoy ring is visible for the first ~50 ticks.
  - Defenders that fire at unknown tracks spend interceptors on decoys.
  - That leaves too little magazine for the 27 strikers that follow.
- ID-gated and deadline defenders (class_gated, id_only, deadline_queue,
  ledger types):
  - They ignore the decoys.
  - They then face 27 strikers against 20 interceptors (pk 0.85) plus a gun.
  - The gun only has about 25 ticks of range.
  - So at least 3 strikers (30 hp) are expected to get through.
- Blast-packing and convergence schedulers (convergent_deadline_packer,
  convergence_blast_scheduler, cluster_blast_column_breaker):
  - Strikers sit on 27 evenly spaced bearings.
  - Each shell of 9 is 40 degrees apart.
  - Shells arrive 6 ticks (24 units) apart, more than the blast diameter.
  - So no single blast can catch two strikers, even near the asset where
    paths converge.
- Parked, hover, and loiter defenders (parked_hover_ring_doublecover,
  loiter_then_collapse, loiter_pool, origin_pingpong):
  - These are the only ones that resist a plain synchronized ring.
  - Here they park interceptors when the decoys appear.
  - Interceptors only live 90 ticks.
  - The strikers arrive more than 150 ticks after the decoys are detected.
  - So the parked screen has expired or has been spent on decoys before the
    real wave arrives.
- Hiding: until the dive, every striker orbits at about 478 units, outside
  the 450-unit radar. Defenders that profile or fingerprint cohorts see nothing
  to work with.
- Robustness: the bearing convention (radians or degrees, orientation) is
  measured from the first launch instead of assumed.
"""

import math

NAME = "hidden_orbit_tri_shell_decoy_lure"
ROLE = "attacker"

TWO_PI = 2.0 * math.pi
ORBIT_R = 478.0
N_DECOYS = 12
N_STRIKERS = 27
N_SHELLS = 3
DIVE_TICK = 55
SHELL_LAG = 6

_S = {}


def _wrap(a):
    while a > math.pi:
        a -= TWO_PI
    while a < -math.pi:
        a += TWO_PI
    return a


def _idkey(i):
    s = str(i)
    return (len(s), s)


def reset(seed=None):
    _S.clear()
    _S["mapped"] = False
    _S["scale"] = 1.0       # bearing units -> radians
    _S["sgn"] = 1.0
    _S["offset"] = 0.0
    _S["probe_ids"] = []
    _S["decoys_left"] = N_DECOYS
    _S["decoy_queue"] = []
    _S["striker_queue"] = []  # list of (slot_angle, shell)
    _S["pending"] = []        # (expected_angle, shell) launched, not yet seen
    _S["role"] = {}           # drone id -> ("decoy",) or ("striker", shell)
    _S["seen"] = set()
    _S["omega"] = 4.0 / ORBIT_R
    _S["first_tick"] = None
    base = math.pi / N_STRIKERS
    q = []
    for j in range(N_STRIKERS):
        q.append((base + TWO_PI * j / N_STRIKERS, j % N_SHELLS))
    # Interleave the launch order so that shells are mixed.
    _S["striker_queue"] = q


reset()


def _to_bearing(angle):
    b = _S["sgn"] * (angle - _S["offset"]) / _S["scale"]
    if _S["scale"] != 1.0:
        b = b % 360.0
    else:
        b = b % TWO_PI
    return b


def _act(obs):
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    sc = float(rules.get("striker_cost", 2.0))
    dc = float(rules.get("decoy_cost", 0.5))
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    spd = float(rules.get("striker_speed", 4.0))
    spawn_r = float(rules.get("spawn_radius", 490.0))
    _S["omega"] = spd / max(ORBIT_R, 1.0)
    if _S["first_tick"] is None:
        _S["first_tick"] = tick
    t0 = _S["first_tick"]
    rel = tick - t0

    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])

    drones = obs.get("drones", []) or []
    launches = []
    steer = {}

    # --- Probe the bearing convention ---
    if rel == 0 and not _S["probe_ids"]:
        probes = [0.0, math.pi / 2.0, math.pi, 1.5 * math.pi]
        for b in probes:
            if budget >= dc and _S["decoys_left"] > 0:
                launches.append({"type": "decoy", "bearing": b})
                budget -= dc
                _S["decoys_left"] -= 1
        _S["probe_ids"] = ["pending"]
        return {"launch": launches, "steer": steer}

    if not _S["mapped"]:
        ds = sorted(drones, key=lambda d: _idkey(d.get("id")))
        if len(ds) >= 2:
            angs = []
            for d in ds[:4]:
                p = d.get("pos", [1.0, 0.0])
                angs.append(math.atan2(float(p[1]) - ay, float(p[0]) - ax))
            spread = max(abs(_wrap(a - angs[0])) for a in angs)
            if spread < 0.3:
                _S["scale"] = math.pi / 180.0
                d1 = _wrap(angs[-1] - angs[0])
                _S["sgn"] = 1.0 if d1 >= 0 else -1.0
            else:
                _S["scale"] = 1.0
                d1 = _wrap(angs[1] - angs[0])
                _S["sgn"] = 1.0 if d1 >= 0 else -1.0
            _S["offset"] = angs[0]
            _S["mapped"] = True
            for d in ds:
                _S["role"][d.get("id")] = ("decoy",)
                _S["seen"].add(d.get("id"))
        elif rel >= 4:
            _S["mapped"] = True
            for d in drones:
                _S["role"][d.get("id")] = ("decoy",)
                _S["seen"].add(d.get("id"))
        else:
            return {"launch": [], "steer": {}}
        # Build the remaining decoy queue, offset between the probe bearings.
        n = _S["decoys_left"]
        _S["decoy_queue"] = [_S["offset"] + math.pi / 4.0 + TWO_PI * i / max(n, 1)
                             for i in range(n)]

    # --- Assign roles to newly seen drones ---
    for d in drones:
        did = d.get("id")
        if did in _S["seen"]:
            continue
        _S["seen"].add(did)
        if d.get("type") == "striker" and _S["pending"]:
            p = d.get("pos", [1.0, 0.0])
            a = math.atan2(float(p[1]) - ay, float(p[0]) - ax)
            best, bi = None, 0
            for i, (ea, sh) in enumerate(_S["pending"]):
                e = abs(_wrap(a - ea))
                if best is None or e < best:
                    best, bi = e, i
            ea, sh = _S["pending"].pop(bi)
            _S["role"][did] = ("striker", sh)
        elif d.get("type") == "striker":
            _S["role"][did] = ("striker", N_SHELLS - 1)
        else:
            _S["role"][did] = ("decoy",)

    # --- Launches: decoys first, then strikers ---
    n_launch = 0
    while n_launch < per_tick and _S["decoy_queue"] and budget >= dc:
        a = _S["decoy_queue"].pop(0)
        launches.append({"type": "decoy", "bearing": _to_bearing(a)})
        budget -= dc
        n_launch += 1
    while n_launch < per_tick and _S["striker_queue"] and budget >= sc:
        s, sh = _S["striker_queue"].pop(0)
        a = s + _S["omega"] * rel
        launches.append({"type": "striker", "bearing": _to_bearing(a)})
        _S["pending"].append((a, sh))
        budget -= sc
        n_launch += 1

    # --- Steering ---
    for d in drones:
        did = d.get("id")
        role = _S["role"].get(did, ("decoy",))
        if role[0] != "striker":
            continue
        sh = role[1]
        if rel >= DIVE_TICK + SHELL_LAG * sh:
            steer[did] = None
            continue
        p = d.get("pos", [spawn_r, 0.0])
        px, py = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(px, py)
        if r < 1.0:
            steer[did] = None
            continue
        a = math.atan2(py, px)
        wr = ORBIT_R + (ORBIT_R - r) * 3.0
        wr = max(ORBIT_R - 10.0, min(ORBIT_R + 25.0, wr))
        wa = a + 30.0 / r
        steer[did] = [ax + wr * math.cos(wa), ay + wr * math.sin(wa)]

    return {"launch": launches, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
