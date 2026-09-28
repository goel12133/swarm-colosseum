"""Rush: everything down one corridor, as fast as the launch rate allows.

Tests the simplest question in the game -- can raw saturation from a single bearing
outrun a defender's ability to launch? It ignores decoys entirely, so it also sets the
floor for how much the defender's identification range is worth: against rush there is
nothing to misidentify.
"""
NAME = "rush"
ROLE = "attacker"
BEARING = 0.0


def act(obs):
    rules = obs["rules"]
    budget = obs["budget"]
    cost = rules["striker_cost"]
    n = min(int(rules["attacker_launches_per_tick"]), int(budget // cost))
    return {"launch": [{"type": "striker", "bearing": BEARING} for _ in range(n)],
            "steer": {}}
