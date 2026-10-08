"""Idea: Stage thirty strikers just outside radar range on three interleaved shells, each rotated 12 degrees and set 12 units deeper than the last, so no two strikers are ever inside one blast radius. Then release them all on one tick.

How it works
------------
* Slots. There are 30 slots in 3 shells of 10. Inside a shell the slots are 36
  degrees apart. Shell k is rotated 12*k degrees and staged at radius
  456 + 12*k. All three shells sit outside radar range (450), so the defender
  sees nothing during staging.
* Staging. Strikers launch 4 per tick on their slot bearings. Each one is
  steered to its slot and held there with a small tangential dither. Drones are
  matched to slots by angle each tick, so the bearing convention does not
  matter.
* Release. When every striker is on station (or at the tick-60 failsafe), every
  waypoint is cleared on the same tick. All strikers then fly straight in.
  Shells reach the asset 3 ticks apart, and the whole wave arrives within about
  6 ticks.

Why this holds up against the whole field
-----------------------------------------
* Blast-packing defenders (convergence_blast_scheduler,
  backscheduled_blast_packer, cluster_blast_column_breaker,
  contracting_ring_blaster, loiter_then_collapse). These win by waiting until
  strikers squeeze within one 10-unit blast.
  - Neighbours in angle are in different shells, so they are always at least
    12 units apart along the radius.
  - Strikers in the same shell are 36 degrees apart. At the asset edge (r=25)
    their chord is about 15.5 units.
  - So no pair ever fits inside one blast. Each interceptor kills at most one
    striker, and the 20-round magazine kills at most about 17.
  - Waiting for a squeeze that never comes only leaves less time to shoot.
* Ledger, value-model, annealing and nearest-first defenders. These already
  fire one-for-one, so they cannot shoot fast enough. At 2 launches per tick
  against a 6-tick arrival window, and with no early radar picture, they also
  hit the magazine limit. The gun gets roughly one shot per tick for about 30
  ticks. That is not enough to stop the 13 or more strikers left over, and only
  3 need to get through.
* Shell-by-shell defenders (dither / parked magazine). The shells are so close
  together that no defender can clear one shell and reload its picture before
  the next arrives.
* No decoys. Every point of budget buys a striker, and type reveal (id range
  150) gives the defender nothing to filter out.
"""

import math
import random

NAME = "staggered_trishell_blast_denial"
ROLE = "attacker"

N_STRIKERS = 30
N_SHELLS = 3
PER_SHELL = 10
BASE_R = 456.0
SHELL_GAP = 12.0

_state = {}


def reset(seed=0):
    rng = random.Random(seed)
    rot = rng.uniform(0.0, 2.0 * math.pi)
    slots = []
    # interleave shells so early launches already spread out
    for j in range(PER_SHELL):
        for k in range(N_SHELLS):
            ang = rot + j * (2.0 * math.pi / PER_SHELL) + k * (2.0 * math.pi / (PER_SHELL * N_SHELLS))
            ang = math.atan2(math.sin(ang), math.cos(ang))
            slots.append((ang, BASE_R + SHELL_GAP * k))
    _state.clear()
    _state["slots"] = slots
    _state["launched"] = 0
    _state["assign"] = {}
    _state["released"] = False


def _angdiff(a, b):
    d = a - b
    return abs(math.atan2(math.sin(d), math.cos(d)))


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "slots" not in _state:
        reset(0)
    slots = _state["slots"]
    tick = obs.get("tick", 0)
    budget = float(obs.get("budget", 0.0))
    asset = obs.get("asset", {}).get("pos", [0.0, 0.0])
    ax, ay = float(asset[0]), float(asset[1])
    rules = obs.get("rules", {}) or {}
    cap = int(rules.get("attacker_launches_per_tick", 4))
    cost = float(rules.get("striker_cost", 2.0))

    action = {"launch": [], "steer": {}}

    # launches
    n = min(cap, N_STRIKERS - _state["launched"], int(budget // cost) if cost > 0 else 0)
    for _ in range(max(0, n)):
        ang = slots[_state["launched"]][0]
        action["launch"].append({"type": "striker", "bearing": ang})
        _state["launched"] += 1

    drones = [d for d in obs.get("drones", []) if d.get("type", "striker") == "striker"]
    try:
        drones.sort(key=lambda d: str(d["id"]))
    except Exception:
        pass

    assign = _state["assign"]
    alive_ids = set(d["id"] for d in drones)
    for did in list(assign.keys()):
        if did not in alive_ids:
            assign.pop(did, None)

    if _state["released"]:
        return action

    used = set(assign.values())
    for d in drones:
        if d["id"] in assign:
            continue
        px, py = float(d["pos"][0]) - ax, float(d["pos"][1]) - ay
        a = math.atan2(py, px)
        best, bd = None, 1e9
        for i, (sa, sr) in enumerate(slots):
            if i in used:
                continue
            v = _angdiff(a, sa)
            if v < bd:
                bd, best = v, i
        if best is not None:
            assign[d["id"]] = best
            used.add(best)

    # readiness check
    ready = _state["launched"] >= N_STRIKERS and len(drones) >= N_STRIKERS - 0
    targets = {}
    for d in drones:
        i = assign.get(d["id"])
        if i is None:
            continue
        sa, sr = slots[i]
        tx, ty = ax + sr * math.cos(sa), ay + sr * math.sin(sa)
        dist = math.hypot(float(d["pos"][0]) - tx, float(d["pos"][1]) - ty)
        targets[d["id"]] = (tx, ty, sa, dist)
        if dist > 12.0:
            ready = False
    if len(targets) < len(drones):
        ready = False

    if ready or tick >= 60:
        _state["released"] = True
        for d in drones:
            action["steer"][d["id"]] = None
        return action

    sign = 1.0 if (tick // 2) % 2 == 0 else -1.0
    for d in drones:
        t = targets.get(d["id"])
        if t is None:
            continue
        tx, ty, sa, dist = t
        if dist > 10.0:
            action["steer"][d["id"]] = [tx, ty]
        else:
            txn, tyn = -math.sin(sa), math.cos(sa)
            action["steer"][d["id"]] = [tx + sign * 10.0 * txn, ty + sign * 10.0 * tyn]
    return action
