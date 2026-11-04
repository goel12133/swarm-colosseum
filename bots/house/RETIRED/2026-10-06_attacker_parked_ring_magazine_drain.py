"""Idea: Burn the magazine with a cheap leading decoy wave, hold every striker on a parking orbit just outside radar range, then release them all at once behind a thin decoy escort.

Weakness targeted: nearest_first commits interceptors and gun shots on range alone, with no
regard for track class. Its result in the decoy_screen vs nearest_first pairing shows this:
mean score_defender 0.107. In seed 0 it spent 13 of its 20 interceptors on 0.5-credit decoys,
ended with stock_left 0, and was breached at tick 124.

This bot pushes that weakness further in four steps:
  1. An opening wave of 20 decoys flies straight in. These are the only visible tracks, so
     nearest_first fires its whole magazine at them, two per tick, before any striker is seen.
  2. Escort decoys and all strikers are steered onto an orbit at radius 470. That is outside
     the 450 radar range, so the defender cannot see them while it spends interceptors.
  3. After the magazine has had time to drain, the escorts are released first and the
     strikers a few ticks later. Every striker then converges together from evenly spread
     bearings.
  4. The escorts stay slightly closer to the asset than the strikers. A nearest-first gun
     spends its early shots on them, and the strikers arrive together, which overloads a gun
     that fires once per tick.

Bearings are assumed to be in radians.
"""
import math

NAME = "parked_ring_magazine_drain"
ROLE = "attacker"

N_LEAD_DECOYS = 20
N_ESCORT_DECOYS = 10
PARK_RADIUS = 470.0
RELEASE_TICK = 30
STRIKER_DELAY = 3

_state = {}


def reset(seed=None):
    _state.clear()
    _state["queue"] = None
    _state["decoys_seen"] = 0
    _state["role"] = {}
    _state["launched_decoy"] = 0
    _state["launched_striker"] = 0


def _build_queue(budget, rules):
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    q = []
    b = budget
    for _ in range(N_LEAD_DECOYS):
        if b >= d_cost:
            q.append("decoy")
            b -= d_cost
    n_esc = 0
    for _ in range(N_ESCORT_DECOYS):
        if b - d_cost >= s_cost * 3:
            q.append("decoy")
            b -= d_cost
            n_esc += 1
    n_str = int(b // s_cost) if s_cost > 0 else 0
    q.extend(["striker"] * n_str)
    b -= n_str * s_cost
    while b >= d_cost:
        q.append("decoy")
        b -= d_cost
    _state["n_striker_total"] = max(1, n_str)
    return q


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "role" not in _state:
        reset()
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]

    if _state["queue"] is None:
        _state["queue"] = _build_queue(budget, rules)

    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    cap = int(rules.get("attacker_launches_per_tick", 4))

    launches = []
    q = _state["queue"]
    spent = 0.0
    while q and len(launches) < cap:
        t = q[0]
        c = s_cost if t == "striker" else d_cost
        if budget - spent < c - 1e-9:
            break
        q.pop(0)
        spent += c
        if t == "striker":
            k = _state["launched_striker"]
            _state["launched_striker"] += 1
            bearing = 2.0 * math.pi * k / _state["n_striker_total"]
        else:
            k = _state["launched_decoy"]
            _state["launched_decoy"] += 1
            bearing = 2.0 * math.pi * ((k * 0.618034) % 1.0)
        launches.append({"type": t, "bearing": bearing})

    role = _state["role"]
    drones = sorted(obs.get("drones", []) or [], key=lambda d: str(d.get("id")))
    for d in drones:
        did = d.get("id")
        if did in role:
            continue
        if d.get("type") == "striker":
            role[did] = "striker"
        else:
            if _state["decoys_seen"] < N_LEAD_DECOYS:
                role[did] = "lead"
            else:
                role[did] = "escort"
            _state["decoys_seen"] += 1

    rel_escort = tick >= RELEASE_TICK and not q
    rel_striker = tick >= RELEASE_TICK + STRIKER_DELAY and not q

    steer = {}
    for d in drones:
        did = d.get("id")
        r = role.get(did)
        if r == "lead":
            continue
        released = rel_striker if r == "striker" else rel_escort
        if released:
            if d.get("waypoint") is not None:
                steer[did] = None
            continue
        pos = d.get("pos") or [0.0, 0.0]
        dx, dy = pos[0] - ax, pos[1] - ay
        ang = math.atan2(dy, dx)
        tgt = ang + 0.06
        steer[did] = [ax + PARK_RADIUS * math.cos(tgt),
                      ay + PARK_RADIUS * math.sin(tgt)]

    return {"launch": launches, "steer": steer}
