"""Flanker: two axes timed to arrive in the same tick window, to overrun the defender's
two-interceptor-per-tick launch cap.

The idea being tested is a rate limit, not a geometry trick. A defender can commit at most
2 interceptors and 1 gun shot per tick, so what matters is not how many drones are in the
air but how many arrive *per tick*. The attacker's own launch cap is 4 per tick, which puts
a ceiling of 4 arrivals per tick on any single-axis attack however it is shaped.

Two axes with different path lengths break that ceiling. One wave takes a dogleg -- out to a
waypoint beyond radar range, then in from a different bearing -- and the other flies direct
from a third bearing, launched later by exactly the difference in flight time. Both waves
then land in the same few ticks, at up to 8 arrivals per tick against a defence that can
answer 2.

The dogleg wave flies an **arc** at spawn radius rather than a straight chord. A straight
line from one bearing to another cuts inside: from 0 deg to 120 deg at radius 480 the chord
passes within about 240 u of the asset, which is deep inside the 450 u radar, and the wave is
tracked and destroyed for two hundred ticks before it ever arrives. That was measured, not
assumed -- the chord version scored zero impacts against every active defender. Steering a
few degrees around the circle each tick keeps the whole transit outside radar range.

The drones do **not** fan out to dodge blasts -- an earlier version did, and won nothing,
because at a 10 u blast radius spreading buys little survivability and costs the concentration
this idea depends on. But they are de-stacked by a couple of degrees, which is a different
thing. Four drones launched on the same tick from the same bearing occupy *identical*
coordinates, and a single interceptor then kills all four; the first version of this bot lost
6, 8 and 11 drones to single blasts that way. A 2.5 deg offset puts same-tick launches about
20 u apart at the spawn ring -- outside each other's blast radius -- while still landing
inside the same arrival window.

Timing is computed from the rules rather than hard-coded, so it still holds if a later season
changes speeds or ranges.
"""
import math

NAME = "flanker"
ROLE = "attacker"

DOGLEG_LAUNCH_BEARING = 0.0      # where the dogleg wave is launched from
DOGLEG_TURN_BEARING = 120.0      # and the bearing it finally attacks from
DIRECT_BEARING = 240.0           # the second axis, flown straight in
DOGLEG_SHARE = 0.55              # fraction of the budget spent on the longer path
ARC_STEP_DEG = 9.0               # how far around the circle to aim each tick
DESTACK_DEG = 2.5                # keeps same-tick launches outside one blast radius

_state = {"wave1": set()}


def reset(seed):
    _state["wave1"] = set()


def _plan(rules):
    """Flight times for both paths, and the launch offset that makes them coincide."""
    spawn_r = rules["spawn_radius"]
    turn_r = max(rules["radar_range"] + 20.0, spawn_r - 10.0)   # stay outside radar
    speed = rules["striker_speed"]
    sweep = abs(DOGLEG_TURN_BEARING - DOGLEG_LAUNCH_BEARING) % 360.0
    arc_len = turn_r * math.radians(sweep)
    dogleg_ticks = (arc_len + turn_r - rules["asset_radius"]) / speed
    direct_ticks = (spawn_r - rules["asset_radius"]) / speed
    return dict(turn_r=turn_r, sweep=sweep,
                offset=int(round(dogleg_ticks - direct_ticks)))


def act(obs):
    rules = obs["rules"]
    plan = _plan(rules)
    per_tick = int(rules["attacker_launches_per_tick"])
    cost = rules["striker_cost"]
    budget = obs["budget"]

    total = int(rules["attacker_budget"] // cost)
    n_dogleg = int(total * DOGLEG_SHARE)
    wave1_ticks = max(1, math.ceil(n_dogleg / per_tick))

    tick = obs["tick"]
    launches = []
    # Wave 1: the long way round, launched immediately.
    if 1 <= tick <= wave1_ticks:
        n = min(per_tick, int(budget // cost))
        launches = [{"type": "striker",
                     "bearing": DOGLEG_LAUNCH_BEARING + i * DESTACK_DEG} for i in range(n)]
    # Wave 2: straight in, launched late enough to land with wave 1.
    elif plan["offset"] + 1 <= tick <= plan["offset"] + wave1_ticks + 2:
        n = min(per_tick, int(budget // cost))
        launches = [{"type": "striker",
                     "bearing": DIRECT_BEARING + i * DESTACK_DEG} for i in range(n)]

    # Wave 1 is walked around the circle a few degrees at a time; wave 2 flies straight in.
    steer = {}
    for d in obs["drones"]:
        if d["id"] not in _state["wave1"]:
            if tick <= wave1_ticks + 1:
                _state["wave1"].add(d["id"])
            else:
                continue
        x, y = d["pos"]
        bearing = math.degrees(math.atan2(y, x)) % 360.0
        travelled = (bearing - DOGLEG_LAUNCH_BEARING) % 360.0
        if travelled > 300.0:        # just behind the launch bearing from de-stacking
            travelled = 0.0
        if travelled >= plan["sweep"] - ARC_STEP_DEG:
            steer[d["id"]] = None                     # on station: turn in for the asset
            continue
        aim = math.radians(min(travelled + ARC_STEP_DEG, plan["sweep"])
                           + DOGLEG_LAUNCH_BEARING)
        steer[d["id"]] = [plan["turn_r"] * math.cos(aim), plan["turn_r"] * math.sin(aim)]
    return {"launch": launches, "steer": steer}
