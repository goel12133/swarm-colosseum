"""Decoy screen: a wall of decoys first, strikers following behind it.

Tests whether cheap drones can absorb interceptors. Decoys and strikers move at the same
speed, so before the identification range the defender cannot tell them apart -- the
screen is only wasted if the defender waits until 150 u to commit.
"""
NAME = "decoy_screen"
ROLE = "attacker"
BEARING = 45.0
SCREEN_TICKS = 4


def act(obs):
    rules = obs["rules"]
    budget = obs["budget"]
    per_tick = int(rules["attacker_launches_per_tick"])
    if obs["tick"] <= SCREEN_TICKS:
        dtype, cost = "decoy", rules["decoy_cost"]
    else:
        dtype, cost = "striker", rules["striker_cost"]
    n = min(per_tick, int(budget // cost))
    spread = [-6.0, -2.0, 2.0, 6.0]
    return {"launch": [{"type": dtype, "bearing": BEARING + spread[i % len(spread)]}
                       for i in range(n)],
            "steer": {}}
