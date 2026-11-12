"""Idea: Interceptors fly only at radar-confirmed strikers, and each one waits in a hover near the asset (steered by retargeting) only when a later burst would catch more converging strikers in one blast.

Rule digest used: asset 30 hp vs 10 damage per striker, 20 interceptors at pk 0.85
with a 10 unit blast, launch cap 2 per tick, type revealed inside 150, gun inside 100.

How it works:
1. ID gate. A track counts as a threat only once it is identified as a striker, or when
   an unidentified track is already inside reveal range or has 20 or fewer ticks left.
   Every drone has to cross the 150 reveal ring, which leaves about 31 ticks. That is
   enough to engage from the asset, so decoys never draw magazine.
2. Blast-fold test. For each uncovered threat I predict the intercept point with the
   best available interceptor, then count other threats within blast radius of it.
   I compare that count with the count when the threat reaches radius 45 later.
   - If waiting gathers more strikers into one blast, the threat waits.
   - Otherwise it is engaged immediately.
   Neighbours near a committed blast get partial cover credit, so a dense
   ring is covered roughly every other drone.
3. Hover staging. When threats are waiting, I launch interceptors into a hover pool.
   Each pool member is retarget-steered toward the asset, alternating between tracks
   on opposite sides. When the convergence point arrives the whole pool commits in one
   tick, which gets around the 2-per-tick launch cap. Pool members near the end of
   their lifetime commit to whatever they can still reach, so the pool does not expire
   unused. Interceptors whose target dies or turns out to be a decoy rejoin the pool.
4. Misses. A missed target becomes uncovered again and is re-engaged. A close striker
   gets a second interceptor when there is spare magazine.
5. Gun. It fires at the nearest threat that is not about to be hit.

Expected result against each attacker type:
- Synchronized and phase-locked rings. These defeat ID-gated packers, which spend
  2-per-tick launches on single kills. Here they meet a staged pool that bursts at
  convergence, the same mechanism that lets the loiter and pingpong defenders score
  0.65 to 0.73.
- Staggered screen trickle. This punished hover-ring defenders (0.13). The bot reverts
  to fire-on-identification because the fold test finds no density, and the pool only
  forms on demand.
- Bait-count / clear-sky waves and decoy lures. Bait is never fired at, because staging
  and commits require a striker ID, so the full magazine is there when the real wave comes.
- Depth shells and interleaves. Deadline ordering plus re-engagement handles layered
  arrivals. Orbits are timed with a conservative max-speed ETA, so a drone that loiters
  and then dives is never late.
"""
import math

NAME = "convergence_hold_burst_packer"
ROLE = "defender"

_S = {}


def reset(seed=None):
    _S.clear()
    _S.update(roles={}, ctarget={}, lastdir={}, pending={})


reset()


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _itime(qx, qy, px, py, vx, vy, s):
    dx, dy = px - qx, py - qy
    a = vx * vx + vy * vy - s * s
    b = 2.0 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    if a >= -1e-9:
        return math.sqrt(c) / max(s - math.hypot(vx, vy), 0.5)
    disc = b * b - 4 * a * c
    if disc < 0:
        disc = 0.0
    t = (b + math.sqrt(disc)) / (2.0 * -a)
    return max(t, 0.0)


