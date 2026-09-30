"""Idea: Probe the engine's bearing convention with the first four launches, then use per-drone dogleg waypoints so every striker crosses the 150 u identification ring on the same tick, evenly spaced around the circle.

Phase-locked ring (attacker).

How it works
------------
1. Tick 0 launches four strikers at requested bearings 0, 90, 180 and 270.
   Read as degrees, those are four compass points. Read as radians, they are
   about 0, 96, 193 and 289 degrees. Either way the probe is spread out. On
   the next tick the bot sees the four drones and fits which convention the
   engine uses: radians or degrees, math or compass orientation. It then aims
   every later launch exactly.
2. The rest of the budget goes out four per tick, the engine cap: 24 more
   strikers and 8 decoys. Final approach slots are 36 bearings spaced evenly
   around the ring.
3. Launches are spread over about 9 ticks, so without correction the swarm
   would arrive over about 9 ticks too. Each drone is steered every tick
   toward a waypoint on the 150 u ring. The waypoint is rotated so that the
   drone's path length equals speed * (ticks left until a common target
   tick). Earlier launches fly a longer dogleg. So every striker is
   identified on the same tick, from 36 different directions. Decoys aim 3
   ticks earlier, slightly ahead of the strikers.

Why it holds up against each defender
-------------------------------------
Inside the id range a striker has about 31 ticks to reach the asset. The
defender can launch only 2 interceptors per tick and holds 20. When about 28
strikers appear at once:

* miss_budget_scheduler: every striker's deadline is equally tight, so its
  model says "only one try fits" for many of them. It then fires pairs,
  which drains its 20-round magazine even faster. Deadline ordering gives it
  nothing to sort by. Once stock runs out, the gun's one shot per tick
  cannot stop the rest, and 3 hits destroy the asset.
* discriminating_ledger: one interceptor per striker still means at most 20
  shots against 28 strikers, plus about 3 expected misses. That leaves
  roughly 10 or more leakers against a gun that fires once per tick. The
  decoys cost it nothing, but they cost us only 4 credits in total.
* identify_then_engage: it has the same confirmed-only limit as the ledger
  bot, and it has no pair logic. The result is the same saturation.
* layered: it engages unknowns near the id ring by time to impact. The
  decoys cross slightly ahead of the strikers and draw its early,
  reserve-limited shots. The striker wave then arrives all at once.
* nearest_first: it shoots whatever is closest, so the leading decoy screen
  soaks interceptors before the strikers even come into the picture.
* gun_only: it gets one shot per tick with low probability at range.
  Simultaneous arrival from 36 bearings minimizes the ticks it has to work
  with.

Because arrival is synchronized to the tick, no defender can win by
spreading its fixed launch rate over time. Launch rate is the resource this
attacker attacks.
"""

import math

NAME = "phase_locked_ring"
ROLE = "attacker"

_S = {}


def reset(seed=None):
    _S.clear()


def _init():
    if "init" not in _S:
        _S.update({
            "init": True,
            "probe_tick": None,
            "mode": None,
            "plan": [],
            "T_arr": None,
        })


PROBE = [0.0, 90.0, 180.0, 270.0]

# Hypotheses: (request -> actual angle in radians, actual angle -> request)
HYP = {
    "rad_math": (lambda b: b, lambda a: a),
    "deg_math": (lambda b: math.radians(b), lambda a: math.degrees(a)),
    "rad_comp": (lambda b: math.pi / 2 - b, lambda a: math.pi / 2 - a),
    "deg_comp": (lambda b: math.pi / 2 - math.radians(b),
                 lambda a: 90.0 - math.degrees(a)),
}


def _adiff(a, b):
    d = (a - b) % (2 * math.pi)
    if d > math.pi:
        d -= 2 * math.pi
    return abs(d)


