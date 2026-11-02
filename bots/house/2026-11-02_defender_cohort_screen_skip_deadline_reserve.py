"""Idea: Sort tracks by radar-entry cohort so the first-arriving screen gets no fire, put 16 interceptors on the striker shells at the radar edge, and hold 4 for terminal targets that a deadline-simulated gun cannot reach in time.

What this attacks in hidden_orbit_screen_then_interleaved_drop:
- Its release schedule is fixed, and its strikers cannot hide inside it. Every drone
  waits on the r=482 orbit. The 16 decoys are released at tick 14 and cross the
  450 radar ring together at about tick 22. Shell A (tick 27) and shell B (tick 31)
  cross about 13 and 17 ticks later. The first cohort to enter radar is always the
  pure screen and every later cohort is pure striker, long before the 150 ID ring.
  Its docstring counts on defenders that "hold fire until ID" to compress the
  engagement window. We need no ID, so we fire at the strikers from r~450
  and leave ID only to confirm or overrule the cohort guess.
- Replays: in its two closest calls (hover_bank_double_lattice, seeds 3 and 5)
  every decoy flew harmlessly into the asset at tick 128. The defender won only
  by killing all 26 strikers, with 17-19 interceptor kills plus 7-9 gun kills from
  22 shots. Its mean score_defender is 0.08-0.13 against nearest_first, layered and
  annealed_eager, which shoot at unknowns. So the margin lies in two places: never
  spending a round on the screen, and never letting the gun face more terminal
  strikers than it can kill before impact.
- Blast-proof spacing makes doubles impossible, so each interceptor is one striker.
  We spread 16 early rounds evenly across the two shells, one per striker, and
  retarget at once when a target dies. Near the end we simulate the gun's queue
  against each survivor's time to impact. Reserve rounds go only to strikers the
  gun would miss, and the gun never shoots a decoy.
"""
import math

NAME = "cohort_screen_skip_deadline_reserve"
ROLE = "defender"

RESERVE = 4
COHORT_GAP = 4
STABLE_TICKS = 6
EARLY_TRIGGER_R = 330.0
LATE_R = 170.0
TPK = 2.5

_s = {}


def reset(seed=None):
    _s.clear()
    _s["cohort_of"] = {}
    _s["cohorts"] = []      # [start, last]
    _s["ev"] = []           # [striker_ev, decoy_ev]
    _s["known"] = {}
    _s["last_new"] = -100


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _rng(t, ax, ay):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(p[0] - ax, p[1] - ay)
    return float(r)


def _act(obs):
    if "cohort_of" not in _s:
        reset(None)
    tick = obs.get("tick", 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    spd = float(rules.get("striker_speed", 4.0)) or 4.0

    cohort_of = _s["cohort_of"]
    cohorts = _s["cohorts"]
    ev = _s["ev"]
    known = _s["known"]

    alive = {}
    for t in tracks:
        tid = t["id"]
        alive[tid] = t
        if tid not in cohort_of:
            if cohorts and tick - cohorts[-1][1] <= COHORT_GAP:
                cohorts[-1][1] = tick
            else:
                cohorts.append([tick, tick])
                ev.append([0, 0])
            cohort_of[tid] = len(cohorts) - 1
            _s["last_new"] = tick
        c = t.get("cls")
        if c in ("striker", "decoy") and tid not in known:
            known[tid] = c
            k = cohort_of[tid]
            ev[k][0 if c == "striker" else 1] += 1

    def kind(tid):
        c = known.get(tid)
        if c:
            return c
        k = cohort_of.get(tid, 0)
        s_ev, d_ev = ev[k]
        if s_ev > d_ev:
            return "striker"
        if k > 0 and d_ev == 0:
            return "striker"
        return "hold"

    rng = {tid: _rng(t, ax, ay) for tid, t in alive.items()}
    eligible = [tid for tid in alive if kind(tid) == "striker"]
    elig_set = set(eligible)

    assigned = {}
    for it in ints:
        tg = it.get("target")
        if tg in alive:
            assigned[tg] = assigned.get(tg, 0) + 1

    # retarget interceptors whose targets died or turned out to be decoys
    retarget = {}
    for it in ints:
        tg = it.get("target")
        if tg in alive and tg in elig_set:
            continue
        ip = it.get("pos", [ax, ay])
        best, bd = None, 1e18
        for tid in eligible:
            if assigned.get(tid, 0) > 0:
                continue
            p = alive[tid]["pos"]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d < bd:
                bd, best = d, tid
        if best is None:
            for tid in eligible:
                p = alive[tid]["pos"]
                d = math.hypot(p[0] - ip[0], p[1] - ip[1])
                if d < bd:
                    bd, best = d, tid
        if best is not None:
            if tg in assigned:
                assigned[tg] -= 1
            retarget[it["id"]] = best
            assigned[best] = assigned.get(best, 0) + 1

    launches = []
    avail = stock

    # late phase: deadline-simulate gun, reserve rounds go to overflow
    unassigned = sorted([tid for tid in eligible if assigned.get(tid, 0) == 0],
                        key=lambda x: rng[x])
    tg_time = 0.0
    overflow = []
    for tid in unassigned:
        r = rng[tid]
        enter = max(0.0, (r - gun_range) / spd)
        impact = max(0.0, (r - arad) / spd)
        start = max(tg_time, enter)
        if start + TPK <= impact:
            tg_time = start + TPK
        else:
            overflow.append(tid)
    for tid in overflow:
        if len(launches) >= cap or avail <= 0:
            break
        r = rng[tid]
        if r <= LATE_R and r > arad + 4.0:
            launches.append(tid)
            assigned[tid] = assigned.get(tid, 0) + 1
            avail -= 1

    # early phase: commit on striker cohorts, balanced across cohorts
    pool = [tid for tid in eligible if assigned.get(tid, 0) == 0]
    if pool:
        min_r = min(rng[t] for t in pool)
        stable = tick - _s["last_new"] >= STABLE_TICKS
        if stable or min_r < EARLY_TRIGGER_R:
            while len(launches) < cap and avail > RESERVE and pool:
                size, done = {}, {}
                for tid in eligible:
                    k = cohort_of[tid]
                    size[k] = size.get(k, 0) + 1
                    if assigned.get(tid, 0) > 0:
                        done[k] = done.get(k, 0) + 1

                def key(tid):
                    k = cohort_of[tid]
                    return (done.get(k, 0) / float(size[k]), rng[tid])
                pool.sort(key=key)
                tid = pool.pop(0)
                launches.append(tid)
                assigned[tid] = assigned.get(tid, 0) + 1
                avail -= 1

    # gun: strikers only, prefer ones with no interceptor inbound, nearest first
    gun = None
    if ammo > 0:
        cands = [tid for tid in eligible if rng[tid] <= gun_range]
        if cands:
            free = [t for t in cands if assigned.get(t, 0) == 0]
            src = free if free else cands
            gun = min(src, key=lambda x: rng[x])

    return {"intercept": launches, "retarget": retarget, "gun": gun}
