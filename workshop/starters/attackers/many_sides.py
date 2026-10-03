"""Many sides: strikers from several directions, one direction after another.

A defender has to turn its attention to wherever the drones are coming from. Coming
from more than one side at once might make that harder.
"""
NAME = "many_sides"
ROLE = "attacker"

# TODO: add more bearings (degrees) to this list, e.g. [0.0, 180.0]
BEARINGS = [0.0]


def act(obs):
    rules = obs["rules"]
    cost = rules["striker_cost"]
    n = min(rules["attacker_launches_per_tick"], int(obs["budget"] // cost))
    launches = []
    for i in range(n):
        bearing = BEARINGS[i % len(BEARINGS)]    # take turns through the list
        launches.append({"type": "striker", "bearing": bearing})
    return {"launch": launches, "steer": {}}
