"""Never returns. Must be cut off by the per-tick timeout."""
NAME = "busy_bot"
ROLE = "attacker"


def act(obs):
    x = 0
    while True:
        x += 1
