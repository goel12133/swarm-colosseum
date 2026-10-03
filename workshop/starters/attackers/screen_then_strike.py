"""Screen then strike: cheap decoys first, real strikers behind them.

Decoys cost a quarter of a striker and do no damage, but from far away the defender cannot
tell them apart. A defender that shoots at everything wastes its interceptors on them.
"""
NAME = "screen_then_strike"
ROLE = "attacker"

BEARING = 45.0
# TODO: for how many ticks should we send decoys before the strikers? 0 means no decoys.
SCREEN_TICKS = 0


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
