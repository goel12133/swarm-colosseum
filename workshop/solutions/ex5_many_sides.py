"""Exercise 5 solution: every striker gets a bearing of its own.

identify_then_engage waits until it is sure a drone is a striker, then fires. Drones that
fly in a line die together: one interceptor burst catches everything within 10 u, so
four bearings still means lines of drones on each one. Giving every striker a fresh
bearing spreads them round the circle, so each interceptor can only ever take one, and
the defender runs out (it has 20) before the strikers do (we can afford 30).
"""
NAME = "many_sides"
ROLE = "attacker"

STEP = 12.0         # degrees between one striker's bearing and the next
launched = 0        # how many strikers we have sent so far this match


def reset(seed):
    global launched
    launched = 0


def act(obs):
    global launched
    rules = obs["rules"]
    cost = rules["striker_cost"]
    n = min(rules["attacker_launches_per_tick"], int(obs["budget"] // cost))
    launches = []
    for _ in range(n):
        launches.append({"type": "striker", "bearing": (launched * STEP) % 360.0})
        launched += 1
    return {"launch": launches, "steer": {}}
