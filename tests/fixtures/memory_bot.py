"""Allocates far past the container memory limit. Must die without taking the match down."""
NAME = "memory_bot"
ROLE = "attacker"


def act(obs):
    blocks = []
    while True:
        blocks.append(bytearray(32 * 1024 * 1024))
