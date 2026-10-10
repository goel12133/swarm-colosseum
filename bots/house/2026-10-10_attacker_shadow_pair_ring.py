"""Idea: Every striker is parked directly behind its own decoy on the same radial line, so the pair stays nose-to-tail and a range-only gun always shoots the decoy in front.

Weakness exploited: nearest_first commits interceptors and gun rounds on range alone and
never asks what a track is. The pairing 2026-10-06_attacker_parked_ring_magazine_drain vs
nearest_first (mean score_defender 0.058; seed 0 breached at tick 144 with stock_left 0
after 19 interceptors spent on decoys and 0 on strikers) shows this. The defender emptied its
whole 20-round magazine on 0.5-credit decoys, then 20 strikers walked in.

Plan:
  1. Drain: 30 decoys fly straight in on spread bearings. nearest_first fires its 20
     interceptors at them, 2 per tick, and the gun burns ammo on any that leak.
  2. Shadow park: 18 strikers hold at r=472, just outside the 450 radar. Each has a decoy
     "shield" held at r=462 on the exact same bearing.
  3. Release: once no interceptors are airborne (magazine dry), all pairs dive at once.
     Each decoy stays 10 units ahead of its striker. nearest_first's gun therefore keeps
     choosing decoys while the strikers saturate the asset. Three hits are enough.
Budget: 30*0.5 + 18*2 + 18*0.5 = 60.
"""
import math

NAME = "shadow_pair_ring"
ROLE = "attacker"

N_DRAIN = 30
N_PAIRS = 18
R_STRIKER = 472.0
R_SHIELD = 462.0
MIN_RELEASE_TICK = 45
FORCE_RELEASE_TICK = 260

_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "seen": set(),
        "drain_ids": set(),
        "striker_slot": {},
        "shield_slot": {},
        "drain_req": 0,
        "striker_req": 0,
        "shield_req": 0,
        "released": False,
        "quiet_ticks": 0,
    })


reset(0)


def _bearing(k, n, off):
    return (2.0 * math.pi * k / n + off) % (2.0 * math.pi)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    st = _state
    tick = obs.get("tick", 0)
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    drones = obs.get("drones", []) or []
    interceptors = obs.get("interceptors", []) or []

    # Assign newly appeared drones to roles, in id order.
    new = [d for d in drones if d.get("id") not in st["seen"]]
    new.sort(key=lambda d: str(d.get("id")))
    for d in new:
        did = d.get("id")
        st["seen"].add(did)
        if d.get("type") == "striker":
            st["striker_slot"][did] = len(st["striker_slot"]) % N_PAIRS
        elif len(st["drain_ids"]) < N_DRAIN and not st["striker_slot"] and not st["shield_slot"]:
            st["drain_ids"].add(did)
        else:
            st["shield_slot"][did] = len(st["shield_slot"]) % N_PAIRS

    # Launch requests: drain decoys first, then interleaved shield and striker pairs.
    launch = []
    slots = per_tick
    while slots > 0 and st["drain_req"] < N_DRAIN and budget >= d_cost:
        b = _bearing(st["drain_req"], N_DRAIN, 0.0)
        launch.append({"type": "decoy", "bearing": b})
        st["drain_req"] += 1
        budget -= d_cost
        slots -= 1
    if st["drain_req"] >= N_DRAIN:
        while slots > 0 and (st["shield_req"] < N_PAIRS or st["striker_req"] < N_PAIRS):
            if st["shield_req"] <= st["striker_req"] and st["shield_req"] < N_PAIRS:
                if budget < d_cost:
                    break
                b = _bearing(st["shield_req"], N_PAIRS, 0.1)
                launch.append({"type": "decoy", "bearing": b})
                st["shield_req"] += 1
                budget -= d_cost
            else:
                if budget < s_cost:
                    break
                b = _bearing(st["striker_req"], N_PAIRS, 0.1)
                launch.append({"type": "striker", "bearing": b})
                st["striker_req"] += 1
                budget -= s_cost
            slots -= 1

    # Release decision: wait until the magazine looks dry.
    all_launched = st["striker_req"] >= N_PAIRS and st["shield_req"] >= N_PAIRS
    if interceptors:
        st["quiet_ticks"] = 0
    else:
        st["quiet_ticks"] += 1
    if not st["released"]:
        if tick >= FORCE_RELEASE_TICK:
            st["released"] = True
        elif (all_launched and tick >= MIN_RELEASE_TICK and st["quiet_ticks"] >= 3
              and len(st["striker_slot"]) >= N_PAIRS):
            st["released"] = True

    # Steering.
    steer = {}
    for d in drones:
        did = d.get("id")
        if did in st["drain_ids"]:
            continue
        if st["released"]:
            if d.get("waypoint") is not None:
                steer[did] = None
            continue
        if did in st["striker_slot"]:
            th = _bearing(st["striker_slot"][did], N_PAIRS, 0.1)
            r = R_STRIKER
        elif did in st["shield_slot"]:
            th = _bearing(st["shield_slot"][did], N_PAIRS, 0.1)
            r = R_SHIELD
        else:
            continue
        steer[did] = [ax + r * math.cos(th), ay + r * math.sin(th)]

    return {"launch": launch, "steer": steer}
