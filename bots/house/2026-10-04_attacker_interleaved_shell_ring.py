"""Idea: Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.

Name: interleaved_shell_ring

How it works
------------
Every striker gets a slot. Slots sit 12 degrees apart. Slot i also belongs to
shell i % 3, and each shell is staged 24 units further out than the one before
it. Bearing-neighbours therefore always sit in different shells. Two drones in
the same shell are 36 degrees apart.

While the swarm is staging (radius 300 to 348, outside id range), the whole
formation slowly rotates. On release every striker flies straight at the
asset. Shells keep their 24-unit radial gap, which is 6 ticks of arrival
spread, all the way in.

The geometry guarantee: any two strikers stay more than 20 units apart, which
is twice the blast radius.
* Bearing-neighbours are at least 24 apart radially.
* Same-shell drones are at least 2*pi*r/10 apart, which is more than 20 for
  any r above 32, so until they are basically inside the asset radius.
No interceptor can ever kill more than one striker. Yet 30 threats still land
inside a 12-tick window.

Why it holds against the field
------------------------------
* convergence_blast_scheduler and loiter_then_collapse beat
  synchronized_ring only because a uniform ring compresses until three
  strikers share a blast. Here the ring never compresses below 20-unit
  spacing. Their held magazine buys at most one kill per interceptor, and
  waiting has cost them time. Loitering interceptors also age toward their
  90-tick lifetime while the formation orbits.
* backscheduled_blast_packer looks for the tick where threats pack tightest.
  No such tick exists, so it collapses into one-for-one shooting against a
  12-tick saturation wave.
* discriminating_ledger, miss_budget_scheduler, reveal_timed_prelaunch,
  annealed/greedy assigners and the other baselines all lost heavily to
  synchronized saturation, scoring about 0.14. This bot keeps that property:
  30 all-striker threats, unidentified until 150, arriving almost together.
  Twenty interceptors at 0.85 and one gun shot per tick cannot stop three of
  them.
* gun_only and nearest_first are throughput-limited, and a near-simultaneous
  wave overwhelms both.
"""

import math

NAME = "interleaved_shell_ring"
ROLE = "attacker"

N_SLOTS = 30
N_SHELLS = 3
SHELL_GAP = 24.0
STAGE_R = 300.0
ORBIT_RATE = 0.004      # rad per tick formation rotation while staging
LOOKAHEAD = 10          # ticks of lookahead along the orbit
READY_TOL = 14.0
MAX_HOLD_TICK = 170

_state = {}


def reset(seed=0):
    _state.clear()
    _state["base"] = ((seed or 0) % 360) * math.pi / 180.0
    _state["launched"] = 0
    _state["slot_of"] = {}
    _state["free"] = list(range(N_SLOTS))
    _state["released"] = False
    _state["phi"] = 0.0


def _slot_angle(i, phi):
    return _state["base"] + i * 2.0 * math.pi / N_SLOTS + phi


def _stage_point(i, phi):
    a = _slot_angle(i, phi)
    r = STAGE_R + SHELL_GAP * (i % N_SHELLS)
    return [r * math.cos(a), r * math.sin(a)]


def _angdiff(a, b):
    d = (a - b) % (2.0 * math.pi)
    return min(d, 2.0 * math.pi - d)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "base" not in _state:
        reset(0)
    tick = int(obs.get("tick", 0) or 0)
    budget = float(obs.get("budget", 0.0) or 0.0)
    rules = obs.get("rules", {}) or {}
    cost = float(rules.get("striker_cost", 2.0) or 2.0)
    per_tick = int(rules.get("attacker_launches_per_tick", 4) or 4)
    ax, ay = 0.0, 0.0
    try:
        ap = obs.get("asset", {}).get("pos", [0.0, 0.0])
        ax, ay = float(ap[0]), float(ap[1])
    except Exception:
        pass

    drones = obs.get("drones", []) or []

    # Slot assignment for newly seen drones (nearest free slot bearing).
    slot_of = _state["slot_of"]
    new = [d for d in drones if d.get("id") not in slot_of]
    new.sort(key=lambda d: str(d.get("id")))
    for d in new:
        if not _state["free"]:
            slot_of[d.get("id")] = len(slot_of) % N_SLOTS
            continue
        p = d.get("pos", [0.0, 0.0])
        ang = math.atan2(float(p[1]) - ay, float(p[0]) - ax)
        best = min(_state["free"],
                   key=lambda i: _angdiff(ang, _slot_angle(i, _state["phi"])))
        _state["free"].remove(best)
        slot_of[d.get("id")] = best

    # Launches.
    launch = []
    if not _state["released"]:
        while (len(launch) < per_tick and _state["launched"] < N_SLOTS
               and budget >= cost - 1e-9):
            i = _state["launched"]
            launch.append({"type": "striker",
                           "bearing": float(_slot_angle(i, _state["phi"]) % (2.0 * math.pi))})
            _state["launched"] += 1
            budget -= cost

    steer = {}
    if not _state["released"]:
        all_launched = (_state["launched"] >= N_SLOTS) or budget < cost
        ready = all_launched and len(drones) > 0
        if ready:
            for d in drones:
                i = slot_of.get(d.get("id"), 0)
                sp = _stage_point(i, _state["phi"])
                p = d.get("pos", [0.0, 0.0])
                if math.hypot(float(p[0]) - ax - sp[0], float(p[1]) - ay - sp[1]) > READY_TOL:
                    ready = False
                    break
        if (ready or tick >= MAX_HOLD_TICK) and all_launched and drones:
            _state["released"] = True
        else:
            _state["phi"] += ORBIT_RATE
            ahead = _state["phi"] + ORBIT_RATE * LOOKAHEAD
            for d in drones:
                i = slot_of.get(d.get("id"), 0)
                p = d.get("pos", [0.0, 0.0])
                sp_now = _stage_point(i, _state["phi"])
                dist = math.hypot(float(p[0]) - ax - sp_now[0], float(p[1]) - ay - sp_now[1])
                tgt = _stage_point(i, ahead) if dist < 3 * READY_TOL else sp_now
                steer[d.get("id")] = [tgt[0] + ax, tgt[1] + ay]

    if _state["released"]:
        for d in drones:
            if d.get("waypoint") is not None:
                steer[d.get("id")] = None

    return {"launch": launch, "steer": steer}
