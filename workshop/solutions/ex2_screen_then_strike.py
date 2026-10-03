"""Exercise 2 solution: four ticks of decoys (16 of them) before the strikers.

nearest_first fires at whatever is closest, and from far away a decoy looks like a
striker. Sixteen decoys cost 8 credits and soak up interceptors that cost the defender
4 credits each.
"""
NAME = "screen_then_strike"
ROLE = "attacker"

BEARING = 45.0
SCREEN_TICKS = 4


def act(obs):
    rules = obs["rules"]
    if obs["tick"] <= SCREEN_TICKS:
        kind = "decoy"
        cost = rules["decoy_cost"]
    else:
        kind = "striker"
        cost = rules["striker_cost"]
    n = min(rules["attacker_launches_per_tick"], int(obs["budget"] // cost))
    launches = []
    for i in range(n):
        # spread them out a little so they don't all fly on top of each other
        launches.append({"type": kind, "bearing": BEARING + 3.0 * i})
    return {"launch": launches, "steer": {}}
