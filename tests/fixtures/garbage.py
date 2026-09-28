"""Returns malformed actions: wrong types, unknown drone types, over-rate launches."""
NAME = "garbage"
ROLE = "attacker"


def act(obs):
    return {"launch": [{"type": "battleship", "bearing": 0},
                       {"type": "striker", "bearing": "north"},
                       "not-a-dict",
                       {"type": "striker", "bearing": 10},
                       {"type": "striker", "bearing": 20},
                       {"type": "striker", "bearing": 30},
                       {"type": "striker", "bearing": 40},
                       {"type": "striker", "bearing": 50}],
            "steer": {"nope": [1, 2], "1": "bad"}}
