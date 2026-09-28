"""Gun only: never launches an interceptor.

The economic extreme. A shot costs 0.1 against an interceptor's 4, so this bot should post
an excellent cost-exchange ratio and lose on asset HP -- it is the control that stops the
scoring from being read as "cheap is good". If gun_only tops the defender ladder, the
score weights are wrong, not the strategy.
"""
NAME = "gun_only"
ROLE = "defender"


def act(obs):
    gun_range = obs["rules"]["gun_range"]
    in_gun = [t for t in obs["tracks"] if t["range"] <= gun_range]
    in_gun.sort(key=lambda t: t["range"])
    return {"intercept": [], "retarget": {},
            "gun": in_gun[0]["id"] if in_gun else None}
