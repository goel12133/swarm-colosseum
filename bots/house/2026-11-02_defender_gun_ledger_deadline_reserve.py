"""Idea: Treat the gun as a measured kill budget, not a backstop: spend the magazine early only on the trailing cohort, down to the gun's online-estimated capacity plus a 5-round reserve, then release that reserve by deadline only at strikers the gun has failed to stop.

Target: the striker-count sizing in hidden_orbit_screen_then_interleaved_drop.
- Its docstring says 26 strikers are "more than the 20-round magazine at
  pk 0.85 plus the gun can stop". That only holds against a defender that
  dumps the magazine as one pulse at the ID ring. Once that pulse is spent,
  the gun is left alone against both shells.
- Its two closest calls (vs hover_bank_double_lattice, seeds 3 and 5) were
  both decided by the gun. The defender won with 9 and 7 gun kills from 22
  shots, plus 17 and 19 interceptor kills from 19 rounds.
- In both of those games, all 16 decoys impacted harmlessly at tick 128.
  So the decoy screen never mattered there. The only swing factor was how
  the magazine and the gun split the 26 strikers.

Timing this exploits:
- Decoys are released at tick 14 and strikers at ticks 27 and 31.
- So the strikers first show up on radar about 52 units behind a cohort
  already inside 450 range. A track born while another track is 30 or more
  units deeper is presumed to be a striker before it reaches the ID ring.
- The two shells cross the 100-unit gun line 4 ticks apart. That gives
  about 23 gun ticks.

How this bot uses it:
- Ledger: fire early, far out, at presumed or confirmed strikers until
  uncovered strikers <= expected gun kills + min(stock, 5).
- Early fire leaves time to notice interceptor misses and re-cover them.
- The gun shoots the nearest uncovered striker. It never spends a shot on
  a striker an interceptor is already chasing.
- Every tick, a deadline check asks whether the gun can still clear the
  k-th striker before it impacts. Any striker it cannot clear gets a
  reserve interceptor just in time, so no round goes to a striker the gun
  would have killed anyway.
- Gun pk is estimated online from observed shot results.
"""
import math

NAME = "gun_ledger_deadline_reserve"
ROLE = "defender"

RES = 5
PRIOR_PK = 0.35
PRIOR_W = 6.0
GUN_WINDOW = 22.0
TRAIL_GAP = 30.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["trailing"] = {}
    _s["gun_last"] = None
    _s["g_hit"] = 0
    _s["g_miss"] = 0
    _s["prev_targets"] = set()


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    S = _s
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)) or 25.0)
    speed = float(rules.get("striker_speed", 4.0) or 4.0)
    gr = float(rules.get("gun_range", 100.0) or 100.0)
    cap = int(rules.get("interceptor_launches_per_tick", 2) or 2)
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    tr = {}
    rngs = {}
    for t in obs.get("tracks", []) or []:
        tid = t.get("id")
        if tid is None:
            continue
        tr[tid] = t
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0.0, 0.0])
            r = math.hypot(p[0] - ax, p[1] - ay)
        rngs[tid] = float(r)

    # ---- birth classification: trailing cohort ----
    fs = S["first_seen"]
    existing = [rngs[tid] for tid in tr if tid in fs]
    rmin_ex = min(existing) if existing else None
    for tid in tr:
        if tid not in fs:
            fs[tid] = tick
            S["trailing"][tid] = (rmin_ex is not None and
                                  rmin_ex <= rngs[tid] - TRAIL_GAP)

    # ---- online gun pk estimate ----
    gl = S["gun_last"]
    if gl is not None and gl[1] == tick - 1:
        gid = gl[0]
        if gid in tr:
            S["g_miss"] += 1
        elif gid not in S["prev_targets"]:
            S["g_hit"] += 1
    S["gun_last"] = None
    p_est = (S["g_hit"] + PRIOR_PK * PRIOR_W) / (S["g_hit"] + S["g_miss"] + PRIOR_W)
    p_eff = p_est * 0.85 if ammo > 0 else 0.0

    def is_threat(tid):
        t = tr[tid]
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if S["trailing"].get(tid, False):
            return True
        # unknown deep inside id range: failsafe
        return rngs[tid] < min(gr, 120.0)

    threats = [tid for tid in tr if is_threat(tid)]
    tset = set(threats)

    def T(tid):
        return max(0.0, rngs[tid] - arad) / speed

    # ---- coverage and retargeting ----
    cover = {}
    orphans = []
    targets_now = set()
    for it in obs.get("interceptors", []) or []:
        tg = it.get("target")
        if tg in tset:
            cover[tg] = cover.get(tg, 0) + 1
            targets_now.add(tg)
        else:
            orphans.append(it)
    retarget = {}
    for it in orphans:
        if not threats:
            break
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        unc = [x for x in threats if cover.get(x, 0) == 0]
        pool = unc if unc else threats

        def d(x):
            p = tr[x].get("pos", [ax, ay])
            return math.hypot(p[0] - ip[0], p[1] - ip[1])
        best = min(pool, key=d)
        retarget[it.get("id")] = best
        cover[best] = cover.get(best, 0) + 1
        targets_now.add(best)

    uncovered = sorted([x for x in threats if cover.get(x, 0) == 0], key=T)

    launches = []
    stock_left = stock

    # ---- deadline finisher: strikers the gun cannot be expected to clear ----
    if uncovered and stock_left > 0:
        rmin_u = min(rngs[x] for x in uncovered)
        t_gs = max(0.0, (rmin_u - gr) / speed)
        j = 0
        for k, tid in enumerate(uncovered, 1):
            Tk = T(tid)
            capk = p_eff * max(0.0, Tk - t_gs)
            if k > capk + 0.5:
                j += 1
                if Tk <= 7 + math.ceil(j / 2.0) and Tk >= 0.5:
                    if len(launches) < cap and stock_left > 0:
                        launches.append(tid)
                        stock_left -= 1

    # ---- early ledger: thin trailing cohort down to gun + reserve ----
    rem = [x for x in uncovered if x not in launches]
    if rem and stock_left > 0 and len(launches) < cap:
        G = min(p_eff * GUN_WINDOW, 0.6 * len(rem))

        def pairs(x):
            p = tr[x].get("pos", [0, 0])
            n = 0
            for y in threats:
                if y == x:
                    continue
                q = tr[y].get("pos", [0, 0])
                if math.hypot(p[0] - q[0], p[1] - q[1]) < 12.0:
                    n += 1
            return n

        while len(launches) < cap and stock_left > 0 and rem:
            excess = len(rem) - G - min(stock_left, RES)
            if excess <= 0:
                break
            best = min(rem, key=lambda x: T(x) - 3.0 * pairs(x))
            launches.append(best)
            rem.remove(best)
            stock_left -= 1

    for x in launches:
        cover[x] = cover.get(x, 0) + 1
        targets_now.add(x)

    # ---- gun: nearest uncovered striker in range ----
    gun = None
    if ammo > 0:
        cand = [x for x in threats if rngs[x] <= gr]
        if cand:
            unc = [x for x in cand if cover.get(x, 0) == 0]
            pool = unc if unc else cand
            gun = min(pool, key=lambda x: rngs[x])
        if gun is not None:
            S["gun_last"] = (gun, tick)

    S["prev_targets"] = targets_now
    return {"intercept": launches, "retarget": retarget, "gun": gun}
