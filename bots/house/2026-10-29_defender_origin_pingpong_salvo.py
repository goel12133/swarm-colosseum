"""Idea: Hold the interceptor magazine as a hovering reserve at the origin by retargeting each interceptor every tick toward a track on the far side, then release it in one same-tick salvo timed so the blasts land where a converging ring is packed tighter than one blast radius.

Target weakness
---------------
Pairing: 2026-10-09_attacker_attacker_blast_isolated_synchronized_rel vs gun_only,
mean score_defender 0.316. In seed 0 all ten impacts landed on tick 120. gun_only
launched no interceptors and fired its gun only about 20 times.

That attacker sizes its ring to the radius where the scheduler engages, r=40. There,
26 strikers sit 9.66 apart, just over 0.9*blast. It then makes every striker share
the same radius at the same tick, by staging them at r=130 and releasing them
together. A ring that is kept in sync this way keeps shrinking. At r~33 the arc
spacing is 2*pi*33/26 ~ 8, which is below the 10-unit blast radius. One blast aimed
at a striker then also reaches both of its neighbours. The attacker's isolation
argument only holds at the radius it checked.

The synchronized release also limits a normal defender. It can launch only 2
interceptors per tick, so it cannot fire many interceptors in the ~3 ticks the ring
spends below r~45.

What this bot does
------------------
1. Reserve. When threats come within about 60 ticks of impact (worst-case speed),
   the bot launches interceptors early. Each tick it retargets each one at whichever
   track lies most directly back across the origin. The interceptors therefore
   shuttle back and forth within ~12 units of the asset. They count as already
   launched, so the 2-per-tick launch cap no longer limits the salvo.
2. Deadline trigger. For each threat, the bot solves the intercept from the origin.
   It fires once the predicted meet radius would drop below asset_radius+8 on the
   next tick. Stock launches are pulled earlier when the 2-per-tick cap requires it.
   Against a synchronized ring, all strikers trigger on the same tick.
3. Greedy coverage salvo. The bot picks aim tracks one at a time to maximise
   expected kills. A blast counts against every threat predicted to be within
   0.85*blast of the meet point at meet time, weighted by that threat's current
   survival. Every triggered threat is covered at least once. Spare interceptors
   then add second coverage, unless other threats are still incoming.
4. Cleanup. Interceptors whose target is gone are retargeted to the most urgent
   uncovered threat. The gun shoots the nearest-to-impact uncovered threat. Reserve
   interceptors about to expire are spent on the most urgent threat. If tracks do
   not surround the asset, so the reserve cannot hover, the bot falls back to
   as-late-as-feasible launch scheduling.
"""
import math

NAME = "origin_pingpong_salvo"
ROLE = "defender"

_S = {}


def _init():
    _S.clear()
    _S["role"] = {}
    _S["pend"] = []
    _S["hist"] = {}


def reset(seed=None):
    _init()


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _xy(p):
    try:
        return float(p[0]), float(p[1])
    except Exception:
        return 0.0, 0.0


