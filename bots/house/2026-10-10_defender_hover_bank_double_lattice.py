"""
Idea: Bank the whole magazine as interceptors held near the asset, then commit them as a double-covering lattice of blasts at the radius where the converging ring's neighbours fall inside one blast radius.

Target: 2026-09-29_attacker_synchronized_ring.

Which part of its logic this attacks
------------------------------------
Its whole plan rests on one geometric claim from its docstring: "30 strikers
evenly around the ring (12 degrees apart, about 20+ units apart where the
interceptors meet them), so one blast should kill one striker." That holds
only if the interceptors meet the strikers far out. The ring is perfectly
regular and every striker is released on the same tick, so the ring stays a
circle that shrinks at 4 units per tick. The gap between neighbours is
2*pi*r/30, about 0.209*r. At r of about 41 the gap is about 8.6, which is
less than the 10-unit blast radius. A blast centred on one striker then also
catches both of its neighbours. Twenty blasts placed in the pattern
0,2,3,5,6,8,... cover every striker twice. That needs 20*3 = 60 coverings for
30 strikers, which is exactly the stock we have. Each striker then survives
with probability 0.15^2, about 0.02.

The only obstacle is the cap of 2 launches per tick. All 30 strikers reach the
dense radius on the same tick, so launching on demand is too slow. The fix is
to launch the full magazine as soon as the release is seen, which is about 35
ticks before the dense radius. We then hold each interceptor near the asset by
pointing it, every tick, at a far track on the opposite side of its current
offset. Retargeting has no cap, so all the held interceptors can be committed
together. Each one is committed when its own predicted meeting radius drops to
about 42.

What in the replays shows this is where it breaks
-------------------------------------------------
Its two closest calls, contracting_ring_blaster (26 interceptor kills from 20
interceptors) and loiter_then_collapse (28 kills from 20 interceptors), are
both defenders that wait and hit the shrinking ring late. Both got more kills
per interceptor than one, so the "one blast = one kill" assumption already
fails there. Those defenders still spent part of their stock early or out of
step. We hold everything back and place blasts deliberately so the coverage
overlaps, and the gun cleans up the few that leak.
"""
import math

NAME = "hover_bank_double_lattice"
ROLE = "defender"

R_MEET = 41.0
COMMIT_R = 42.0
PLAN_R = 80.0
ARM_R = 175.0

_S = {}


def reset(seed=None):
    global _S
    _S = {"bear": {}, "committed": {}, "armed": False, "nlaunch": 0}


