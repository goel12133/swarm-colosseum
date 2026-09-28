"""Launches exactly one decoy on tick 1, from bearing 0, then nothing."""
NAME = "one_decoy"
ROLE = "attacker"


def act(obs):
    if obs["tick"] == 1:
        return {"launch": [{"type": "decoy", "bearing": 0.0}], "steer": {}}
    return {"launch": [], "steer": {}}
