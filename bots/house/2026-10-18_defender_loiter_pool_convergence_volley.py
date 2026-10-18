"""Idea: Park the whole interceptor magazine as a loitering pool bouncing around the origin, then commit it all at once with no launch cap when a ring converges, aiming every blast at a predicted point where neighbouring strikers sit inside one blast radius.

Weakness exploited
------------------
2026-10-09_attacker_attacker_blast_isolated_synchronized_rel (worst attacker,
5% win rate) beat gun_only 0.316 (seed 0: 26 strikers, 10 simultaneous impacts
at tick 120, zero interceptors launched). Its whole bet is a perfectly
synchronized release from an r=130 staging ring, sized so that neighbours are
"just past one blast width" at r=40. The sizing was checked against a
conservative 0.9*blast coverage, not the real 10-unit radius, and it ignores
what happens further in. Because all 26 run inward on the same tick at the same
speed, the shrinking ring is fully predictable. At r~36 the spacing is about
8.7, so one blast centred on a striker also reaches both neighbours.

The 2-per-tick launch cap is what normally stops a defender from cashing that
moment in, since nobody can put 20 interceptors on a ring in 3 ticks from the
silo. This bot does not launch at the ring. It launches the magazine early,
while the attacker parks, and keeps the interceptors near the origin. Each one
is retargeted every tick to the far track most opposite its own position, so it
oscillates in place. When the ring is a tick away from the planned meet radius,
the bot commits the pool by retarget, which has no cap. Blast points are chosen
greedily to cover the most uncovered strikers, and a second pass double-covers
for pk misses. The gun takes the closest striker that is still uncovered.
"""
import math

NAME = "loiter_pool_convergence_volley"
ROLE = "defender"

_S = {}


def reset(seed=None):
    _S.clear()


def _init():
    if "f" not in _S:
        _S["f"] = {}
        _S["committed"] = {}
        _S["pending"] = []


