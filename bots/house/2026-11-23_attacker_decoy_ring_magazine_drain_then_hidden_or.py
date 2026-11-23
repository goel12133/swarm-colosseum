"""Idea: Send a cheap all-decoy ring first to draw out the whole interceptor magazine, while every striker waits on a hidden orbit beyond radar range, then drop the strikers in one simultaneous ring against a defender with nothing left but its gun.

Target weakness
---------------
2026-10-02_defender_loiter_then_collapse treats the first inward-moving ring it
sees as "the release". It launches its entire magazine at that ring, loiters the
interceptors over the asset, and commits every one of them on the same tick once
the wave closes to about W = 47. It keeps nothing in reserve and does not wait
for track identification. The pairing
2026-10-23_attacker_bait_count_then_clear_sky_wave vs
2026-10-02_defender_loiter_then_collapse (mean score_defender 0.034) shows the
problem. The decoy wave arrived at tick 117 to 120. By then stock_left was 0 and
all 20 interceptors were gone. The strikers came in much later, at tick 295, and
the gun alone could not stop them.

What this bot does
------------------
1. Ticks 0-4: launches 20 decoys on evenly spaced bearings (cost 10). They fly
   straight in as a closing ring, which is exactly the trigger this defender
   waits for.
2. Ticks 5-11: launches 25 strikers (cost 50). Each tick they are steered to a
   waypoint slightly ahead on a circle of radius 478. They orbit outside the
   450 radar range, so the defender never sees them.
3. The bot watches the defender's interceptors. Once some have been seen and
   none have flown for several ticks after the decoy wave, the magazine is
   spent. Every striker is then released on the same tick. A fallback deadline
   releases them even if no interceptors were ever seen.
4. All strikers start at the same radius, so they arrive together. The gun
   fires once per tick inside a ~19-tick window, and three hits finish the
   asset.
"""

import math

NAME = "decoy_ring_magazine_drain_then_hidden_orbit_drop"
ROLE = "attacker"

N_DECOYS = 20
N_STRIKERS = 25
HOLD_R = 478.0
HOLD_STEP = 0.05
MIN_RELEASE_TICK = 125
QUIET_TICKS = 4
FALLBACK_RELEASE = 230
HARD_DEADLINE = 440

_state = {}


def reset(seed=None):
    _state.clear()
    _state.update({
        "decoys_sent": 0,
        "strikers_sent": 0,
        "seen_interceptors": False,
        "quiet": 0,
        "released": False,
    })


reset()


def _f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    s = _state
    if not s:
        reset()
    tick = int(_f(obs.get("tick", 0)))
    budget = _f(obs.get("budget", 0.0))
    rules = obs.get("rules", {}) or {}
    cap = int(_f(rules.get("attacker_launches_per_tick", 4), 4)) or 4
    s_cost = _f(rules.get("striker_cost", 2.0), 2.0)
    d_cost = _f(rules.get("decoy_cost", 0.5), 0.5)
    radar = _f(rules.get("radar_range", 450.0), 450.0)
    hold_r = max(HOLD_R, radar + 20.0)
    spawn_r = _f(rules.get("spawn_radius", 490.0), 490.0)
    hold_r = min(hold_r, spawn_r - 4.0) if spawn_r - 4.0 > radar + 5.0 else hold_r

    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = _f(ap[0]), _f(ap[1])

    launch = []
    steer = {}

    # Phase 1: decoy ring.
    while len(launch) < cap and s["decoys_sent"] < N_DECOYS and budget >= d_cost:
        i = s["decoys_sent"]
        launch.append({"type": "decoy", "bearing": 2 * math.pi * i / N_DECOYS})
        s["decoys_sent"] += 1
        budget -= d_cost

    # Phase 2: strikers to the hidden orbit (after the decoys are out).
    if s["decoys_sent"] >= N_DECOYS and not s["released"]:
        while len(launch) < cap and s["strikers_sent"] < N_STRIKERS and budget >= s_cost:
            i = s["strikers_sent"]
            b = 2 * math.pi * (i + 0.5) / N_STRIKERS
            launch.append({"type": "striker", "bearing": b})
            s["strikers_sent"] += 1
            budget -= s_cost

    # Track the defender's interceptors.
    ints = obs.get("interceptors", []) or []
    if len(ints) > 0:
        s["seen_interceptors"] = True
        s["quiet"] = 0
    else:
        s["quiet"] += 1

    decoys_alive = 0
    strikers = []
    for d in obs.get("drones", []) or []:
        t = d.get("type")
        if t == "decoy":
            decoys_alive += 1
        elif t == "striker":
            strikers.append(d)

    if not s["released"]:
        drained = (s["seen_interceptors"] and s["quiet"] >= QUIET_TICKS
                   and tick >= MIN_RELEASE_TICK)
        if drained or tick >= FALLBACK_RELEASE or tick >= HARD_DEADLINE:
            if s["strikers_sent"] >= N_STRIKERS or budget < s_cost or tick >= FALLBACK_RELEASE:
                s["released"] = True

    for d in strikers:
        did = d.get("id")
        if did is None:
            continue
        if s["released"]:
            if d.get("waypoint") is not None:
                steer[did] = None
            continue
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        px, py = _f(p[0]) - ax, _f(p[1]) - ay
        a = math.atan2(py, px) + HOLD_STEP
        steer[did] = [ax + hold_r * math.cos(a), ay + hold_r * math.sin(a)]

    return {"launch": launch, "steer": steer}