reset()


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    icps = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    blast = float(rules.get("blast_radius", 10.0))
    pk = float(rules.get("interceptor_kill_prob", 0.85))
    ispd = float(rules.get("interceptor_speed", 12.0))
    sspd = float(rules.get("striker_speed", 4.0))
    gun_r = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))
    total_stock = int(rules.get("interceptor_stock", 20))
    D = blast - 0.5

    # Build the list of threat tracks
    th = []
    for t in tracks:
        if t.get("cls") == "decoy":
            continue
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        dx, dy = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(dx, dy)
        if r < 1e-6:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = dx / r, dy / r
        tid = t.get("id")
        # Smooth the bearing over ticks
        b = S["bear"].get(tid)
        if b is None:
            b = [ux, uy]
        else:
            b = [0.7 * b[0] + 0.3 * ux, 0.7 * b[1] + 0.3 * uy]
        S["bear"][tid] = b
        bn = math.hypot(b[0], b[1]) or 1.0
        v = t.get("vel", [0.0, 0.0]) or [0.0, 0.0]
        vr = float(v[0]) * ux + float(v[1]) * uy
        th.append({"id": tid, "r": r, "u": (b[0] / bn, b[1] / bn),
                   "vr": vr, "pos": (float(p[0]), float(p[1]))})

    # Smooth the radius using the median of tracks at a similar radius
    rs = [x["r"] for x in th]
    for x in th:
        grp = sorted(rr for rr in rs if abs(rr - x["r"]) < 15.0)
        x["rs"] = grp[len(grp) // 2] if grp else x["r"]
    byid = {x["id"]: x for x in th}

    def ppos(x, rad=None):
        rr = x["rs"] if rad is None else rad
        return (ax + x["u"][0] * rr, ay + x["u"][1] * rr)

    intercept = []
    retarget = {}
    gun = None

    # Arm once the attack starts coming in
    if not S["armed"]:
        for x in th:
            if (x["r"] < ARM_R and x["vr"] < -1.0) or x["r"] < 120.0:
                S["armed"] = True
                break

    alive_ids = set()
    for ic in icps:
        alive_ids.add(ic.get("id"))
    for iid in list(S["committed"].keys()):
        if iid not in alive_ids:
            del S["committed"][iid]

    def far_opposite(ix, iy):
        ox, oy = ix - ax, iy - ay
        on = math.hypot(ox, oy)
        best, bv = None, -1e9
        for x in th:
            dd = math.hypot(x["pos"][0] - ix, x["pos"][1] - iy)
            if dd < 60.0:
                continue
            if on > 1.0:
                val = -(x["u"][0] * ox + x["u"][1] * oy) / on
            else:
                val = x["r"]
            val += 0.001 * x["r"]
            if val > bv:
                bv, best = val, x["id"]
        return best

    def nearest_to(ix, iy):
        best, bd = None, 1e18
        for x in th:
            dd = math.hypot(x["pos"][0] - ix, x["pos"][1] - iy)
            if dd < bd:
                bd, best = dd, x["id"]
        return best

    # Committed interceptors: if the target is dead, pick the nearest threat
    pool = []
    for ic in icps:
        iid = ic.get("id")
        p = ic.get("pos", [ax, ay]) or [ax, ay]
        ix, iy = float(p[0]), float(p[1])
        if iid in S["committed"]:
            tg = S["committed"][iid]
            if tg not in byid:
                nt = nearest_to(ix, iy)
                if nt is not None:
                    S["committed"][iid] = nt
                    retarget[iid] = nt
            continue
        age = int(ic.get("age", 0))
        if age >= life - 6 and th:
            nt = nearest_to(ix, iy)
            if nt is not None:
                S["committed"][iid] = nt
                retarget[iid] = nt
            continue
        pool.append((iid, ix, iy))

    # Coverage already provided by committed interceptors
    cover = {x["id"]: 0 for x in th}
    for iid, tg in S["committed"].items():
        x = byid.get(tg)
        if x is None:
            continue
        cx, cy = ppos(x, min(x["rs"], R_MEET))
        for y in th:
            yx, yy = ppos(y, min(y["rs"], R_MEET))
            if math.hypot(yx - cx, yy - cy) <= D:
                cover[y["id"]] += 1

    # Greedy plan of blast centres using the held interceptors
    cand = [x for x in th if x["rs"] <= PLAN_R and (x["vr"] < 0.5 or x["rs"] < 60)]
    plan = []
    if cand and pool:
        cpos = {x["id"]: ppos(x, min(x["rs"], R_MEET)) for x in cand}
        nbr = {}
        for x in cand:
            cx, cy = cpos[x["id"]]
            nbr[x["id"]] = [y["id"] for y in cand
                            if math.hypot(cpos[y["id"]][0] - cx,
                                          cpos[y["id"]][1] - cy) <= D]
        c = dict(cover)
        for _ in range(len(pool)):
            best, bg = None, 0.0
            for x in cand:
                g = 0.0
                for j in nbr[x["id"]]:
                    g += pk * ((1.0 - pk) ** c.get(j, 0))
                g -= 0.0005 * x["rs"]
                if g > bg:
                    bg, best = g, x["id"]
            if best is None or bg < 0.08:
                break
            plan.append(best)
            for j in nbr[best]:
                c[j] = c.get(j, 0) + 1
        plan.sort(key=lambda i: byid[i]["rs"])

    # Commit held interceptors when their meeting radius is right
    used = set()
    for tg in plan:
        x = byid[tg]
        sx, sy = ppos(x)
        best, bm, closest, cd = None, -1e9, None, 1e18
        for (iid, ix, iy) in pool:
            if iid in used:
                continue
            d = math.hypot(sx - ix, sy - iy)
            mr = x["rs"] - sspd * d / (ispd + sspd)
            if mr <= COMMIT_R and mr > bm:
                bm, best = mr, iid
            if d < cd:
                cd, closest = d, iid
        if best is None and x["rs"] < 32.0:
            best = closest
        if best is not None:
            used.add(best)
            S["committed"][best] = tg
            retarget[best] = tg

    # Keep the other held interceptors near the asset
    for (iid, ix, iy) in pool:
        if iid in used:
            continue
        tg = far_opposite(ix, iy)
        if tg is None:
            tg = nearest_to(ix, iy)
        if tg is not None:
            retarget[iid] = tg

    # Launch the bank
    if S["armed"] and th and stock > 0:
        need = min(total_stock, int(math.ceil(len(th) * 2.0 / 3.0)) + 1)
        n = 0
        while n < cap and stock - n > 0 and S["nlaunch"] < need:
            tg = far_opposite(ax, ay)
            if tg is None:
                tg = nearest_to(ax, ay)
            if tg is None:
                break
            intercept.append(tg)
            S["nlaunch"] += 1
            n += 1

    # Gun: shoot the nearest threat in range
    if ammo > 0:
        best, br = None, 1e18
        for x in th:
            if x["r"] <= gun_r and x["r"] < br:
                br, best = x["r"], x["id"]
        gun = best

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
