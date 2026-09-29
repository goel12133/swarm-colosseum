"""
NAME: synchronized_ring

Target: 2026-09-28_defender_discriminating_ledger.

Which part of its logic this attacks
------------------------------------
1. The id gate in is_threat(). The ledger only engages confirmed strikers, or
   unknown tracks closer than 0.9 * id_range (135). Anything parked at about
   190 is ignored. It gets no interceptors and no gun, so we can loiter there
   for free and choose when every striker starts its run.
2. The magazine plus the launch rate. It only has 20 interceptors against our
   30 strikers, and a cap of 2 launches per tick. The ledger gives one
   interceptor per striker, so the stock is gone after the first 20 strikers
   are engaged.
3. The single gun. After the stock is gone the gun is the only thing left, and
   it can pick one track per tick with a low per-shot kill chance.

What the replays show
---------------------
* Against rush (seed 0), 30 strikers came in on a tight axis. The ledger killed
  all 30 with only 20 interceptors, so the 10 m blasts took several strikers
  each. Clustering helps it. We spread 30 strikers evenly around the ring (12
  degrees apart, about 20+ units apart where the interceptors meet them), so
  one blast should kill one striker.
* Its closest calls were all multi_axis (asset hp 10). Stock hit 0 and
  strikers leaked at ticks 165 and 166, arriving at nearly the same time from
  different axes. When arrivals overlap in time and the stock is empty, the
  one-target gun cannot keep up. multi_axis did that partly by accident and
  wasted budget on decoys. We do it on purpose, with all strikers and no
  decoys.

Plan
----
* Calibrate the bearing convention with one launch, then launch the rest on
  evenly spaced bearings.
* Hold every striker on a ring at radius 190, outside the gate, until all are
  on station.
* Release all strikers on the same tick. About 30 strikers enter id range
  together. At most 20 interceptors (about 17 kills at 0.85) can be used, and
  the roughly 10 survivors arrive within a few ticks of each other. The gun
  gets about 19 shots with a weak kill chance, and 3 hits destroy the asset.
"""
import math

NAME = "synchronized_ring"
ROLE = "attacker"

HOLD_R = 190.0
TRAVEL_MIN_R = 235.0
RELEASE_DEADLINE = 420

_S = {}


def reset(seed=None):
    global _S
    _S = {
        "cal": None,          # convention index
        "cal_launch_tick": None,
        "cal_bearing": 3.0,
        "slots": None,        # list of slot angles
        "next_slot": 1,
        "pending": [],        # slot indices launched, not yet claimed
        "assign": {},         # drone id -> slot index
        "claimed": set(),
        "planned": None,
        "launched": 0,
        "released": False,
        "known": set(),
    }


reset()


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def _fwd(conv, b):
    # bearing value -> math angle
    if conv == 0:
        return b
    if conv == 1:
        return math.radians(b)
    if conv == 2:
        return math.pi / 2 - b
    return math.pi / 2 - math.radians(b)


def _inv(conv, th):
    # math angle -> bearing value
    if conv == 0:
        return th % (2 * math.pi)
    if conv == 1:
        return math.degrees(th) % 360.0
    if conv == 2:
        return (math.pi / 2 - th) % (2 * math.pi)
    return math.degrees(math.pi / 2 - th) % 360.0


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    s_cost = float(rules.get("striker_cost", 2.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    drones = obs.get("drones", []) or []

    launch = []
    steer = {}

    if S["planned"] is None:
        S["planned"] = int(budget // s_cost) if s_cost > 0 else 0

    # Find drones we have not seen before
    new = []
    for d in drones:
        did = d.get("id")
        if did not in S["known"]:
            S["known"].add(did)
            new.append(d)

    def ang_of(d):
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        return math.atan2(float(p[1]) - ay, float(p[0]) - ax)

    # Calibration
    if S["cal"] is None:
        if S["cal_launch_tick"] is None:
            if budget >= s_cost and S["planned"] > 0:
                launch.append({"type": "striker", "bearing": S["cal_bearing"]})
                S["cal_launch_tick"] = tick
                S["launched"] += 1
            return {"launch": launch, "steer": steer}
        if new:
            a = ang_of(new[0])
            best, bd = 0, 1e9
            for c in range(4):
                dd = abs(_wrap(_fwd(c, S["cal_bearing"]) - a))
                if dd < bd:
                    bd, best = dd, c
            S["cal"] = best
            n = max(1, S["planned"])
            S["slots"] = [_wrap(a + 2 * math.pi * k / n) for k in range(n)]
            S["assign"][new[0].get("id")] = 0
            S["claimed"].add(0)
            new = new[1:]
        elif tick - S["cal_launch_tick"] > 3:
            S["cal"] = 0
            a = _fwd(0, S["cal_bearing"])
            n = max(1, S["planned"])
            S["slots"] = [_wrap(a + 2 * math.pi * k / n) for k in range(n)]
            S["pending"].append(0)
        else:
            return {"launch": launch, "steer": steer}

    slots = S["slots"]

    # Give each new drone the nearest slot that was launched but not claimed
    for d in new:
        a = ang_of(d)
        best, bd = None, 1e9
        for k in S["pending"]:
            dd = abs(_wrap(slots[k] - a))
            if dd < bd:
                bd, best = dd, k
        if best is None:
            # fallback: nearest unclaimed slot
            for k in range(len(slots)):
                if k in S["claimed"]:
                    continue
                dd = abs(_wrap(slots[k] - a))
                if dd < bd:
                    bd, best = dd, k
        if best is None:
            best = 0
        if best in S["pending"]:
            S["pending"].remove(best)
        S["claimed"].add(best)
        S["assign"][d.get("id")] = best

    # Launch the remaining slots on even bearings
    b = budget
    while (len(launch) < cap and S["next_slot"] < len(slots)
           and b >= s_cost and S["launched"] < S["planned"]):
        k = S["next_slot"]
        launch.append({"type": "striker",
                       "bearing": _inv(S["cal"], slots[k])})
        S["pending"].append(k)
        S["next_slot"] += 1
        S["launched"] += 1
        b -= s_cost

    all_launched = (S["next_slot"] >= len(slots) or b < s_cost
                    or S["launched"] >= S["planned"])

    # Decide whether to release
    if not S["released"]:
        ready = all_launched and not launch and len(S["pending"]) == 0
        if ready:
            for d in drones:
                did = d.get("id")
                k = S["assign"].get(did)
                if k is None:
                    continue
                p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
                dx, dy = float(p[0]) - ax, float(p[1]) - ay
                r = math.hypot(dx, dy)
                err = abs(_wrap(slots[k] - math.atan2(dy, dx)))
                if abs(r - HOLD_R) > 12.0 or err > 0.1:
                    ready = False
                    break
        if ready or tick >= RELEASE_DEADLINE:
            S["released"] = True

    # Steer
    for d in drones:
        did = d.get("id")
        if S["released"]:
            steer[did] = [ax, ay]
            continue
        k = S["assign"].get(did)
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        dx, dy = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(dx, dy)
        phi = math.atan2(dy, dx)
        th = slots[k] if k is not None else phi
        err = _wrap(th - phi)
        if abs(err) > 0.25:
            step = 0.25 if err > 0 else -0.25
            rr = max(r, TRAVEL_MIN_R)
            wa = phi + step
            steer[did] = [ax + rr * math.cos(wa), ay + rr * math.sin(wa)]
        else:
            steer[did] = [ax + HOLD_R * math.cos(th), ay + HOLD_R * math.sin(th)]

    return {"launch": launch, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
