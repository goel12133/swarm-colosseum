"""Exercise 4 solution: four sides instead of one.

nearest_first always chases whatever is closest. With drones arriving from four
directions at once, its interceptors are spread thin and the gun can only point one way.
"""
NAME = "many_sides"
ROLE = "attacker"

BEARINGS = [0.0, 90.0, 180.0, 270.0]


def act(obs):
    rules = obs["rules"]
    cost = rules["striker_cost"]
    n = min(rules["attacker_launches_per_tick"], int(obs["budget"] // cost))
    launches = []
    for i in range(n):
        bearing = BEARINGS[i % len(BEARINGS)]    # take turns through the list
        launches.append({"type": "striker", "bearing": bearing})
    return {"launch": launches, "steer": {}}
