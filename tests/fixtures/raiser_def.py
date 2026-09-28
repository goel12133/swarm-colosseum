"""Defender that raises on every call."""
NAME = "raiser_def"
ROLE = "defender"


def act(obs):
    raise ValueError("boom")
