"""Multi-axis: staggered mixed waves from four bearings at once.

Tests whether splitting the threat beats concentrating it. A defender that prioritises
purely by range has to keep switching sides, and interceptor flight time is dead time.
Each wave leads with a decoy so the defender's early commitments are on the wrong drone.
"""
NAME = "multi_axis"
ROLE = "attacker"
BEARINGS = [0.0, 90.0, 180.0, 270.0]
WAVE_EVERY = 12


def act(obs):
    rules = obs["rules"]
    budget = obs["budget"]
    tick = obs["tick"]
    if tick % WAVE_EVERY not in (1, 2):
        return {"launch": [], "steer": {}}
    wave = tick // WAVE_EVERY
    launches = []
    for i, bearing in enumerate(BEARINGS):
        dtype = "decoy" if (tick % WAVE_EVERY == 1 and i % 2 == 0) else "striker"
        cost = rules["decoy_cost"] if dtype == "decoy" else rules["striker_cost"]
        if budget < cost:
            break
        budget -= cost
        launches.append({"type": dtype, "bearing": (bearing + 7.0 * wave) % 360.0})
    return {"launch": launches[:int(rules["attacker_launches_per_tick"])], "steer": {}}
