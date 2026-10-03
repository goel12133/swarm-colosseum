"""Exercise 1 solution: the gun switched on.

rush sends all 30 strikers down one line. Interceptors alone run out (there are 20);
the gun is the last line, cheap and close in, and catches the ones that get through.
"""
NAME = "closest_first"
ROLE = "defender"

USE_GUN = True


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