def _meet(q, p, v, s):
    dx, dy = p[0] - q[0], p[1] - q[1]
    a = v[0] * v[0] + v[1] * v[1] - s * s
    b = 2.0 * (dx * v[0] + dy * v[1])
    c = dx * dx + dy * dy
    if a >= -1e-6:
        return math.sqrt(c) / s
    disc = b * b - 4 * a * c
    if disc < 0:
        disc = 0.0
    t = (-b - math.sqrt(disc)) / (2 * a)
    if t < 0:
        t = math.sqrt(c) / s
    return t


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    _init()
    rules = obs.get("rules", {}) or {}
    AR = float(rules.get("asset_radius", 25.0))
    GUN = float(rules.get("gun_range", 100.0))
    IS = float(rules.get("interceptor_speed", 12.0))
    BL = float(rules.get("blast_radius", 10.0))
    LIFE = int(rules.get("interceptor_lifetime", 90))
    CAP = int(rules.get("interceptor_launches_per_tick", 2))
    COVER = 0.9 * BL
    MEET_R = AR + 11.0
    tick = obs.get("tick", 0)
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))

    # --- filter tracks
    F = _S["f"]
    tracks = obs.get("tracks", []) or []
    tinfo = {}
    seen = set()
    for t in tracks:
        tid = t["id"]
        seen.add(tid)
        zx, zy = float(t["pos"][0]), float(t["pos"][1])
        if tid not in F:
            vv = t.get("vel") or [0.0, 0.0]
            F[tid] = [zx, zy, float(vv[0]), float(vv[1]), tick]
        else:
            st = F[tid]
            dt = max(1, tick - st[4])
            px, py = st[0] + st[2] * dt, st[1] + st[3] * dt
            rx, ry = zx - px, zy - py
            st[0] = px + 0.45 * rx
            st[1] = py + 0.45 * ry
            st[2] += 0.15 * rx / dt
            st[3] += 0.15 * ry / dt
            sp = math.hypot(st[2], st[3])
            if sp > 6.0:
                st[2] *= 6.0 / sp
                st[3] *= 6.0 / sp
            st[4] = tick
        st = F[tid]
        R = max(1e-6, math.hypot(st[0], st[1]))
        clos = -(st[0] * st[2] + st[1] * st[3]) / R
        tinfo[tid] = {"p": (st[0], st[1]), "v": (st[2], st[3]), "R": R,
                      "clos": clos, "cls": t.get("cls", "unknown"),
                      "orng": float(t.get("range", R))}
    for k in list(F.keys()):
        if k not in seen:
            del F[k]

    def pred(k, tm):
        i = tinfo[k]
        return (i["p"][0] + i["v"][0] * tm, i["p"][1] + i["v"][1] * tm)

    threats = [k for k in tinfo if tinfo[k]["cls"] != "decoy"]

    # --- interceptors
    inters = obs.get("interceptors", []) or []
    ipos, iage, itgt = {}, {}, {}
    for it in inters:
        ipos[it["id"]] = (float(it["pos"][0]), float(it["pos"][1]))
        iage[it["id"]] = int(it.get("age", 0))
        itgt[it["id"]] = it.get("target")
    committed = _S["committed"]
    for iid in list(committed.keys()):
        if iid not in ipos or committed[iid] not in tinfo:
            del committed[iid]
    pending = _S["pending"]
    for iid in ipos:
        if iid not in committed and itgt.get(iid) in pending and itgt[iid] in tinfo:
            committed[iid] = itgt[iid]
            pending.remove(itgt[iid])
    _S["pending"] = []
    pool = [i for i in ipos if i not in committed]

    # --- coverage from committed interceptors
    cover = {k: 0.0 for k in threats}

    def apply_cover(q, tid):
        i = tinfo[tid]
        tm = _meet(q, i["p"], i["v"], IS)
        M = pred(tid, tm)
        got = []
        for k in threats:
            if k == tid:
                got.append(k)
                continue
            P = pred(k, tm)
            if math.hypot(P[0] - M[0], P[1] - M[1]) <= COVER:
                got.append(k)
        return got, tm, M

    for iid, tid in committed.items():
        if tid in cover:
            got, _, _ = apply_cover(ipos[iid], tid)
            for k in got:
                cover[k] += 1

    active = [k for k in threats
              if tinfo[k]["clos"] > 1.0 or tinfo[k]["R"] < 70.0]

    retarget = {}
    intercept = []

    def rm_from(q, k):
        i = tinfo[k]
        tm = _meet(q, i["p"], i["v"], IS)
        P = pred(k, tm)
        return math.hypot(P[0], P[1]), tm

    def best_rm(k, qs):
        best = -1.0
        for q in qs:
            r, _ = rm_from(q, k)
            if r > best:
                best = r
        return best

    poolq = [ipos[i] for i in pool]
    rmx = {}
    for k in active:
        qs = poolq if poolq else [(0.0, 0.0)]
        rmx[k] = best_rm(k, qs)

    def triggered(k):
        c = max(tinfo[k]["clos"], 0.5)
        tti = (tinfo[k]["R"] - AR) / c
        return rmx[k] - 0.8 * c <= MEET_R or tti < 4.0

    def greedy(level, budget_n):
        used = 0
        while pool and used < budget_n:
            trig = [k for k in active if cover[k] < level and triggered(k)]
            if not trig:
                break
            cands = [k for k in active if rmx[k] <= MEET_R + 12.0] or trig
            best = None
            for c in cands:
                bi, btm = None, 1e9
                for iid in pool:
                    tm = _meet(ipos[iid], tinfo[c]["p"], tinfo[c]["v"], IS)
                    if tm < btm:
                        btm, bi = tm, iid
                got, tm, M = apply_cover(ipos[bi], c)
                gt = sum(2 for k in got if k in trig)
                if gt == 0:
                    continue
                gain = gt + sum(1 for k in got if cover[k] < level and k not in trig)
                key = (gain, -abs(math.hypot(M[0], M[1]) - MEET_R))
                if best is None or key > best[0]:
                    best = (key, c, bi, got)
            if best is None:
                break
            _, c, bi, got = best
            committed[bi] = c
            pool.remove(bi)
            retarget[bi] = c
            for k in got:
                cover[k] += 1
            used += 1

    greedy(1, 99)
    if pool:
        far_uncov = sum(1 for k in threats if cover[k] < 1 and k not in active)
        reserve = int(math.ceil(0.4 * far_uncov))
        greedy(2, max(0, len(pool) - reserve))

    # --- aging pool interceptors: spend before expiry
    for iid in list(pool):
        if iage.get(iid, 0) >= LIFE - 12 and active:
            k = min(active, key=lambda k: (cover[k], tinfo[k]["R"]))
            committed[iid] = k
            pool.remove(iid)
            retarget[iid] = k
            for g in apply_cover(ipos[iid], k)[0]:
                cover[g] += 1

    # --- launches from silo (backscheduled, cap-aware)
    launches_left = min(CAP, stock)
    if launches_left > 0:
        need = []
        for k in active:
            if cover[k] >= 1:
                continue
            r0, _ = rm_from((0.0, 0.0), k)
            c = max(tinfo[k]["clos"], 0.5)
            slack = (r0 - MEET_R) / (0.75 * c)
            need.append((slack, k))
        need.sort()
        for idx, (slack, k) in enumerate(need):
            if launches_left <= 0:
                break
            if cover[k] >= 1:
                continue
            if slack < idx // max(1, CAP) + 1.5:
                intercept.append(k)
                _S["pending"].append(k)
                launches_left -= 1
                for g in apply_cover((0.0, 0.0), k)[0]:
                    cover[g] += 1

    # --- deploy loiter pool
    far = [k for k in tinfo if tinfo[k]["R"] > 100.0]
    near_thr = [k for k in threats if tinfo[k]["R"] < 300.0]
    deploy = False
    for k in threats:
        i = tinfo[k]
        if i["R"] < 260.0:
            tti = (i["R"] - AR) / max(i["clos"], 0.5)
            if (i["clos"] > 1.0 and tti < 55.0) or i["R"] < 170.0:
                deploy = True
                break
    if deploy and far and launches_left > 0:
        target_n = min(int(rules.get("interceptor_stock", 20)),
                       int(math.ceil(0.75 * len(near_thr))) + 2)
        inv = len(ipos) + len(intercept)
        dummy = max(far, key=lambda k: tinfo[k]["R"])
        while launches_left > 0 and inv < target_n:
            intercept.append(dummy)
            launches_left -= 1
            inv += 1

    # --- loiter: retarget pool to far tracks opposite own position
    for iid in pool:
        if not far:
            break
        q = ipos[iid]
        nq = math.hypot(q[0], q[1])
        cur = itgt.get(iid)
        if nq > 4.0:
            ux, uy = q[0] / nq, q[1] / nq
            pick = min(far, key=lambda k: (ux * tinfo[k]["p"][0] + uy * tinfo[k]["p"][1]) / tinfo[k]["R"])
        else:
            pick = cur if cur in far else max(far, key=lambda k: tinfo[k]["R"])
        if pick != cur:
            retarget[iid] = pick
    for iid, tid in committed.items():
        if itgt.get(iid) != tid and iid not in retarget:
            retarget[iid] = tid

    # --- gun
    gun = None
    if ammo > 0:
        inr = [k for k in threats if tinfo[k]["orng"] <= GUN]
        if inr:
            unc = [k for k in inr if cover[k] < 1]
            pickset = unc if unc else inr
            gun = min(pickset, key=lambda k: tinfo[k]["orng"])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
