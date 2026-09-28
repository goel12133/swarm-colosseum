"""Four drones launched on the same tick from the same bearing: a clump inside one blast."""
NAME = "clump"
ROLE = "attacker"


def act(obs):
    if obs["tick"] == 1:
        return {"launch": [{"type": "striker", "bearing": 0.0} for _ in range(4)],
                "steer": {}}
    return {"launch": [], "steer": {}}
