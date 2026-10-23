"""Idea: Count the defender's interceptor launches from the attacker's own view of the sky and hold every striker on the pad until the bait-drawn magazine is seen to be spent or aged out, then send one interleaved striker wave.

Weakness attacked
-----------------
2026-10-06_defender_contracting_ring_blaster commits its whole magazine as
soon as tracks begin moving inward. It does not check what those tracks are,
because type is only revealed inside id_range 150. It then parks the
interceptors near the origin, waiting for a contracting ring. Interceptors
live 90 ticks. A drone needs about 116 ticks to fly from the 490 spawn ring
to the asset. So a cheap first wave makes the magazine launch and then
expire, or spend itself on decoys, before anything worth hitting arrives.

The pairing that shows it is dark_ring_release vs contracting_ring_blaster,
mean score_defender 0.054. In seed 0 the defender launched 20 interceptors
for 2 decoy kills (stock_left 0). The later striker wave met only the gun,
which killed 3 strikers, and the asset was breached at tick 296.

What this bot adds
------------------
dark_ring_release releases strikers on a fixed timer. This bot instead
watches obs["interceptors"] and adds up every increase in the airborne
count, which estimates how many interceptors the defender has launched. It
releases strikers only once that estimate shows the magazine committed and
the sky is clear. A fallback deadline still leaves time to reach the asset
before max_ticks.

Bearings follow a golden-angle sequence, so each tick's batch of four is
spread around the ring. Late blasts and the gun cannot pick off a cluster.
"""

import math

NAME = "bait_count_then_clear_sky_wave"
ROLE = "attacker"

_GOLDEN = 137.50776405
_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "decoys_sent": 0,
        "strikers_sent": 0,
        "k": 0,
        "prev_inter": 0,
        "est_launched": 0,
        "release": False,
        "seen_inter": False,
    })


reset(0)


def _bearing():
    k = _state["k"]
    _state["k"] = k + 1
    return (k * _GOLDEN + 7.0) % 360.0


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    stock = int(rules.get("interceptor_stock", 20))
    life = int(rules.get("interceptor_lifetime", 90))
    max_ticks = int(rules.get("max_ticks", 600))
    spawn_r = float(rules.get("spawn_radius", 490.0))
    speed = float(rules.get("striker_speed", 4.0)) or 4.0
    asset_r = float(rules.get("asset_radius", 25.0))
    total_budget = float(rules.get("attacker_budget", 60.0))

    inters = obs.get("interceptors", []) or []
    n_now = len(inters)
    if n_now > 0:
        _state["seen_inter"] = True
    if n_now > _state["prev_inter"]:
        _state["est_launched"] += n_now - _state["prev_inter"]
    _state["prev_inter"] = n_now

    n_bait = 16
    if total_budget < 40:
        n_bait = max(4, int(total_budget * 0.25 / max(d_cost, 1e-6)))

    launches = []

    # Phase 1: cheap bait ring.
    if _state["decoys_sent"] < n_bait:
        while (len(launches) < per_tick and _state["decoys_sent"] < n_bait
               and budget >= d_cost):
            launches.append({"type": "decoy", "bearing": _bearing()})
            budget -= d_cost
            _state["decoys_sent"] += 1
        return {"launch": launches, "steer": {}}

    # Phase 2: wait for the magazine to be committed and the sky to clear.
    if not _state["release"]:
        flight = int((spawn_r - asset_r) / speed) + 1
        n_strikers_left = int(budget // s_cost) if s_cost > 0 else 0
        launch_ticks = (n_strikers_left + per_tick - 1) // max(per_tick, 1)
        hard_deadline = max_ticks - flight - launch_ticks - 30
        soft_deadline = min(hard_deadline, 140)
        spent = _state["est_launched"] >= int(0.75 * stock)
        clear = n_now == 0
        if spent and clear:
            _state["release"] = True
        elif tick >= soft_deadline and clear:
            _state["release"] = True
        elif tick >= soft_deadline + life // 2:
            _state["release"] = True
        elif tick >= hard_deadline:
            _state["release"] = True

    if _state["release"]:
        while len(launches) < per_tick and budget >= s_cost:
            launches.append({"type": "striker", "bearing": _bearing()})
            budget -= s_cost
            _state["strikers_sent"] += 1
        # Leftover change becomes decoys mixed into the wave.
        while (len(launches) < per_tick and budget < s_cost
               and budget >= d_cost):
            launches.append({"type": "decoy", "bearing": _bearing()})
            budget -= d_cost

    return {"launch": launches, "steer": {}}
