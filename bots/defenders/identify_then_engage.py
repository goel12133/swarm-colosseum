"""Identify then engage: interceptors only on tracks confirmed to be strikers, and
orphaned interceptors get retargeted rather than wasted.

Tests whether the identification range is worth the delay. Waiting until 150 u means
firing later and with less flight time to spare, but never spending 4 credits on a 0.5
credit decoy. Against decoy_screen it should win the economy; against rush it gives up
stand-off distance for nothing.
"""
NAME = "identify_then_engage"
ROLE = "defender"


def act(obs):
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    by_id = {t["id"]: t for t in tracks}
    strikers = [t for t in tracks if t["cls"] == "striker"]
    engaged = {i["target"] for i in obs["interceptors"] if i["target"] in by_id}

    # Any interceptor whose target has gone (killed, or left radar) is re-aimed at the
    # closest confirmed striker that nothing is already chasing.
    retarget, claimed = {}, set(engaged)
    free = [t for t in strikers if t["id"] not in claimed]
    for i in obs["interceptors"]:
        if i["target"] not in by_id and free:
            t = free.pop(0)
            retarget[i["id"]] = t["id"]
            claimed.add(t["id"])

    intercept = [t["id"] for t in strikers if t["id"] not in claimed]
    intercept = intercept[:int(obs["rules"]["interceptor_launches_per_tick"])]

    gun_range = obs["rules"]["gun_range"]
    in_gun = [t for t in tracks if t["range"] <= gun_range and t["cls"] != "decoy"]
    if not in_gun:
        in_gun = [t for t in tracks if t["range"] <= gun_range]
    return {"intercept": intercept, "retarget": retarget,
            "gun": in_gun[0]["id"] if in_gun else None}
