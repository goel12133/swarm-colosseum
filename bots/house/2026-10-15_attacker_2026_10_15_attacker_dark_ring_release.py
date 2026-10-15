"""Idea: Park every striker just outside radar range and hold it there, invisible, until decoys have drawn the defender's whole interceptor magazine, then release all strikers at once from equal radius so they arrive together.

Weakness targeted: nearest_first commits one interceptor to the nearest unengaged
track and never checks what that track is. It only fires at tracks it can see, and
radar range is 450 while drones spawn at 490. Strikers waiting at radius ~475 are
never tracks, so they can never draw an interceptor. Decoys flood in first, and the
defender spends all 20 interceptors (4 credits each) on 0.5-credit decoys.

The strikers are then released from the same radius at the same time. They cross the
100-unit gun band within about 25 ticks of each other. The single gun can engage only
one target per tick, so it can stop only a few of them, and three hits break the asset.

Pairing that shows it: 2026-10-06_attacker_parked_ring_magazine_drain vs nearest_first
(mean score_defender 0.058). In seed 0 the defender ended with stock_left 0, and 19 of
its 20 interceptors killed decoys while 20 strikers impacted. This bot keeps that
magazine drain and adds two things: strikers stay fully outside radar until the drain
is confirmed, and a reserve decoy wave is sent if the magazine is not yet empty.
"""

import math

NAME = "2026-10-15_attacker_dark_ring_release"
ROLE = "attacker"

PARK_R = 475.0
N_STRIKERS = 20
FIRST_DECOYS = 24

_s = {}


def reset(seed=0):
    _s.clear()
    _s.update({
        "strikers_launched": 0,
        "decoys_launched": 0,
        "decoy_wave_target": FIRST_DECOYS,
        "park": {},
        "released": False,
        "prev_icount": 0,
        "est_launched": 0,
        "spent": 0.0,
    })


reset()


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = obs.get("tick", 0)
    budget = float(obs.get("budget", 0.0))
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    stock = int(rules.get("interceptor_stock", 20))
    max_ticks = int(rules.get("max_ticks", 600))
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]

    drones = obs.get("drones", []) or []
    icount = len(obs.get("interceptors", []) or [])
    if icount > _s["prev_icount"]:
        _s["est_launched"] += icount - _s["prev_icount"]
    _s["prev_icount"] = icount

    launches = []
    slots = per_tick

    # Strikers first; they spawn outside radar and stay there.
    while slots > 0 and _s["strikers_launched"] < N_STRIKERS and budget >= s_cost:
        k = _s["strikers_launched"]
        b = 2.0 * math.pi * k / N_STRIKERS
        launches.append({"type": "striker", "bearing": b})
        _s["strikers_launched"] += 1
        budget -= s_cost
        slots -= 1

    # Decoy waves, spread around the ring to dilute blast double-kills.
    if _s["strikers_launched"] >= N_STRIKERS or budget < s_cost:
        while (slots > 0 and _s["decoys_launched"] < _s["decoy_wave_target"]
               and budget >= d_cost):
            k = _s["decoys_launched"]
            b = 2.0 * math.pi * ((k * 0.618034) % 1.0)
            launches.append({"type": "decoy", "bearing": b})
            _s["decoys_launched"] += 1
            budget -= d_cost
            slots -= 1

    decoys_alive = sum(1 for d in drones if d.get("type") == "decoy")
    wave_done = _s["decoys_launched"] >= _s["decoy_wave_target"]

    if not _s["released"]:
        drained = _s["est_launched"] >= stock
        quiet = icount == 0
        if drained and quiet:
            _s["released"] = True
        elif wave_done and decoys_alive == 0 and quiet and tick > 20:
            # Magazine may not be empty: send another wave if we can afford it.
            if budget >= d_cost * 4:
                extra = int(min(16, budget // d_cost))
                _s["decoy_wave_target"] += extra
            else:
                _s["released"] = True
        if tick >= max_ticks - 150:
            _s["released"] = True

    steer = {}
    for d in drones:
        if d.get("type") != "striker":
            continue
        did = d.get("id")
        if _s["released"]:
            steer[did] = None
            continue
        pk = _s["park"].get(did)
        if pk is None:
            px, py = (d.get("pos") or [ax + PARK_R, ay])[:2]
            dx, dy = px - ax, py - ay
            r = math.hypot(dx, dy) or 1.0
            pk = [ax + dx / r * PARK_R, ay + dy / r * PARK_R]
            _s["park"][did] = pk
        steer[did] = [pk[0], pk[1]]

    return {"launch": launches, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
