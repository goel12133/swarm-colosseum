"""Closest first: send an interceptor at the nearest drone nothing is chasing yet.

The base has two tools. Interceptors (4 credits each, 20 in stock) fly out and burst
near a drone. The gun (0.1 credits a shot) only reaches drones close to the base, and
hits more often the closer they are.
"""
NAME = "closest_first"
ROLE = "defender"

# TODO: the gun is switched off. Try turning it on.
USE_GUN = False


def act(obs):
    rules = obs["rules"]
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])     # nearest first
    already_chased = {i["target"] for i in obs["interceptors"]}

    intercept = []
    for t in tracks:
        if t["id"] not in already_chased:
            intercept.append(t["id"])
    intercept = intercept[:rules["interceptor_launches_per_tick"]]

    gun = None
    if USE_GUN:
        for t in tracks:
            if t["range"] <= rules["gun_range"]:
                gun = t["id"]                   # shoot the nearest one in range
                break
    return {"intercept": intercept, "retarget": {}, "gun": gun}
