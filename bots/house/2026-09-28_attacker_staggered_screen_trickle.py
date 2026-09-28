"""
NAME: staggered_screen_trickle

Target: identify_then_engage. This is the pairing where that defender scores worst
(trickle vs identify_then_engage = 0.155 mean score_defender).

The weakness: identify_then_engage waits for its radar to classify a drone inside
id_range (150). Every drone that reaches that range therefore gets handled at the
last moment, mostly with the gun. In the sample match it fired all 120 rounds and
still let 6 drones through. Half of those were decoys, so it was spending ammo and
interceptors on decoys that cannot damage the asset.

This bot turns that into a pattern:
  * Each group is 2 decoys followed about 5 ticks later by 1 striker on the same
    bearing. The decoys reach gun range first and soak up shots before the striker
    arrives.
  * A new group every 18 ticks. Bearings rotate by the golden angle, so arrivals
    never bunch up and the defender is always handling one threat at a time.
  * Budget is split exactly: 20 groups x (2 x 0.5 + 2.0) = 60.
  * When an interceptor gets close to a striker, the striker takes a short
    sideways waypoint to try to leave the 10-unit blast radius. Once the threat
    has passed, the waypoint is cleared.
"""
import math

NAME = "staggered_screen_trickle"
ROLE = "attacker"

PERIOD = 18
STRIKER_DELAY = 5
GOLDEN = 2.399963229728653

_state = {"dodging": set()}


def reset(seed=None):
    _state["dodging"] = set()


def _bearing(g):
    return (g * GOLDEN + 0.3) % (2.0 * math.pi)


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    cap = int(rules.get("attacker_launches_per_tick", 4))

    launch = []
    g = tick // PERIOD
    phase = tick % PERIOD
    b = _bearing(g)

    if phase == 0:
        # Launch decoys only if a striker can still be afforded afterwards.
        for _ in range(2):
            if len(launch) < cap and budget - d_cost >= s_cost:
                launch.append({"type": "decoy", "bearing": b})
                budget -= d_cost
    elif phase == STRIKER_DELAY:
        if budget >= s_cost and len(launch) < cap:
            launch.append({"type": "striker", "bearing": b})
            budget -= s_cost

    # Leftover budget that cannot buy a striker goes on decoys.
    if budget < s_cost and budget >= d_cost and phase == 9:
        while budget >= d_cost and len(launch) < cap:
            launch.append({"type": "decoy", "bearing": _bearing(g + 7)})
            budget -= d_cost

    steer = {}
    asset = obs.get("asset", {}) or {}
    apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ints = obs.get("interceptors", []) or []
    dodging = _state["dodging"]

    for d in obs.get("drones", []) or []:
        if d.get("type") != "striker":
            continue
        did = d.get("id")
        px, py = d.get("pos", [0.0, 0.0])
        rng = math.hypot(px - apos[0], py - apos[1])

        best = None
        bd = 1e18
        for ip in ints:
            try:
                ix, iy = ip[0], ip[1]
            except Exception:
                continue
            dd = math.hypot(ix - px, iy - py)
            if dd < bd:
                bd = dd
                best = (ix, iy)

        if best is not None and bd < 40.0 and rng > 50.0:
            dx, dy = best[0] - px, best[1] - py
            n = math.hypot(dx, dy) or 1.0
            perp_x, perp_y = -dy / n, dx / n
            # Pick the sideways direction that also points more toward the asset.
            tx, ty = apos[0] - px, apos[1] - py
            if perp_x * tx + perp_y * ty < 0:
                perp_x, perp_y = -perp_x, -perp_y
            steer[did] = [px + perp_x * 30.0, py + perp_y * 30.0]
            dodging.add(did)
        elif did in dodging:
            steer[did] = None
            dodging.discard(did)

    return {"launch": launch, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
