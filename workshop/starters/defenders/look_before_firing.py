"""Look before firing: only send interceptors at drones we are sure are strikers.

Every track has a "cls" (class): "striker", "decoy", or "unknown" while the drone is
still too far away to identify. Waiting to find out costs time; not waiting costs
interceptors spent on decoys.
"""
NAME = "look_before_firing"
ROLE = "defender"

# TODO: which classes are worth an interceptor? Try removing "unknown" and "decoy".
FIRE_AT = ["striker", "unknown", "decoy"]


def act(obs):
    rules = obs["rules"]
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    already_chased = {i["target"] for i in obs["interceptors"]}

    intercept = []
    for t in tracks:
        if t["cls"] in FIRE_AT and t["id"] not in already_chased:
            intercept.append(t["id"])
    intercept = intercept[:rules["interceptor_launches_per_tick"]]

    gun = None
    for t in tracks:
        if t["range"] <= rules["gun_range"]:
            gun = t["id"]
            break
    return {"intercept": intercept, "retarget": {}, "gun": gun}
