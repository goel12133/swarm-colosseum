"""Idea: Hide every striker in a tangential orbit just outside radar range while a decoy-only ring stages a fake synchronized release, then launch all strikers at once only after the attacker sees the defender's interceptor count fall to zero.

Target: 2026-10-02_defender_loiter_then_collapse.

Weakness
--------
The defender empties its whole magazine as soon as it sees a ring released from
about radius 190. It does not wait to learn what the ring is made of. Its
loiterers have a lifetime of 90 and are all committed on one tick. That leaves
nothing for a second wave. The defender checks neither drone class nor whether
more raiders are still coming.

The pairing bait_count_then_clear_sky_wave vs loiter_then_collapse shows this
(mean score_defender 0.034). In the seed-0 replay, 20 interceptors were spent on
a decoy ring and only 1 decoy was killed. All 15 decoy impacts land at ticks
117-120 with stock_left 0. The strikers then arrive at tick 295 into an empty
sky, and the gun alone stops just 2 of them.

What this bot does differently
------------------------------
* 16 decoys form a rotating ring at radius 190 and are released on the same
  tick. This copies the synchronized-ring signature that sets off the
  defender's full launch.
* 26 strikers are never seen before they commit. Each one is steered every tick
  to a point slightly ahead of it on a circle of about radius 485. That is
  outside radar range (450), so the defender has no tracks to save stock for.
* The strikers are released by observation, not by a timer. The attacker
  watches obs.interceptors and waits until interceptors have been seen and the
  count has then stayed at zero for several ticks. At that point the magazine
  has been spent or has expired. A tick fallback releases them anyway.
* All strikers are released on the same tick from the same radius. They reach
  gun range together, so the single gun gets about one tick per striker. Three
  hits on the asset are enough.
"""

import math

NAME = "attacker_radar_shadow_orbit_decoy_drain"
ROLE = "attacker"

_S = {}


def reset(seed=0):
    _S.clear()
    _S.update({
        "deg": None,          # bearing units detection
        "probe": None,        # (bearing radians, tick) of first launch
        "decoys": [],         # ordered decoy ids
        "strikers": [],       # ordered striker ids
        "decoy_launched": 0,
        "decoys_released": False,
        "decoy_release_tick": None,
        "strikers_released": False,
        "max_ic": 0,
        "zero_ic_ticks": 0,
        "seen_ids": set(),
    })


reset(0)

N_DECOYS = 16
HOLD_R = 190.0
ORBIT_R = 485.0


def _bearing(rad):
    if _S["deg"]:
        return math.degrees(rad)
    return rad


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    drones = obs.get("drones", []) or []
    ics = obs.get("interceptors", []) or []
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    radar = float(rules.get("radar_range", 450.0))
    spawn_r = float(rules.get("spawn_radius", 490.0))
    orbit_r = min(ORBIT_R, spawn_r - 3.0)
    if orbit_r < radar + 10.0:
        orbit_r = max(radar + 10.0, spawn_r - 3.0)

    # Register drones by type, in order of first appearance.
    by_id = {}
    for d in drones:
        did = d.get("id")
        by_id[did] = d
        if did in _S["seen_ids"]:
            continue
        _S["seen_ids"].add(did)
        if d.get("type") == "decoy":
            _S["decoys"].append(did)
        else:
            _S["strikers"].append(did)

    # Detect whether bearings are in degrees or radians, from the first drone.
    if _S["deg"] is None and _S["probe"] is not None and drones:
        b, _t = _S["probe"]
        d = drones[0]
        px, py = d.get("pos", [0, 0])[:2]
        ang = math.atan2(py - ay, px - ax)
        diff_rad = abs((ang - b + math.pi) % (2 * math.pi) - math.pi)
        bd = math.radians(b)
        diff_deg = abs((ang - bd + math.pi) % (2 * math.pi) - math.pi)
        _S["deg"] = diff_deg + 1e-9 < diff_rad

    launch = []
    steer = {}

    # ---- launches ----
    slots = per_tick
    while slots > 0 and _S["decoy_launched"] < N_DECOYS and budget >= d_cost:
        k = _S["decoy_launched"]
        b = 2 * math.pi * k / N_DECOYS + 0.37
        if _S["probe"] is None:
            _S["probe"] = (b, tick)
        launch.append({"type": "decoy", "bearing": _bearing(b)})
        _S["decoy_launched"] += 1
        budget -= d_cost
        slots -= 1
    if _S["decoy_launched"] >= N_DECOYS:
        k = len(_S["strikers"]) + sum(1 for l in launch if l["type"] == "striker")
        while slots > 0 and budget >= s_cost and not _S["strikers_released"]:
            b = 2 * math.pi * k / 26.0 + 0.11
            launch.append({"type": "striker", "bearing": _bearing(b)})
            budget -= s_cost
            slots -= 1
            k += 1

    # ---- interceptor observation ----
    n_ic = len(ics)
    _S["max_ic"] = max(_S["max_ic"], n_ic)
    if n_ic == 0:
        _S["zero_ic_ticks"] += 1
    else:
        _S["zero_ic_ticks"] = 0

    # ---- decoy ring: hold then synchronized release ----
    live_decoys = [i for i in _S["decoys"] if i in by_id]
    if not _S["decoys_released"]:
        n = max(1, N_DECOYS)
        omega = 3.0 / HOLD_R
        all_in = len(live_decoys) >= N_DECOYS - 1 and _S["decoy_launched"] >= N_DECOYS
        for idx, did in enumerate(_S["decoys"]):
            if did not in by_id:
                continue
            a = 2 * math.pi * idx / n + 0.37 + omega * tick
            sx = ax + HOLD_R * math.cos(a)
            sy = ay + HOLD_R * math.sin(a)
            px, py = by_id[did].get("pos", [0, 0])[:2]
            if math.hypot(px - sx, py - sy) > 15.0:
                all_in = False
            a2 = a + 0.04
            steer[did] = [ax + HOLD_R * math.cos(a2), ay + HOLD_R * math.sin(a2)]
        if (all_in and tick > 20) or tick >= 140:
            _S["decoys_released"] = True
            _S["decoy_release_tick"] = tick
            for did in live_decoys:
                steer[did] = None

    # ---- strikers: shadow orbit outside radar, then release together ----
    if not _S["strikers_released"]:
        rel = False
        tdr = _S["decoy_release_tick"]
        if tdr is not None:
            drained = _S["max_ic"] > 0 and _S["zero_ic_ticks"] >= 4 and tick > tdr + 5
            idle = _S["max_ic"] == 0 and tick > tdr + 80
            if drained or idle or tick >= tdr + 160:
                rel = True
        if tick >= 420:
            rel = True
        if rel:
            _S["strikers_released"] = True
            for did in _S["strikers"]:
                if did in by_id:
                    steer[did] = None
        else:
            for did in _S["strikers"]:
                if did not in by_id:
                    continue
                px, py = by_id[did].get("pos", [0, 0])[:2]
                a = math.atan2(py - ay, px - ax)
                a2 = a + 4.0 / orbit_r
                steer[did] = [ax + orbit_r * math.cos(a2), ay + orbit_r * math.sin(a2)]

    return {"launch": launch, "steer": steer}
