"""Exercise 3 solution: interceptors only for confirmed strikers.

decoy_screen sends 16 decoys ahead of its strikers. Firing at "unknown" tracks spends
interceptors on decoys long before anything can be identified; waiting until a track is
known to be a striker (150 u out) keeps all 20 for the drones that matter.
"""
NAME = "look_before_firing"
ROLE = "defender"

FIRE_AT = ["striker"]


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
