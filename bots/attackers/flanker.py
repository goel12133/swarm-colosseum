"""Flanker: dogleg waypoints so the attack arrives from a side the defender is not facing,
and spreads out so one blast cannot take several drones.

Tests two things at once: whether committing interceptors early against an apparent bearing
is punished when the drones turn, and whether spacing defeats the rule that every drone
inside a blast is rolled.
"""
import math

NAME = "flanker"
ROLE = "attacker"
LAUNCH_BEARING = 200.0
TURN_BEARING = 20.0
# The turn has to happen OUTSIDE radar range, or the defender simply watches the dogleg
# and the bot is only flying a longer exposed path. The first version turned at 300 u,
# well inside the 450 u radar, and lost every match for exactly that reason.
DOGLEG_RADIUS = 470.0


def act(obs):
    rules = obs["rules"]
    budget = obs["budget"]
    per_tick = int(rules["attacker_launches_per_tick"])
    launches = []
    n = min(per_tick, int(budget // rules["striker_cost"]))
    for i in range(n):
        launches.append({"type": "striker",
                         "bearing": (LAUNCH_BEARING + 11.0 * i) % 360.0})

    # Give every drone without a waypoint a dogleg point, fanned out so the group does not
    # arrive as a single clump inside one blast radius.
    steer = {}
    for d in obs["drones"]:
        if d["waypoint"] is None:
            spread = (d["id"] % 7) * 14.0 - 42.0
            theta = math.radians(TURN_BEARING + spread)
            steer[d["id"]] = [DOGLEG_RADIUS * math.cos(theta),
                              DOGLEG_RADIUS * math.sin(theta)]
    return {"launch": launches, "steer": steer}
