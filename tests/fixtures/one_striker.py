"""Launches exactly one striker on tick 1, from bearing 0, then nothing."""
NAME = "one_striker"
ROLE = "attacker"


def act(obs):
    if obs["tick"] == 1:
        return {"launch": [{"type": "striker", "bearing": 0.0}], "steer": {}}
    return {"launch": [], "steer": {}}
