"""Gun line: interceptors only for drones that get close; the gun does the rest.

Interceptors are expensive and there are only 20. This bot holds them back until a
drone is inside ENGAGE_RANGE, hoping the cheap gun can handle most of the work.
"""
NAME = "gun_line"
ROLE = "defender"

# TODO: how close (in u) must a drone be before we spend an interceptor on it?
# The radar sees out to 450 u; the gun reaches 100 u.
ENGAGE_RANGE = 450.0


def act(obs):
    rules = obs["rules"]
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    already_chased = {i["target"] for i in obs["interceptors"]}

    intercept = []
    for t in tracks:
        if t["range"] <= ENGAGE_RANGE and t["id"] not in already_chased:
            intercept.append(t["id"])
    intercept = intercept[:rules["interceptor_launches_per_tick"]]

    gun = None
    for t in tracks:
        if t["range"] <= rules["gun_range"]:
            gun = t["id"]
            break
    return {"intercept": intercept, "retarget": {}, "gun": gun}
