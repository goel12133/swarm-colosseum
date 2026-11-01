"""Idea: Park the whole main wave on an orbit just outside radar range, spend a cheap decoy cohort to draw early fire, then drop in a ring of depth-staggered shells that are invisible until release and impossible to blast more than one at a time.

Why it holds up across the defender field:
- Eager, unknown-shooting defenders (nearest_first, greedy_value_model,
  annealed_assignment*, the ledger and packer families). They see a 12-decoy
  bait cohort first, at radar range and with no type yet. They spend
  interceptors on it while it is still far outside id range. The main wave is
  still hidden in orbit at r=478, beyond radar range 450 plus noise, so it
  cannot be engaged before release.
- Cohort-fingerprinting and screen-skipping defenders (first_cohort_screen_skip,
  birth_cohort_lull_splitter, radar_edge_cohort_timing, etc.). The bait costs
  only 6 of the 60 budget, so ignoring it costs us little. The main wave
  mixes strikers and decoys inside every shell and every bearing
  neighbourhood. Neither birth time nor position nor cohort separates the
  types before the 150 id range.
- Class-gated and id-only magazine keepers. 24 strikers enter id range
  almost together, each needing a separate interceptor. 20 rounds at
  pk 0.85 plus a single gun stream cannot clear enough of them before 3 reach
  the asset.
- Convergence and blast packers (convergence_blast_scheduler,
  cluster_blast_column_breaker, contracting_ring_blaster, origin_pingpong).
  Adjacent bearings always sit in different shells, 24 units apart radially.
  Same-shell drones are at least two slots apart in angle. One blast of
  radius 10 rarely catches two drones until they are inside the asset radius.
- Hover-bank and loiter-pool defenders. Their parked interceptors expire
  (lifetime 90) while we orbit unseen. Our release time is fixed by our own
  clock, not by their posture.
- Gun-only and layered defenders. The three shells arrive within about
  12 ticks of each other. The gun's one shot per tick inside range 100 sees
  roughly 20 or more targets in that window.
"""
import math

NAME = "hidden_orbit_bait_then_depth_shell_ring"
ROLE = "attacker"

R_ORBIT = 478.0
OMEGA = 4.0 / R_ORBIT
N_BAIT = 12
N_MAIN = 36
SHELL_GAP = 6
BASE_RELEASE = 90

_S = {}


def _shell_of(slot):
    if slot is None:
        return 0
    return (slot + slot // 3) % 3


def reset(seed=0):
    global _S
    queue = []
    for i in range(N_BAIT):
        b = 2 * math.pi * (i + 0.5) / N_BAIT
        queue.append({"type": "decoy", "role": "bait", "slot": None, "base": b})
    for s in range(N_MAIN):
        t = "decoy" if s % 3 == 0 else "striker"
        queue.append({"type": t, "role": "main", "slot": s,
                      "base": 2 * math.pi * s / N_MAIN})
    _S = {"queue": queue, "pending": [], "known": {}, "main_start": None,
          "main_done": None, "release": None}


reset(0)


def _angdiff(a, b):
    d = (a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if not _S:
        reset(0)
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    cap = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    drones = obs.get("drones", []) or []
    known = _S["known"]

    # match newly appeared drones to the launch requests sent last tick
    pending = _S["pending"]
    for d in drones:
        did = d.get("id")
        if did in known:
            continue
        pos = d.get("pos", [0, 0])
        ang = math.atan2(pos[1], pos[0])
        best, bi = None, -1
        for i, p in enumerate(pending):
            if p["type"] != d.get("type"):
                continue
            df = _angdiff(ang, p["bearing"])
            if best is None or df < best:
                best, bi = df, i
        if bi >= 0:
            p = pending.pop(bi)
            known[did] = {"role": p["role"], "slot": p["slot"]}
        else:
            known[did] = {"role": "main", "slot": None}
    _S["pending"] = []

    # launches
    launch = []
    queue = _S["queue"]
    while queue and len(launch) < cap:
        item = queue[0]
        cost = s_cost if item["type"] == "striker" else d_cost
        if budget + 1e-9 < cost:
            # try to fit a cheaper item instead of stalling
            alt = None
            for j, it in enumerate(queue):
                c = s_cost if it["type"] == "striker" else d_cost
                if budget + 1e-9 >= c:
                    alt = j
                    break
            if alt is None:
                queue.clear()
                break
            item = queue.pop(alt)
            cost = s_cost if item["type"] == "striker" else d_cost
        else:
            queue.pop(0)
        if item["role"] == "main":
            if _S["main_start"] is None:
                _S["main_start"] = tick
            b = item["base"] + OMEGA * (tick - _S["main_start"])
        else:
            b = item["base"]
        b = math.atan2(math.sin(b), math.cos(b))
        budget -= cost
        launch.append({"type": item["type"], "bearing": b})
        _S["pending"].append({"type": item["type"], "role": item["role"],
                              "slot": item["slot"], "bearing": b})
    if not queue and _S["main_done"] is None and _S["main_start"] is not None:
        _S["main_done"] = tick

    if _S["release"] is None and _S["main_done"] is not None:
        _S["release"] = max(BASE_RELEASE, _S["main_done"] + 10)
    release = _S["release"]
    force = tick >= 400

    steer = {}
    for d in drones:
        did = d.get("id")
        info = known.get(did)
        if info is None or info["role"] != "main":
            continue
        shell = _shell_of(info["slot"])
        if force or (release is not None and tick >= release + shell * SHELL_GAP):
            if d.get("waypoint") is not None:
                steer[did] = None
            continue
        pos = d.get("pos", [0, 0])
        ang = math.atan2(pos[1], pos[0]) + 0.03
        steer[did] = [R_ORBIT * math.cos(ang), R_ORBIT * math.sin(ang)]

    return {"launch": launch, "steer": steer}
