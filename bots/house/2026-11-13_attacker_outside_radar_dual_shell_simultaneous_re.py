"""Idea: Park the whole swarm in two depth-offset shells just outside radar range, then release every drone at once so they arrive as one blast-proof, interleaved striker/decoy wave.

Why it holds up across the defender field:
- Staging out of sight: drones spawn at radius 490 and are held at radii 462 and 488.
  Both are beyond radar range (450), so defenders see nothing while the ring fills.
  Defenders that fire early at a trickle ("prelaunch", "edge strike", "cohort
  fingerprint" types) have no early cohort to profile or pick off.
- One synchronized release: all drones enter radar within about 7 ticks of each
  other. This is the same compression that lets synchronized/phase-locked rings
  hold defenders near 0.14. It also limits the gun to roughly one burst window and
  forces the 2-per-tick interceptor cap to saturate.
- Blast-proof spacing: there are 48 evenly spaced bearings, and neighbours sit on
  alternating shells about 26 units apart in depth. One 10-unit blast almost never
  catches two drones, even while the ring converges. Cluster/convergence "packers"
  therefore get about one kill per interceptor at best.
- Budget split (24 strikers, 24 decoys = 60):
  - Against defenders that fire blind, decoys soak about half the 20 interceptors.
  - Against ID-gated defenders that wait for the 150-unit reveal, 24 strikers still
    exceed 20 interceptors x 0.85 plus gun kills. At least 3 strikers (30 hp)
    usually get through.
- Hover/loiter/parked-ring defenders gain little: the attack is a single
  simultaneous wave from all bearings, so pre-positioned interceptors cover only a
  few sectors.
- Robust to engine conventions:
  - Bearing units (radians or degrees) are detected from where the first drones appear.
  - Hold slots are tracked against the observed asset position.
  - A timeout guarantees release even if staging stalls.
"""

import math

NAME = "outside_radar_dual_shell_simultaneous_release"
ROLE = "attacker"

_N = 48
_R_SHELL = (462.0, 488.0)


def _new_state():
    slots = []
    off = math.pi / _N
    for i in range(_N):
        a = 2.0 * math.pi * i / _N + off
        k = i // 2
        if i % 2 == 0:
            typ = "striker"
            shell = k % 2
        else:
            typ = "decoy"
            shell = (k + 1) % 2
        slots.append({"type": typ, "angle": a, "r": _R_SHELL[shell]})
    return {
        "slots": slots,
        "next": 0,
        "launched": [],      # slot indices launched but not yet matched to a drone
        "assign": {},        # drone id -> slot index
        "deg": None,         # bearing unit detection
        "released": False,
        "last_new_tick": 0,
    }


_S = _new_state()


def reset(seed=None):
    global _S
    _S = _new_state()


def _angdiff(a, b):
    d = (a - b) % (2.0 * math.pi)
    if d > math.pi:
        d -= 2.0 * math.pi
    return abs(d)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    S = _S
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    ax = float(ax)
    ay = float(ay)
    drones = obs.get("drones", []) or []
    cost = {
        "striker": float(rules.get("striker_cost", 2.0)),
        "decoy": float(rules.get("decoy_cost", 0.5)),
    }
    cap = int(rules.get("attacker_launches_per_tick", 4))

    # Match newly seen drones to the slots that were launched.
    for d in drones:
        did = d.get("id")
        if did is None or did in S["assign"]:
            continue
        px, py = d.get("pos", [0.0, 0.0])[:2]
        ang = math.atan2(py - ay, px - ax)
        typ = d.get("type")
        best = None
        bestd = 1e9
        for si in S["launched"]:
            if S["slots"][si]["type"] != typ:
                continue
            dd = _angdiff(ang, S["slots"][si]["angle"])
            if dd < bestd:
                bestd = dd
                best = si
        if best is None and S["launched"]:
            best = S["launched"][0]
        if best is None:
            continue
        if S["deg"] is None:
            a_rad = S["slots"][best]["angle"]
            e_rad = _angdiff(ang, a_rad)
            e_deg = _angdiff(ang, math.radians(a_rad))
            S["deg"] = bool(e_deg + 0.05 < e_rad and e_rad > 0.3)
        S["launched"].remove(best)
        S["assign"][did] = best
        S["last_new_tick"] = tick

    # Launch the next planned slots.
    launch = []
    if not S["released"]:
        n = 0
        while n < cap and S["next"] < len(S["slots"]):
            sl = S["slots"][S["next"]]
            c = cost[sl["type"]]
            if budget + 1e-9 < c:
                break
            b = sl["angle"]
            if S["deg"]:
                b = math.degrees(b)
            launch.append({"type": sl["type"], "bearing": float(b)})
            budget -= c
            S["launched"].append(S["next"])
            S["next"] += 1
            n += 1

    steer = {}
    if S["released"]:
        return {"launch": launch, "steer": steer}

    done_launching = S["next"] >= len(S["slots"]) or budget + 1e-9 < min(cost.values())
    all_settled = True
    for d in drones:
        did = d.get("id")
        si = S["assign"].get(did)
        if si is None:
            all_settled = False
            continue
        sl = S["slots"][si]
        hx = ax + sl["r"] * math.cos(sl["angle"])
        hy = ay + sl["r"] * math.sin(sl["angle"])
        px, py = d.get("pos", [0.0, 0.0])[:2]
        dist = math.hypot(px - hx, py - hy)
        if dist > 10.0:
            all_settled = False
        if dist < 5.0:
            da = 0.02 if tick % 2 == 0 else -0.02
            hx = ax + sl["r"] * math.cos(sl["angle"] + da)
            hy = ay + sl["r"] * math.sin(sl["angle"] + da)
        steer[did] = [hx, hy]

    pending = len(S["launched"]) > 0 and tick - S["last_new_tick"] < 5
    release = (done_launching and not launch and all_settled and not pending
               and len(drones) > 0) or tick >= 90
    if release:
        S["released"] = True
        steer = {d.get("id"): None for d in drones if d.get("id") is not None}

    return {"launch": launch, "steer": steer}
