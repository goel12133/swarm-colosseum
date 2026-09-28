"""Nearest first: one interceptor per nearest unengaged track, gun on the nearest thing
in range.

The obvious baseline, and the one that should lose to decoys. It commits on range alone
and never asks what a track is, so every decoy it engages costs 4 credits to destroy 0.5.
Everything else is measured against this.
"""
NAME = "nearest_first"
ROLE = "defender"


def act(obs):
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    engaged = {i["target"] for i in obs["interceptors"]}
    intercept = [t["id"] for t in tracks if t["id"] not in engaged]
    intercept = intercept[:int(obs["rules"]["interceptor_launches_per_tick"])]
    gun_range = obs["rules"]["gun_range"]
    in_gun = [t for t in tracks if t["range"] <= gun_range]
    return {"intercept": intercept, "retarget": {},
            "gun": in_gun[0]["id"] if in_gun else None}