def _act(obs):
    if not _S:
        _init()
    S = _S
    R = obs.get("rules") or {}
    asset = obs.get("asset") or {}
    AR = float(asset.get("radius", R.get("asset_radius", 25.0)))
    ax, ay = _xy(asset.get("pos", (0.0, 0.0)))
    IS = float(R.get("interceptor_speed", 12.0))
    BR = float(R.get("blast_radius", 10.0))
    PK = float(R.get("interceptor_kill_prob", 0.85))
    LIFE = int(R.get("interceptor_lifetime", 90))
    LPT = int(R.get("interceptor_launches_per_tick", 2))
    GR = float(R.get("gun_range", 100.0))
    VMAX = max(float(R.get("striker_speed", 4.0)), float(R.get("decoy_speed", 4.0)), 0.5)
    tick = int(obs.get("tick", 0))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    CR = 0.85 * BR
    RC = AR + 8.0

    # ---------------- tracks ----------------
    tracks = {}
    hist = S["hist"]
    for t in obs.get("tracks") or []:
        tid = t.get("id")
        if tid is None:
            continue
        px, py = _xy(t.get("pos", (0, 0)))
        px -= ax
        py -= ay
        vx, vy = _xy(t.get("vel") or (0, 0))
        h = hist.setdefault(tid, [])
        h.append((tick, px, py))
        if len(h) > 6:
            del h[0]
        if len(h) >= 4:
            t0, x0, y0 = h[0]
            dt = tick - t0
            if dt > 0:
                vx = 0.5 * vx + 0.5 * (px - x0) / dt
                vy = 0.5 * vy + 0.5 * (py - y0) / dt
        r = math.hypot(px, py)
        vc = -(px * vx + py * vy) / r if r > 1e-6 else 0.0
        cls = t.get("cls", "unknown")
        tracks[tid] = {"id": tid, "x": px, "y": py, "vx": vx, "vy": vy,
                       "r": r, "vc": vc, "threat": cls != "decoy"}
    if tick % 20 == 0:
        for k in list(hist.keys()):
            if k not in tracks:
                del hist[k]

    def meet(d, qx=0.0, qy=0.0):
        px = d["x"] - qx
        py = d["y"] - qy
        vx, vy = d["vx"], d["vy"]
        a = vx * vx + vy * vy - IS * IS
        b = 2.0 * (px * vx + py * vy)
        c = px * px + py * py
        if a >= -1e-9:
            tm = math.sqrt(c) / IS
        else:
            disc = b * b - 4 * a * c
            if disc < 0:
                disc = 0.0
            tm = (-b - math.sqrt(disc)) / (2 * a)
            if tm < 0:
                tm = math.sqrt(c) / IS
        return tm, d["x"] + vx * tm, d["y"] + vy * tm

    # ---------------- interceptors & roles ----------------
    role = S["role"]
    pend = S["pend"]
    ints = []
    seen = set()
    for it in obs.get("interceptors") or []:
        iid = it.get("id")
        if iid is None:
            continue
        x, y = _xy(it.get("pos", (0, 0)))
        rec = {"id": iid, "target": it.get("target"), "x": x - ax, "y": y - ay,
               "age": int(it.get("age", 0) or 0)}
        ints.append(rec)
        seen.add(iid)
        if iid not in role:
            rl = "engage"
            for k, (pt, pr) in enumerate(pend):
                if pt == rec["target"]:
                    rl = pr
                    del pend[k]
                    break
            role[iid] = rl
    for k in list(role.keys()):
        if k not in seen:
            del role[k]
    S["pend"] = []
    new_pend = []

    retarget = {}
    intercept = []
    launched = 0

    threats = [d for d in tracks.values() if d["threat"]]
    surv = {d["id"]: 1.0 for d in threats}

    def apply_blast(tm, mx, my):
        for e in threats:
            ex = e["x"] + e["vx"] * tm
            ey = e["y"] + e["vy"] * tm
            if (ex - mx) ** 2 + (ey - my) ** 2 <= CR * CR:
                surv[e["id"]] *= (1.0 - PK)

    def gain(tm, mx, my):
        g = 0.0
        for e in threats:
            s = surv[e["id"]]
            if s < 0.02:
                continue
            ex = e["x"] + e["vx"] * tm
            ey = e["y"] + e["vy"] * tm
            if (ex - mx) ** 2 + (ey - my) ** 2 <= CR * CR:
                g += s * PK
        return g

    def urgency(d):
        return (d["r"] - AR) / max(d["vc"], 0.5)

    engaged = [i for i in ints if role.get(i["id"]) == "engage"]
    loiter = [i for i in ints if role.get(i["id"]) == "loiter"]

    orphans = []
    for i in engaged:
        tg = i["target"]
        if tg in tracks and tracks[tg]["threat"]:
            tm, mx, my = meet(tracks[tg], i["x"], i["y"])
            apply_blast(tm, mx, my)
        else:
            orphans.append(i)
    for i in orphans:
        cands = [d for d in threats if surv[d["id"]] > 0.3 and d["r"] < 250]
        if not cands:
            cands = [d for d in threats if surv[d["id"]] > 0.05 and d["r"] < 250]
        if cands:
            d = min(cands, key=lambda d: (urgency(d), math.hypot(d["x"] - i["x"], d["y"] - i["y"])))
            retarget[i["id"]] = d["id"]
            tm, mx, my = meet(d, i["x"], i["y"])
            apply_blast(tm, mx, my)
        else:
            role[i["id"]] = "loiter"
            loiter.append(i)

    # expiring loiterers: spend on most urgent threat
    keep = []
    for i in loiter:
        if i["age"] >= LIFE - 8:
            cands = [d for d in threats if surv[d["id"]] > 0.05]
            if cands:
                d = min(cands, key=lambda d: (-surv[d["id"]], urgency(d)))
                retarget[i["id"]] = d["id"]
                role[i["id"]] = "engage"
                tm, mx, my = meet(d, i["x"], i["y"])
                apply_blast(tm, mx, my)
                continue
        keep.append(i)
    loiter = keep

    # ---------------- trigger ----------------
    info = {}
    U = []
    for d in threats:
        if surv[d["id"]] <= 0.3:
            continue
        if d["vc"] <= 0.3 and d["r"] > AR + 30:
            continue
        tm, mx, my = meet(d)
        rm = math.hypot(mx, my)
        nd = dict(d)
        nd["x"] += d["vx"]
        nd["y"] += d["vy"]
        _, mx2, my2 = meet(nd)
        dr = rm - math.hypot(mx2, my2)
        if rm <= RC:
            tum = 0.0
        elif dr > 0.05:
            tum = (rm - RC) / dr
        else:
            tum = float("inf")
        info[d["id"]] = (tm, mx, my)
        U.append((tum, d))
    U.sort(key=lambda z: z[0])
    L = len(loiter)
    B = []
    for idx, (tum, d) in enumerate(U):
        k = idx + 1 - L
        k = min(k, stock)
        req = 0 if k <= 0 else int(math.ceil(k / float(LPT)))
        if tum < 1.0 + req:
            B.append(d)

    if B:
        bset = set(d["id"] for d in B)
        fut = sum(1 for d in threats if d["id"] not in bset and surv[d["id"]] > 0.3)
        thr = 0.1 if fut == 0 else 0.45
        free_loit = list(loiter)

        def avail():
            return len(free_loit) + max(0, min(stock - launched, LPT - launched))

        def fire(d):
            nonlocal launched
            tm, mx, my = info[d["id"]]
            if free_loit:
                n = math.hypot(mx, my) or 1.0
                ux, uy = mx / n, my / n
                best = max(free_loit, key=lambda i: i["x"] * ux + i["y"] * uy)
                free_loit.remove(best)
                retarget[best["id"]] = d["id"]
                role[best["id"]] = "engage"
            else:
                intercept.append(d["id"])
                new_pend.append((d["id"], "engage"))
                launched += 1
            apply_blast(tm, mx, my)

        guard = 0
        while avail() > 0 and guard < 60:
            guard += 1
            if not any(surv[d["id"]] > 0.3 for d in B):
                break
            c = max(B, key=lambda d: gain(*info[d["id"]]))
            if gain(*info[c["id"]]) <= 0.0:
                break
            fire(c)
        guard = 0
        while avail() > 0 and guard < 60:
            guard += 1
            c = max(B, key=lambda d: gain(*info[d["id"]]))
            if gain(*info[c["id"]]) < thr:
                break
            fire(c)
        loiter = free_loit

    # ---------------- loiter steering ----------------
    far = [d for d in tracks.values() if d["r"] > 35.0]
    bear = sorted(math.atan2(d["y"], d["x"]) for d in far)
    can_loiter = False
    if len(bear) >= 3:
        gap = max(bear[k + 1] - bear[k] for k in range(len(bear) - 1))
        gap = max(gap, bear[0] + 2 * math.pi - bear[-1])
        can_loiter = gap < 2.2

    def steer(qx, qy, cur):
        if not far:
            return None
        q = math.hypot(qx, qy)
        if q < 3.0:
            if cur in tracks and tracks[cur]["r"] > 35.0:
                return cur
            return max(far, key=lambda d: d["r"])["id"]
        ux, uy = -qx / q, -qy / q
        best, bs = None, -9.0
        for d in far:
            dx, dy = d["x"] - qx, d["y"] - qy
            n = math.hypot(dx, dy)
            if n < 20.0:
                continue
            sc = (dx * ux + dy * uy) / n
            if sc > bs:
                bs, best = sc, d["id"]
        return best

    for i in loiter:
        tg = steer(i["x"], i["y"], i["target"])
        if tg is not None:
            retarget[i["id"]] = tg

    # ---------------- reserve launches ----------------
    if can_loiter and stock - launched > 0 and launched < LPT:
        near = sum(1 for d in threats if d["r"] <= AR + 60.0 * VMAX and surv[d["id"]] > 0.3)
        need = near - len(loiter)
        n = min(need, stock - launched, LPT - launched)
        for _ in range(max(0, n)):
            tg = steer(0.0, 0.0, None)
            if tg is None:
                break
            intercept.append(tg)
            new_pend.append((tg, "loiter"))
            launched += 1

    S["pend"] = new_pend

    # ---------------- gun ----------------
    gun = None
    if ammo > 0:
        best, bs = None, float("inf")
        for d in threats:
            if d["r"] > GR:
                continue
            sc = urgency(d)
            if surv[d["id"]] <= 0.3:
                sc += 4.0
            if sc < bs:
                bs, best = sc, d["id"]
        gun = best

    return {"intercept": intercept[:LPT], "retarget": retarget, "gun": gun}
