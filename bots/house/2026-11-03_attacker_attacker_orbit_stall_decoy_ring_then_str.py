"""Idea: Release a cheap decoy ring so the defender launches its whole magazine, then park the decoys in an orbit just outside its collapse radius so every loitering interceptor times out without firing, and only then send the strikers.

Weakness targeted
-----------------
2026-10-02_defender_loiter_then_collapse launches all 20 interceptors as soon
as it sees a ring moving inward (around W ~ 175). It parks them over the asset
and fires them together only when the wave reaches W ~ 47. Its interceptors
live for 90 ticks. A loiterer that never sees the wave reach the trigger
radius never fires, and it simply ages out.

The pairing that shows it is 2026-10-23_attacker_bait_count_then_clear_sky_wave
vs 2026-10-02_defender_loiter_then_collapse (mean score_defender 0.034). On
seed 0 the defender launched all 20 interceptors at a 16-decoy ring. It got
1 decoy kill, had stock_left 0, and the later striker wave breached with only
the gun opposing it. That attacker still let its decoys dive into the asset.
If even one of them had been a striker, the defender's collapse would have
taken part of the ring.

This bot does not let the bait reach the trigger radius. The 16 decoys fly in
as a ring, then switch to a circular orbit at radius 70. That is inside
identification range but outside the W ~ 47 collapse point. They stay there
for the rest of the match, so the parked interceptors burn through their
lifetime with no commit. The attacker watches the interceptor list. Once it
has seen interceptors and the sky is clear again (or a fallback tick passes),
it spends the remaining 52 budget on 26 strikers. They come in on spread
bearings, 4 per tick, and only the gun is left to stop them.
"""

import math

NAME = "attacker_orbit_stall_decoy_ring_then_striker_flood"
ROLE = "attacker"

N_DECOYS = 16
ORBIT_R = 70.0
ORBIT_START_R = 80.0
ORBIT_LEAD = 0.35          # radians ahead on the orbit circle
FALLBACK_LAUNCH_TICK = 230
LATEST_LAUNCH_TICK = 420

_state = {}


def reset(seed=0):
    _state.clear()
    _state.update({
        "decoys_sent": 0,
        "strikers_sent": 0,
        "seen_interceptors": False,
        "clear_ticks": 0,
        "striker_phase": False,
        "decoy_ids": set(),
    })


reset(0)


def _rules(obs):
    r = obs.get("rules") or {}
    return r if isinstance(r, dict) else {}


def act(obs):
    action = {"launch": [], "steer": {}}
    try:
        if not _state:
            reset(0)
        tick = int(obs.get("tick", 0))
        budget = float(obs.get("budget", 0.0))
        rules = _rules(obs)
        per_tick = int(rules.get("attacker_launches_per_tick", 4))
        s_cost = float(rules.get("striker_cost", 2.0))
        d_cost = float(rules.get("decoy_cost", 0.5))
        asset = obs.get("asset") or {}
        apos = asset.get("pos") or [0.0, 0.0]
        ax, ay = float(apos[0]), float(apos[1])

        drones = obs.get("drones") or []
        interceptors = obs.get("interceptors") or []

        # Track the interceptor state.
        if len(interceptors) > 0:
            _state["seen_interceptors"] = True
            _state["clear_ticks"] = 0
        elif _state["seen_interceptors"]:
            _state["clear_ticks"] += 1

        launches = []
        remaining = budget

        # Phase 1: send the decoy ring.
        while (_state["decoys_sent"] < N_DECOYS and len(launches) < per_tick
               and remaining >= d_cost):
            k = _state["decoys_sent"]
            bearing = (2.0 * math.pi * k) / N_DECOYS
            launches.append({"type": "decoy", "bearing": bearing})
            _state["decoys_sent"] += 1
            remaining -= d_cost

        # Phase 2: decide when the strikers go.
        if not _state["striker_phase"] and _state["decoys_sent"] >= N_DECOYS:
            if ((_state["seen_interceptors"] and _state["clear_ticks"] >= 3
                 and tick >= 120)
                    or tick >= FALLBACK_LAUNCH_TICK):
                _state["striker_phase"] = True
        if tick >= LATEST_LAUNCH_TICK:
            _state["striker_phase"] = True

        if _state["striker_phase"]:
            n_total = 26
            while len(launches) < per_tick and remaining >= s_cost:
                k = _state["strikers_sent"]
                bearing = (2.0 * math.pi * (k % n_total)) / n_total + 0.12
                launches.append({"type": "striker", "bearing": bearing})
                _state["strikers_sent"] += 1
                remaining -= s_cost

        action["launch"] = launches

        # Steering: decoys orbit at ORBIT_R once they get close enough.
        steer = {}
        for d in drones:
            try:
                if d.get("type") != "decoy":
                    continue
                pos = d.get("pos") or [0.0, 0.0]
                dx, dy = float(pos[0]) - ax, float(pos[1]) - ay
                r = math.hypot(dx, dy)
                if r <= ORBIT_START_R or d.get("waypoint") is not None:
                    th = math.atan2(dy, dx) + ORBIT_LEAD
                    steer[d.get("id")] = [ax + ORBIT_R * math.cos(th),
                                          ay + ORBIT_R * math.sin(th)]
            except Exception:
                continue
        action["steer"] = steer
    except Exception:
        return {"launch": [], "steer": {}}
    return action
