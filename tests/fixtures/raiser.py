"""A bot that raises on every call. The match must still finish."""
NAME = "raiser"
ROLE = "attacker"


def reset(seed):
    raise RuntimeError("boom in reset")


def act(obs):
    raise RuntimeError("boom in act")
