"""Straight line: strikers flown straight at the base from one direction.

The simplest attacker there is. Every tick it launches some strikers from the same
bearing (the compass direction they start from) and lets them fly straight in.
"""
NAME = "straight_line"
ROLE = "attacker"

BEARING = 0.0         # where the drones start, in degrees: 0 = east, 90 = north
# TODO: the rules allow up to 4 launches per tick. What happens if you use them all?
LAUNCHES_PER_TICK = 1


def act(obs):
    budget = obs["budget"]                       # credits left to spend
    cost = obs["rules"]["striker_cost"]          # what one striker costs
    can_afford = int(budget // cost)
    n = min(LAUNCHES_PER_TICK, can_afford)
    launches = []
    for _ in range(n):
        launches.append({"type": "striker", "bearing": BEARING})
    return {"launch": launches, "steer": {}}
