"""Defender that does nothing at all."""
NAME = "idle_def"
ROLE = "defender"


def act(obs):
    return {"intercept": [], "retarget": {}, "gun": None}