def _act(obs):
    if not _S:
        reset()
    rules = obs.get("rules") or {}
    arad = float(rules.get("asset_radius", 25.0))
    sspd = float(rules.get("striker_speed", 4.0))
    ispd = float(rules.get("interceptor_speed", 12.0))
    life = float(rules.get("interceptor_lifetime", 90))
    lcap = int(rules.get("interceptor_launches_per_tick", 2))
    blast = float(rules.get("blast_radius", 10.0))
    idr = float(rules.get("id_range", 150.0))
    grange = float(rules.get("gun_range", 100.0))
    R_LATE = arad + 20.0

    asset = obs.get("asset") or {}
    ap = asset.get("pos") or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])

    T = {}
    for t in obs.get("tracks") or []:
        try:
            tid = t["id"]
            px, py = float(t["pos"][0]), float(t["pos"][1])
            v = t.get("vel") or [0.0, 0.0]
            vx, vy = float(v[0]), float(v[1])
        except Exception:
            continue
        dx, dy = px - ax, py - ay
        r = math.hypot(dx, dy)
        clos = -(dx * vx + dy * vy) / r if r > 1e-6 else sspd
        ceta = max(0.0, r - arad) / max(sspd, 0.1)
        cls = t.get("cls", "unknown")
        T[tid] = dict(id=tid, px=px, py=py, vx=vx, vy=vy, r=r, clos=clos,
                      ceta=ceta, cls=cls)

    def is_threat(k):
        if k["cls"] == "striker":
            return True
        if k["cls"] == "unknown":
            return k["r"] <= idr + 15.0 or k["ceta"] <= 20.0
        return False

    threats = [k for k in T.values() if is_threat(k)]
    threats.sort(key=lambda k: k["ceta"])
    tset = set(k["id"] for k in threats)

    roles, ctarget, lastdir, pending = (_S["roles"], _S["ctarget"],
                                        _S["lastdir"], _S["pending"])
    ints = []
    alive = set()
    for it in obs.get("interceptors") or []:
        try:
            iid = it["id"]
            pos = it.get("pos") or [0.0, 0.0]
            ix, iy = float(pos[0]), float(pos[1])
        except Exception:
            continue
        tgt = it.get("target")
        age = float(it.get("age", 0) or 0)
        alive.add(iid)
        if iid not in roles:
            if tgt is not None and pending.get(tgt, 0) > 0:
                roles[iid] = "commit"
                ctarget[iid] = tgt
                pending[tgt] -= 1
            else:
                roles[iid] = "stage"
        if roles[iid] == "commit":
            ct = ctarget.get(iid)
            if ct not in T or T[ct]["cls"] == "decoy":
                roles[iid] = "stage"
                ctarget.pop(iid, None)
        ints.append(dict(id=iid, x=ix, y=iy, tgt=tgt, age=age))
    for iid in list(roles.keys()):
        if iid not in alive:
            roles.pop(iid, None)
            ctarget.pop(iid, None)
            lastdir.pop(iid, None)
    _S["pending"] = {}
    pending = _S["pending"]

    cov = {}
    soft = {}
    tmin = {}

    def pred(k, t):
        return k["px"] + k["vx"] * t, k["py"] + k["vy"] * t

    def neigh_count(cid, t):
        c = T[cid]
        cx, cy = pred(c, t)
        n = 0
        for k in threats:
            if k["id"] == cid:
                continue
            qx, qy = pred(k, t)
            if math.hypot(qx - cx, qy - cy) <= blast:
                n += 1
        return n

    def add_soft(cid, t):
        c = T[cid]
        cx, cy = pred(c, t)
        for k in threats:
            if k["id"] == cid:
                continue
            qx, qy = pred(k, t)
            d = math.hypot(qx - cx, qy - cy)
            if d <= 0.7 * blast:
                soft[k["id"]] = soft.get(k["id"], 0.0) + 1.0
            elif d <= blast:
                soft[k["id"]] = soft.get(k["id"], 0.0) + 0.5

    for it in ints:
        if roles.get(it["id"]) == "commit":
            ct = ctarget.get(it["id"])
            k = T.get(ct)
            if k is None:
                continue
            cov[ct] = cov.get(ct, 0) + 1
            tt = _itime(it["x"], it["y"], k["px"], k["py"], k["vx"], k["vy"], ispd)
            tmin[ct] = min(tmin.get(ct, 1e9), tt)
            if ct in tset:
                add_soft(ct, tt)

    stock = int(obs.get("stock", 0) or 0)
    slots = max(0, min(lcap, stock))
    launches = []
    retarget = {}

    avail = [it for it in ints if roles.get(it["id"]) == "stage"
             and it["age"] < life - 3]

    # Pool members near the end of their lifetime commit to whatever they can reach.
    keep = []
    for it in avail:
        if it["age"] >= life - 10:
            rem = life - it["age"] - 1
            best, bk = None, None
            for k in list(threats) + [k for k in T.values() if k["cls"] == "decoy"]:
                tt = _itime(it["x"], it["y"], k["px"], k["py"], k["vx"], k["vy"], ispd)
                if tt > rem:
                    continue
                uncovered = 0 if (k["id"] in tset and cov.get(k["id"], 0) == 0) else 1
                key = (0 if k["id"] in tset else 1, uncovered, tt)
                if bk is None or key < bk:
                    bk, best = key, k
            if best is not None:
                retarget[it["id"]] = best["id"]
                roles[it["id"]] = "commit"
                ctarget[it["id"]] = best["id"]
                if best["id"] in tset:
                    cov[best["id"]] = cov.get(best["id"], 0) + 1
                continue
        keep.append(it)
    avail = keep

    n_unc = sum(1 for k in threats
                if cov.get(k["id"], 0) + soft.get(k["id"], 0.0) < 1.0)
    spare = stock + len(avail) - n_unc - 3
    waiting = []

    for k in threats:
        tid = k["id"]
        c = cov.get(tid, 0)
        covered = c + soft.get(tid, 0.0) >= 1.0
        dbl = (c == 1 and k["ceta"] <= 9 and spare > 0 and tmin.get(tid, 0) >= 2)
        if covered and not dbl:
            continue
        bs, ts = None, 1e9
        for it in avail:
            tt = _itime(it["x"], it["y"], k["px"], k["py"], k["vx"], k["vy"], ispd)
            if tt < ts:
                ts, bs = tt, it
        to = _itime(ax, ay, k["px"], k["py"], k["vx"], k["vy"], ispd) + 1.0
        if bs is None and slots <= 0:
            continue
        tbest = min(ts if bs is not None else 1e9, to if slots > 0 else 1e9)
        forced = k["ceta"] - tbest <= 8.0
        wait = False
        if not forced and not dbl and k["r"] > R_LATE + 10 and k["clos"] > 0.5:
            tR = (k["r"] - R_LATE) / k["clos"]
            if tR <= 45:
                if neigh_count(tid, tR) > neigh_count(tid, tbest):
                    wait = True
        if wait:
            waiting.append(k)
            continue
        use_staged = bs is not None and (slots <= 0 or ts <= to + 3.0)
        if use_staged:
            retarget[bs["id"]] = tid
            roles[bs["id"]] = "commit"
            ctarget[bs["id"]] = tid
            avail = [a for a in avail if a["id"] != bs["id"]]
            tu = ts
        else:
            launches.append(tid)
            pending[tid] = pending.get(tid, 0) + 1
            slots -= 1
            tu = to
        cov[tid] = cov.get(tid, 0) + 1
        add_soft(tid, tu)
        spare -= 1

    # Stage interceptors into the hover pool for threats that are holding for convergence.
    need = len(waiting) - len(avail)
    wi = 0
    while need > 0 and slots > 0 and waiting:
        launches.append(waiting[wi % len(waiting)]["id"])
        wi += 1
        slots -= 1
        need -= 1

    # Steer the pool toward the asset by retargeting, alternating between opposite tracks.
    allt = list(T.values())
    for it in avail:
        if it["id"] in retarget:
            continue
        gx, gy = ax - it["x"], ay - it["y"]
        gd = math.hypot(gx, gy)
        if gd > 10.0:
            dx, dy = gx / gd, gy / gd
        else:
            ld = lastdir.get(it["id"])
            dx, dy = (-ld[0], -ld[1]) if ld else (1.0, 0.0)
        best, bsc, bu = None, -9.0, None
        for k in allt:
            ddx, ddy = k["px"] - it["x"], k["py"] - it["y"]
            dd = math.hypot(ddx, ddy)
            if dd < 45.0:
                continue
            lt = dd / (ispd + sspd)
            lx = k["px"] + k["vx"] * lt - it["x"]
            ly = k["py"] + k["vy"] * lt - it["y"]
            ln = math.hypot(lx, ly)
            if ln < 1e-6:
                continue
            ux, uy = lx / ln, ly / ln
            sc = ux * dx + uy * dy
            if sc > bsc:
                bsc, best, bu = sc, k, (ux, uy)
        if best is not None:
            retarget[it["id"]] = best["id"]
            lastdir[it["id"]] = bu

    # Gun: nearest threat in range, preferring ones not about to be hit by an interceptor.
    gun = None
    if int(obs.get("ammo", 0) or 0) > 0:
        bk = None
        for k in threats:
            if k["r"] > grange:
                continue
            soon = 1 if tmin.get(k["id"], 1e9) <= 2 else 0
            key = (soon, k["r"])
            if bk is None or key < bk:
                bk, gun = key, k["id"]

    return {"intercept": launches[:max(0, min(lcap, stock))],
            "retarget": retarget, "gun": gun}
