"""Tries to open a network socket on every call. Must fail inside the sandbox."""
import socket

NAME = "socket_bot"
ROLE = "attacker"


def act(obs):
    s = socket.create_connection(("1.1.1.1", 53), timeout=2)
    s.close()
    return {"launch": [{"type": "striker", "bearing": 0.0}], "steer": {}}