def _theta(r, rho, L):
    if r <= 1e-6:
        return 0.0
    c = (r * r + rho * rho - L * L) / (2.0 * r * rho)
    c = max(-1.0, min(1.0, c))
    return math.acos(c)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    _init()
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    R = float(rules.get("spawn_radius", 490.0))
    rho = float(rules.get("id_range", 150.0))
    vs = float(rules.get("striker_speed", 4.0))
    vd = float(rules.get("decoy_speed", 4.0))
    cs = float(rules.get("striker_cost", 2.0))
    cd = float(rules.get("decoy_cost", 0.5))
    per_tick = int(rules.get("attacker_launches_per_tick", 4))
    ax, ay = 0.0, 0.0
    try:
        ap = obs.get("asset", {}).get("pos", [0.0, 0.0])
        ax, ay = float(ap[0]), float(ap[1])
    except Exception:
        pass

    drones = obs.get("drones", []) or []
    launch = []
    steer = {}

    # Phase 0: probe launch
    if _S["probe_tick"] is None:
        n = min(per_tick, 4, int(budget // cs))
        for b in PROBE[:n]:
            launch.append({"type": "striker", "bearing": b})
        _S["probe_tick"] = tick
        return {"launch": launch, "steer": steer}

    # Phase 1: detect bearing convention, build plan
    if _S["mode"] is None:
        angs = []
        for d in drones:
            p = d.get("pos", [0, 0])
            angs.append(math.atan2(p[1] - ay, p[0] - ax))
        if not angs and tick - _S["probe_tick"] < 5:
            return {"launch": [], "steer": {}}
        best, berr = "rad_math", float("inf")
        if angs:
            for k, (f, _) in HYP.items():
                preds = [f(b) for b in PROBE]
                err = sum(min(_adiff(a, p) for p in preds) for a in angs)
                if err < berr:
                    best, berr = k, err
        _S["mode"] = best
        f, finv = HYP[best]

        td = tick
        remaining_slots = 36 - 4
        batches = (remaining_slots + per_tick - 1) // max(1, per_tick)
        last = td + batches - 1
        T_arr = last + int(math.ceil((R - rho) / min(vs, vd))) + 4
        _S["T_arr"] = T_arr

        # finals of probe drones
        finals = []
        if angs:
            for d in drones:
                p = d.get("pos", [0, 0])
                x, y = p[0] - ax, p[1] - ay
                r = math.hypot(x, y)
                phi = math.atan2(y, x)
                L = vs * (T_arr - tick)
                finals.append(phi + _theta(r, rho, L))
        else:
            for b in PROBE:
                L = vs * (T_arr - _S["probe_tick"])
                finals.append(f(b) + _theta(R, rho, L))
        offset = finals[0] if finals else 0.0
        step = 2 * math.pi / 36
        slots = [offset + j * step for j in range(36)]
        used = set()
        for fa in finals:
            bj, bd = None, 9.0
            for j, s in enumerate(slots):
                if j in used:
                    continue
                dd = _adiff(s, fa)
                if dd < bd:
                    bj, bd = j, dd
            if bj is not None:
                used.add(bj)
        free = [slots[j] for j in range(36) if j not in used]
        plan = []
        nb = max(1, batches)
        for i, F in enumerate(free):
            typ = "decoy" if i % 4 == 2 else "striker"
            bt = i % nb
            tl = td + bt
            T = T_arr - 3 if typ == "decoy" else T_arr
            spd = vd if typ == "decoy" else vs
            L = spd * (T - tl)
            phi = F - _theta(R, rho, L)
            plan.append((tl, typ, finv(phi)))
        _S["plan"] = plan

    # Launch scheduled drones (strikers first within a tick)
    due = [p for p in _S["plan"] if p[0] <= tick]
    due.sort(key=lambda p: (p[0], 0 if p[1] == "striker" else 1))
    left = budget
    sent = []
    for p in due:
        if len(launch) >= per_tick:
            break
        c = cs if p[1] == "striker" else cd
        typ = p[1]
        if left + 1e-9 < c:
            if left + 1e-9 >= cd:
                typ, c = "decoy", cd
            else:
                sent.append(p)
                continue
        launch.append({"type": typ, "bearing": float(p[2])})
        left -= c
        sent.append(p)
    if sent:
        ss = set(id(p) for p in sent)
        _S["plan"] = [p for p in _S["plan"] if id(p) not in ss]

    # Steering: phase-lock arrival at the id ring
    T_arr = _S["T_arr"]
    if T_arr is not None:
        for d in drones:
            try:
                did = d.get("id")
                p = d.get("pos", [0, 0])
                x, y = p[0] - ax, p[1] - ay
                r = math.hypot(x, y)
                if r <= rho + 6.0:
                    continue
                is_decoy = d.get("type") == "decoy"
                T = T_arr - 3 if is_decoy else T_arr
                spd = vd if is_decoy else vs
                L = spd * (T - tick)
                if L <= (r - rho) + 1.0:
                    steer[did] = None
                    continue
                th = _theta(r, rho, L)
                phi = math.atan2(y, x) + th
                steer[did] = [ax + rho * math.cos(phi), ay + rho * math.sin(phi)]
            except Exception:
                continue

    return {"launch": launch, "steer": steer}
