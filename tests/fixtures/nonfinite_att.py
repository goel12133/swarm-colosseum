"""Attacker that sends numbers json.loads accepts but the engine must not: NaN, infinities,
and integers too large for a float. One good striker per tick keeps the match going."""
NAME = "nonfinite_att"
ROLE = "attacker"


def act(obs):
    ids = [d["id"] for d in obs["drones"]]
    steer = {str(i): [float("nan"), 0.0] for i in ids[:1]}
    steer.update({str(i): [0.0, 10 ** 400] for i in ids[1:2]})
    steer["1e999"] = [1.0, 1.0]
    return {"launch": [{"type": "decoy", "bearing": float("nan")},
                       {"type": "decoy", "bearing": float("inf")},
                       {"type": "decoy", "bearing": 10 ** 400},
                       {"type": "striker", "bearing": 90}],
            "steer": steer}
