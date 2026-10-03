"""Defender that sends infinities and huge integers as ids. Before the 3.9 fix, int(inf)
raised OverflowError out of the match and took the tournament down with it."""
NAME = "nonfinite_def"
ROLE = "defender"


def act(obs):
    return {"intercept": [float("inf"), 10 ** 400],
            "retarget": {"1": float("-inf")},
            "gun": float("inf")}
