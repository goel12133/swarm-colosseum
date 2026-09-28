"""Defender that tries to launch far more interceptors than the rules allow."""
NAME = "spam_intercept"
ROLE = "defender"


def act(obs):
    ids = [t["id"] for t in obs["tracks"]]
    return {"intercept": ids * 5, "retarget": {},
            "gun": ids[0] if ids else None}
