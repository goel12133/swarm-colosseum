"""Idea: Feint a full synchronized ring dive that stops just outside gun range inside the defender's launch window, then retreat to an orbit beyond interceptor reach so the parked magazine times out, and only then attack.

Name: "Magazine lifetime bleed".

Why this is not the obvious counter
-----------------------------------
The obvious counter to parked_hover_ring_doublecover is to break the ring's geometry.
That means irregular angular spacing, radial staggering wider than DR=8, or arriving in
clumps, so the double-cover blasts stop catching neighbours. This bot does not contest
the blast geometry at all. It attacks the clock instead.

The defender pre-launches parked interceptors whenever enough threats are "soon"
(closing, eta <= 24, which means r <~ 121 at speed 4). It launches until
parked >= ceil(0.8*N)+1. Those interceptors live only 90 ticks. They hover near the
origin and only commit at r<=42, or at age 80, when they have just ~120 units of
flight left.

So the whole ring (all budget spent on strikers) dives radially to r~99, which is
outside the gun's 100 range. That keeps it in the launch window for several ticks while
the defender streams up to 2 interceptors per tick into its parked hover. The ring then
retreats to an orbit at r~220 and rotates evenly. The even rotation keeps the hover
jitter symmetric, so the parked interceptors stay near the origin. They age out, and
their age-80 commits cannot reach the ring. Interceptor counts are watched; if the
magazine is not yet drained, the feint repeats.

The final attack goes in against an empty magazine and the gun alone. It uses two
interleaved half-rings released 4 ticks apart, so whatever stock remains gets single
kills, not triples.
"""
import math

NAME = "magazine_lifetime_bleed_feint_ring"
ROLE = "attacker"

R_HOLD = 220.0
LURE_MIN = 99.0
DIVE_AIM = 55.0
DRAIN_GOAL = 17
STAGGER = 4

_S = {}


def reset(seed=None):
    _S.clear()


def _st():
    if not _S:
        _S.update(phase="gather", rot=0.0, slots={}, sidx={}, assigned=False,
                  n_plan=None, launched=0, t_phase=0, out=set(), cyc_max=0,
                  zero_cnt=0, drained=0, lures=0, t_final=None)
    return _S


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _angdiff(a, b):
    d = abs(a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


def _act(obs):
    st = _st()
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    budget = float(obs.get("budget", 0.0) or 0.0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    cost = float(rules.get("striker_cost", 2.0))
    lpt = int(rules.get("attacker_launches_per_tick", 4))
    max_ticks = int(rules.get("max_ticks", 600))
    spd = float(rules.get("striker_speed", 4.0))
    w = 0.7 * spd / R_HOLD

    if st["n_plan"] is None:
        st["n_plan"] = max(1, int(budget // cost))
    n_plan = st["n_plan"]

    launches = []
    if budget >= cost and st["launched"] < n_plan:
        k = min(lpt, int(budget // cost), n_plan - st["launched"])
        for _ in range(k):
            b = 2 * math.pi * st["launched"] / n_plan
            launches.append({"type": "striker", "bearing": b})
            st["launched"] += 1
    launching_done = (budget < cost) or st["launched"] >= n_plan

    drones = []
    for d in obs.get("drones", []) or []:
        did = d.get("id")
        if did is None:
            continue
        p = d.get("pos") or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        drones.append(dict(id=did, x=x, y=y, r=math.hypot(x, y), a=math.atan2(y, x)))
    ints = obs.get("interceptors", []) or []
    n_int = len(ints)

    # assign evenly spaced slots once everything is launched (robust to bearing units)
    if launching_done and not st["assigned"] and drones and tick > 2:
        ds = sorted(drones, key=lambda d: d["a"])
        base = ds[0]["a"]
        n = len(ds)
        for i, d in enumerate(ds):
            st["slots"][d["id"]] = base + 2 * math.pi * i / n
            st["sidx"][d["id"]] = i
        st["assigned"] = True

    steer = {}

    def pt(r, a):
        return [ax + r * math.cos(a), ay + r * math.sin(a)]

    def hold(d):
        s = st["slots"].get(d["id"])
        if s is None:
            return pt(R_HOLD, d["a"])
        return pt(R_HOLD, s + st["rot"] + 3 * w)

    ph = st["phase"]

    if ph != "final" and tick >= max_ticks - 95:
        ph = st["phase"] = "final"
        st["t_final"] = tick

    if ph == "gather":
        st["rot"] += w
        ready = st["assigned"] and len(drones) > 0
        for d in drones:
            steer[d["id"]] = hold(d)
            s = st["slots"].get(d["id"])
            if s is None or abs(d["r"] - R_HOLD) > 15 or _angdiff(d["a"], s + st["rot"]) > 0.2:
                ready = False
        if ready or (st["assigned"] and tick - st["t_phase"] > 170):
            st["phase"] = "dive"
            st["t_phase"] = tick
            st["out"] = set()
            st["cyc_max"] = 0
    elif ph == "dive":
        st["cyc_max"] = max(st["cyc_max"], n_int)
        for d in drones:
            if d["id"] in st["out"]:
                steer[d["id"]] = pt(R_HOLD, d["a"])
            elif d["r"] <= LURE_MIN:
                st["out"].add(d["id"])
                steer[d["id"]] = pt(R_HOLD, d["a"])
            else:
                steer[d["id"]] = pt(DIVE_AIM, d["a"])
        if all(d["id"] in st["out"] for d in drones) or tick - st["t_phase"] > 45:
            st["phase"] = "retreat"
            st["t_phase"] = tick
            st["zero_cnt"] = 0
    elif ph == "retreat":
        st["cyc_max"] = max(st["cyc_max"], n_int)
        st["rot"] += w
        st["zero_cnt"] = st["zero_cnt"] + 1 if n_int == 0 else 0
        far = True
        for d in drones:
            steer[d["id"]] = hold(d)
            if d["r"] < R_HOLD - 25:
                far = False
        el = tick - st["t_phase"]
        if (el >= 25 and st["zero_cnt"] >= 3 and far) or el > 130:
            st["drained"] += st["cyc_max"]
            st["lures"] += 1
            if st["drained"] < DRAIN_GOAL and st["lures"] < 3 and tick < max_ticks - 270:
                st["phase"] = "dive"
                st["out"] = set()
                st["cyc_max"] = 0
            else:
                st["phase"] = "final"
                st["t_final"] = tick
            st["t_phase"] = tick
    else:  # final
        tf = st["t_final"] if st["t_final"] is not None else tick
        st["rot"] += w
        for d in drones:
            i = st["sidx"].get(d["id"])
            rel = tf + (STAGGER if (i is not None and i % 2 == 1) else 0)
            if tick >= rel or i is None:
                steer[d["id"]] = None
            else:
                steer[d["id"]] = hold(d)

    return {"launch": launches, "steer": steer}
