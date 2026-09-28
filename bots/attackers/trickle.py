"""Trickle: small mixed groups at intervals from seeded-random bearings.

Tests stock exhaustion rather than saturation. The defender has 20 interceptors against a
budget that can buy 30 strikers, so an attacker that never presents a mass target may be
able to drain the magazine and walk the rest in. Bearings are drawn from a seeded RNG so
the pattern differs by match but is reproducible.
"""
import random

NAME = "trickle"
ROLE = "attacker"
GROUP_EVERY = 9
_rng = random.Random(0)


def reset(seed):
    global _rng
    _rng = random.Random(seed)


def act(obs):
    rules = obs["rules"]
    if obs["tick"] % GROUP_EVERY != 1:
        return {"launch": [], "steer": {}}
    budget = obs["budget"]
    launches = []
    for i in range(2):
        dtype = "decoy" if i == 0 else "striker"
        cost = rules["decoy_cost"] if dtype == "decoy" else rules["striker_cost"]
        if budget < cost:
            break
        budget -= cost
        launches.append({"type": dtype, "bearing": _rng.uniform(0.0, 360.0)})
    return {"launch": launches, "steer": {}}
