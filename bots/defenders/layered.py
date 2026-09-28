"""Layered: prioritise by time to impact, keep interceptors back for confirmed strikers,
and let the gun take whatever leaks through.

Tests whether a defender should think in time rather than distance, and whether holding
magazine depth beats engaging everything early. Unknown tracks are engaged only when they
are close enough that waiting for identification would cost the intercept, and the reserve
shrinks as the match runs out of time for new threats to matter.
"""
NAME = "layered"
ROLE = "defender"


def _time_to_impact(track, rules):
    speed = max(rules["striker_speed"], 1e-9)
    return max(0.0, (track["range"] - rules["asset_radius"]) / speed)


def act(obs):
    rules = obs["rules"]
    tracks = obs["tracks"]
    by_id = {t["id"]: t for t in tracks}
    engaged = {i["target"] for i in obs["interceptors"] if i["target"] in by_id}

    ranked = sorted(tracks, key=lambda t: _time_to_impact(t, rules))
    confirmed = [t for t in ranked if t["cls"] == "striker"]
    unknown_close = [t for t in ranked
                     if t["cls"] == "unknown" and _time_to_impact(t, rules) < 45.0]

    retarget, claimed = {}, set(engaged)
    free = [t for t in confirmed if t["id"] not in claimed]
    for i in obs["interceptors"]:
        if i["target"] not in by_id and free:
            t = free.pop(0)
            retarget[i["id"]] = t["id"]
            claimed.add(t["id"])

    # Hold some stock back early: a magazine emptied on the first wave cannot answer the
    # second. The reserve is released as the match runs out of time.
    ticks_left = max(0, rules["max_ticks"] - obs["tick"])
    reserve = 6 if ticks_left > 300 else (3 if ticks_left > 120 else 0)
    allowed = max(0, obs["stock"] - reserve)

    queue = [t for t in confirmed if t["id"] not in claimed]
    queue += [t for t in unknown_close if t["id"] not in claimed]
    intercept = [t["id"] for t in queue][:int(rules["interceptor_launches_per_tick"])]
    intercept = intercept[:allowed]

    gun_range = rules["gun_range"]
    leakers = [t for t in ranked if t["range"] <= gun_range and t["cls"] != "decoy"]
    if not leakers:
        leakers = [t for t in ranked if t["range"] <= gun_range]
    return {"intercept": intercept, "retarget": retarget,
            "gun": leakers[0]["id"] if leakers else None}
