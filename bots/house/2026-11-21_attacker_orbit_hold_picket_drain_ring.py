"""
Idea: Hold the whole striker force in a tangential orbit just outside radar range, spend a cheap decoy picket first to drain interceptor launches and lifetimes, then release every orbiting drone at once so they arrive together from all bearings.

Why this holds up across the defender field:
- Most defenders fire on unknown tracks, or on cohorts timed to radar entry (the
  cohort/edge/deadline/ledger/annealed/greedy families). A synchronized ring
  already drives these to ~0.13 defender score. This bot keeps that ring. The
  ring forms outside radar (orbit radius ~477 > 450), so these defenders see no
  launch timing, bearing clustering or cohort fingerprint. They only see one
  simultaneous inbound shell.
- The strikers and the main-wave decoys share speed and spacing. They are mixed
  around the circle and only become distinguishable at 150 range. That leaves an
  ID-gated defender about 37 ticks and 2 launches per tick against more than 30
  tracks. Pure gun and nearest-first defenders saturate even faster.
- Defenders that park or hover interceptors (doublecover, pingpong, loiter pool)
  are the ring's weak spot. A 16-decoy picket from the opening bearings goes in
  first. It draws parked or eager interceptors and runs down their 90-tick
  lifetimes. Interceptors sent at the picket that are retargeted after reveal
  are already far from the shell that arrives later.
- Bearing spacing keeps neighbours apart by more than the blast radius over most
  of the approach, so one interceptor rarely kills two drones.
- The bot is deterministic, uses only the standard library and does constant
  work per drone per tick. Every action is guarded so that it never raises.
"""
import math

NAME = "orbit_hold_picket_drain_ring"
ROLE = "attacker"

_S = {}


def reset(seed=None):
    _S.clear()
    _S["drain_ids"] = set()
    _S["main_queue"] = []
    _S["drain_queue"] = []
    _S["built"] = False
    _S["released"] = False


def _build(rules, budget):
    sc = float(rules.get("striker_cost", 2.0))
    dc = float(rules.get("decoy_cost", 0.5))
    n_drain = 16
    n_main_decoy = 12
    rem = budget - (n_drain + n_main_decoy) * dc
    n_str = int(rem // sc) if sc > 0 else 0
    if n_str < 6:
        n_drain, n_main_decoy = 4, 0
        n_str = int((budget - n_drain * dc) // sc) if sc > 0 else 0
    left = budget - n_str * sc - (n_drain + n_main_decoy) * dc
    if dc > 0 and left >= dc:
        n_main_decoy += int(left // dc)
    # Drain picket: evenly spaced, offset by half a step from the main ring.
    dq = []
    for i in range(n_drain):
        b = 2 * math.pi * (i + 0.5) / max(1, n_drain)
        dq.append({"type": "decoy", "bearing": b})
    # Main ring: strikers and decoys interleaved evenly around the circle.
    total = n_str + n_main_decoy
    types = []
    acc = 0.0
    ratio = n_main_decoy / float(total) if total else 0.0
    for i in range(total):
        acc += ratio
        if acc >= 1.0 - 1e-9:
            types.append("decoy")
            acc -= 1.0
        else:
            types.append("striker")
    # Fix the count if floating-point drift produced a mismatch.
    while types.count("striker") > n_str:
        types[types.index("striker")] = "decoy"
    while types.count("striker") < n_str and "decoy" in types:
        types[types.index("decoy")] = "striker"
    mq = []
    for i in range(total):
        b = 2 * math.pi * i / max(1, total) + 0.05
        mq.append({"type": types[i], "bearing": b})
    _S["drain_queue"] = dq
    _S["main_queue"] = mq
    _S["built"] = True


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "built" not in _S:
        reset(0)
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    if not _S["built"]:
        _build(rules, budget)

    cap = int(rules.get("attacker_launches_per_tick", 4))
    radar = float(rules.get("radar_range", 450.0))
    spawn = float(rules.get("spawn_radius", 490.0))
    orbit_r = max(radar + 22.0, min(spawn - 8.0, radar + 30.0))
    sc = float(rules.get("striker_cost", 2.0))
    dc = float(rules.get("decoy_cost", 0.5))
    asset = obs.get("asset", {}) or {}
    apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(apos[0]), float(apos[1])

    drones = obs.get("drones", []) or []

    # Every drone visible while the drain queue is still launching is a picket.
    if _S["drain_queue"] or tick <= 1:
        if not _S.get("main_started"):
            for d in drones:
                _S["drain_ids"].add(d.get("id"))

    launch = []
    spend = 0.0
    while len(launch) < cap:
        if _S["drain_queue"]:
            item = _S["drain_queue"][0]
        elif _S["main_queue"]:
            item = _S["main_queue"][0]
            _S["main_started"] = True
        else:
            break
        cost = sc if item["type"] == "striker" else dc
        if spend + cost > budget + 1e-9:
            # Cannot afford it: drop the item so the queue never stalls.
            if _S["drain_queue"]:
                _S["drain_queue"].pop(0)
            else:
                _S["main_queue"].pop(0)
            continue
        spend += cost
        launch.append({"type": item["type"], "bearing": float(item["bearing"])})
        if _S["drain_queue"]:
            _S["drain_queue"].pop(0)
        else:
            _S["main_queue"].pop(0)
    if launch and not _S["drain_queue"] and any(True for _ in launch):
        pass

    # Release the shell once the main ring is fully launched and has had time to
    # settle into orbit, with a hard deadline that leaves time to arrive.
    if not _S["released"]:
        if (not _S["main_queue"] and tick >= 90) or tick >= 200:
            _S["released"] = True

    steer = {}
    step = 30.0
    for d in drones:
        did = d.get("id")
        if did is None or did in _S["drain_ids"]:
            continue
        pos = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        dx, dy = float(pos[0]) - ax, float(pos[1]) - ay
        if _S["released"]:
            steer[did] = None
            continue
        r = math.hypot(dx, dy)
        if r < radar - 5.0:
            # Already inside radar range for some reason; let it continue in.
            steer[did] = None
            continue
        ang = math.atan2(dy, dx)
        dang = step / max(orbit_r, 1.0)
        na = ang + dang
        steer[did] = [ax + orbit_r * math.cos(na), ay + orbit_r * math.sin(na)]

    return {"launch": launch, "steer": steer}
