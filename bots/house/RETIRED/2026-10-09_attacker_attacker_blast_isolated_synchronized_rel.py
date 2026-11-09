"""
Idea: Field FEWER strikers than the ring can hold -- exactly 26 spaced just past one blast width at the defender's engagement radius -- then park them on a staging ring and release all at once so the exchange is forced to a strict 1-for-1 the interceptor magazine cannot win.

Why this is not the obvious counter
-----------------------------------
The obvious reply to convergence_blast_scheduler is to spread harder, desync,
or pile on MORE strikers / decoys so a 10-unit blast cannot catch pairs. Every
ring attacker on the ladder maximises striker count (30) on a wide ring and
lets it converge; that is precisely the shrinking ring the scheduler was built
to feast on -- below r~48 neighbours fall inside one blast and each interceptor
scores doubles or triples, so 20 interceptors clear all 30.

This bot does the opposite of "more": it UNDERCOUNTS on purpose. The scheduler
plans its blast groups at RD1 = asset_radius+15 = 40. The arc length between
neighbours on an evenly filled circle at r is 2*pi*r/N. For the kills to stay
single, that spacing must exceed the coverage radius CR = 0.9*blast = 9 at
r = 40, which caps useful strikers at 2*pi*40/9 ~ 27. We field N = 26: spacing
at r=40 is ~9.66 > 9, so the scheduler's own grouping math can only ever cover
one striker per aim point, and with 26 live threats it has no spare stock for
its secondary (RD2=31) layer. The clever multi-kill engine is reduced to a
plain nearest-shooter.

From there it is arithmetic the defender cannot escape: 20 interceptors at
pk 0.85 kill ~17, the single-target gun cleans up only a few, and the rest
leak. To stop the gun from grinding the leakers down over their 19-tick walk
through gun range, every striker is first flown to a common staging ring at
r=130 (outside the r<100 auto-"closing" flag and the gun's 100 reach) and held
there by chasing a point 0.3 rad ahead on the circle, so radial speed reads ~0
and the scheduler -- which ignores non-closing tracks and engages "as late as
feasible" -- holds its entire magazine. When all 26 are staged they are
released on the same tick; identical remaining range makes them arrive together,
so the gun gets only ~one window of shots across many simultaneous impactors.
Trading raw numbers for a guaranteed blast-isolated, time-synchronized 1-for-1
is what nothing else on the ladder does.
"""
import math

NAME = "attacker_blast_isolated_synchronized_release"
ROLE = "attacker"

N = 26
STAGE_R = 130.0
ORBIT_STEP = 0.3
RELEASE_DEADLINE = 220

_S = {}


def reset(seed=None):
    global _S
    _S = {"launched": 0, "released": False}


reset()


def _act(obs):
    s = _S
    tick = int(obs.get("tick", 0) or 0)
    drones = obs.get("drones", []) or []
    action = {"launch": [], "steer": {}}

    # ---- launch 26 strikers on an even ring (4 per tick cap)
    if s["launched"] < N:
        k = min(4, N - s["launched"])
        for _ in range(k):
            b = (s["launched"] + 0.5) * 2.0 * math.pi / N
            action["launch"].append({"type": "striker", "bearing": b})
            s["launched"] += 1

    # ---- decide synchronized release
    if not s["released"]:
        all_up = s["launched"] >= N
        staged = True
        seen = 0
        for d in drones:
            p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
            r = math.hypot(float(p[0]), float(p[1]))
            seen += 1
            if r > STAGE_R + 15.0:
                staged = False
        if (all_up and seen >= min(N, s["launched"]) and staged) or tick >= RELEASE_DEADLINE:
            s["released"] = True

    # ---- steering
    for d in drones:
        did = d.get("id")
        if did is None:
            continue
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        x, y = float(p[0]), float(p[1])
        r = math.hypot(x, y)

        if s["released"]:
            # head straight for the asset, all at once
            action["steer"][did] = None
            continue

        if r < 1e-6:
            th = 0.0
        else:
            th = math.atan2(y, x)

        if r > STAGE_R + 5.0:
            # inbound: hold bearing, fly to staging ring
            action["steer"][did] = [STAGE_R * math.cos(th), STAGE_R * math.sin(th)]
        else:
            # hold on the staging ring by chasing a point just ahead on it,
            # so radial speed stays ~0 and the scheduler keeps its magazine
            th2 = th + ORBIT_STEP
            action["steer"][did] = [STAGE_R * math.cos(th2), STAGE_R * math.sin(th2)]

    return action


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
