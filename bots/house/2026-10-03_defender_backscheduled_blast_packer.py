"""Idea: Plan interceptor launches backwards from the last safe intercept tick, so each blast lands where inbound strikers are packed tightest, and still shoot lone strikers right away so there is time for a second try.

Name: backscheduled_blast_packer

How it works
------------
Every tick the bot keeps a smoothed range and bearing for each track. It then
treats every confirmed striker (and any unknown already inside the id ring) as
a drone flying straight at the asset at striker speed. For each uncovered
threat it asks one question: does waiting make the blast better? It scans
every launch tick from now to the threat's deadline. The deadline is the last
launch that still meets the drone outside the asset with a margin. For each
tick it counts how many uncovered threats would fall inside one blast at the
meeting point.

* If waiting gives no gain (a lone drone), the threat is due now. It is
  engaged on reveal, about 110 u out, which leaves time for retries and gun
  shots if the interceptor misses.
* If waiting gains (drones closing in from many bearings, or a stack), the
  threat's due tick is its deadline.

The bot then builds the schedule backwards, latest tick first, two launches
per tick. Each slot takes the target whose blast covers the most threats not
yet planned. The densest late slots are filled first, and the 2 per tick
launch cap pushes the remaining work as late as it can go. Only the launches
planned for this tick are fired. Stock is held back for the future slots
already planned, so the magazine is not spent on single kills at long range
when triple kills are coming.

In-flight interceptors count as covering their target and its neighbours. An
interceptor whose target died or turned out to be a decoy is retargeted to
the reachable uncovered threat with the best blast count. The gun fires every
tick at the closest uncovered threat, or at a covered threat when it is very
close. It never fires at decoys.

Why it holds up against each attacker
-------------------------------------
* synchronized_ring / phase_locked_ring: These attackers plan around one
  interceptor per striker and a single burst of 2 launches per tick. Strikers
  spread over 30-36 bearings are 20+ u apart at 110 u but under the 10 u blast
  radius inside about 45 u, because the ring shrinks as it converges. The
  backward schedule packs the 20-round magazine into those last ticks, where
  one blast covers 2-3 strikers. Earlier singles are only used for the
  overflow the launch cap cannot fit. The attacker counts on "20 rounds vs 30
  strikers". Packing breaks that count. Loiterers at 190 u stay unknown and
  are never engaged, so the hold costs nothing.
* trickle / staggered_screen_trickle: Arrivals are spread out, so waiting
  never improves a blast. Each striker is shot as soon as it is revealed,
  with time for a retry. Decoys are revealed at 150 u and ignored by both
  interceptors and the gun. Exactly one interceptor is committed per live
  threat, so the magazine is not drained by doubling up. A sideways dodge
  only orphans the shot, and the orphan is then retargeted.
* rush / flanker / multi_axis: Same-tick launches stack up, and corridors
  form trails. The blast count is already high at launch time, so these are
  hit at once, with several drones per round. Two axes landing together are
  covered by the backward schedule, which makes full use of both launch
  slots per tick.
* decoy_screen: Nothing is committed before the 150 u id ring. Once inside
  it, decoys are classified and never draw a shot. A blast that happens to
  include a decoy costs nothing extra.
"""

import math

NAME = "backscheduled_blast_packer"
ROLE = "defender"

_S = {"f": {}}


def reset(seed=None):
    global _S
    _S = {"f": {}}


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _act(obs):
    global _S
    if not isinstance(_S, dict) or "f" not in _S:
        _S = {"f": {}}
    filt = _S["f"]

    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(apos[0]), float(apos[1])
    ar = float(asset.get("radius", rules.get("asset_radius", 25.0)) or 25.0)
    sp = float(rules.get("striker_speed", 4.0) or 4.0)
    isp = float(rules.get("interceptor_speed", 12.0) or 12.0)
    br = float(rules.get("blast_radius", 10.0) or 10.0)
    idr = float(rules.get("id_range", 150.0) or 150.0)
    gr = float(rules.get("gun_range", 100.0) or 100.0)
    cap = int(rules.get("interceptor_launches_per_tick", 2) or 2)
    life = float(rules.get("interceptor_lifetime", 90) or 90)
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    Rc = br * 0.9
    Rc2 = Rc * Rc
    closing = isp + sp

    # ---- track filtering (range alpha-beta, bearing smoothing) ----
    tracks = obs.get("tracks", []) or []
    seen = set()
    threats = {}
    for tr in tracks:
        tid = tr.get("id")
        if tid is None:
            continue
        p = tr.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        dx, dy = float(p[0]) - ax, float(p[1]) - ay
        rho = math.hypot(dx, dy)
        if rho < 1e-6:
            ux_o, uy_o = 1.0, 0.0
        else:
            ux_o, uy_o = dx / rho, dy / rho
        seen.add(tid)
        f = filt.get(tid)
        if f is None:
            v = tr.get("vel", [0.0, 0.0]) or [0.0, 0.0]
            rd = (float(v[0]) * ux_o + float(v[1]) * uy_o)
            f = {"r": rho, "rd": rd, "ux": ux_o, "uy": uy_o, "t": tick}
            filt[tid] = f
        else:
            dt = max(1, tick - f["t"])
            pred = f["r"] + f["rd"] * dt
            res = rho - pred
            f["r"] = pred + 0.4 * res
            f["rd"] = max(-8.0, min(8.0, f["rd"] + 0.1 * res / dt))
            dot = f["ux"] * ux_o + f["uy"] * uy_o
            dot = max(-1.0, min(1.0, dot))
            angd = math.acos(dot)
            a = 0.3
            if angd * max(rho, 1.0) > 18.0:
                a = 0.7
            nx = (1 - a) * f["ux"] + a * ux_o
            ny = (1 - a) * f["uy"] + a * uy_o
            nn = math.hypot(nx, ny)
            if nn > 1e-9:
                f["ux"], f["uy"] = nx / nn, ny / nn
            f["t"] = tick
        cls = tr.get("cls", "unknown")
        rng = f["r"]
        if cls == "striker" or (cls == "unknown" and rho < 0.95 * idr):
            threats[tid] = (max(rng, 0.0), f["ux"], f["uy"], rho)
    for k in list(filt.keys()):
        if k not in seen:
            del filt[k]

    def pos_at(j, t):
        r, ux, uy, _ = threats[j]
        rr = r - sp * t
        if rr < 0.0:
            rr = 0.0
        return ux * rr, uy * rr

    def cluster(i, t, pool):
        px, py = pos_at(i, t)
        out = []
        for j in pool:
            qx, qy = pos_at(j, t)
            ddx, ddy = qx - px, qy - py
            if ddx * ddx + ddy * ddy <= Rc2:
                out.append(j)
        return out

    # ---- in-flight interceptors: coverage and retargeting ----
    covered = set()
    retarget = {}
    orphans = []
    ints = obs.get("interceptors", []) or []
    tids = list(threats.keys())
    for it in ints:
        iid = it.get("id")
        tgt = it.get("target")
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        ix, iy = float(ip[0]) - ax, float(ip[1]) - ay
        age = float(it.get("age", 0) or 0)
        if tgt is not None and tgt in threats:
            qx, qy = pos_at(tgt, 0)
            d = math.hypot(qx - ix, qy - iy)
            tm = d / closing
            for j in cluster(tgt, tm, tids):
                covered.add(j)
        else:
            orphans.append((iid, ix, iy, age))
    for iid, ix, iy, age in orphans:
        if iid is None:
            continue
        rem = max(0.0, (life - age) * isp)
        best = None
        bkey = None
        bcl = None
        for j in tids:
            if threats[j][0] < ar:
                continue
            qx, qy = pos_at(j, 0)
            d = math.hypot(qx - ix, qy - iy)
            if d > rem:
                continue
            tm = d / closing
            unc_pool = [k for k in tids if k not in covered]
            cl = cluster(j, tm, unc_pool)
            key = (1 if j not in covered else 0, len(cl), -d)
            if bkey is None or key > bkey:
                bkey = key
                best = j
                bcl = cluster(j, tm, tids)
        if best is not None:
            retarget[iid] = best
            for k in bcl:
                covered.add(k)

    # ---- backward launch planning ----
    launches = []
    L = (ar + 8.0) * closing / isp
    rmin = (ar + 2.0) * closing / isp
    U = [j for j in tids if j not in covered and threats[j][0] >= rmin]
    if U and stock > 0:
        s = {}
        b = {}
        Hcap = 30
        for i in U:
            si = int(math.floor((threats[i][0] - L) / sp))
            si = max(0, min(Hcap, si))
            s[i] = si
            r_i = threats[i][0]
            g0 = len(cluster(i, r_i / closing, U))
            gmax = g0
            step = 1 if si <= 15 else 2
            tau = 1
            while tau <= si:
                tm = tau + max(r_i - sp * tau, 0.0) / closing
                g = len(cluster(i, tm, U))
                if g > gmax:
                    gmax = g
                tau += step
            if si > 0 and step == 2:
                tm = si + max(r_i - sp * si, 0.0) / closing
                g = len(cluster(i, tm, U))
                if g > gmax:
                    gmax = g
            b[i] = si if gmax > g0 else 0
        H = max(b.values()) if b else 0
        planned = set()
        plan = {}
        for tau in range(H, -1, -1):
            for _k in range(cap):
                pool = [j for j in U if j not in planned]
                elig = [i for i in pool if b[i] >= tau]
                if not elig:
                    break
                bestk = None
                besti = None
                bestcl = None
                for i in elig:
                    r_i = threats[i][0]
                    tm = tau + max(r_i - sp * tau, 0.0) / closing
                    cl = cluster(i, tm, pool)
                    key = (len(cl), -s[i], -r_i)
                    if bestk is None or key > bestk:
                        bestk = key
                        besti = i
                        bestcl = cl
                if besti is None:
                    break
                plan.setdefault(tau, []).append((bestk[0], besti))
                for j in bestcl:
                    planned.add(j)
                planned.add(besti)
        now = sorted(plan.get(0, []), key=lambda x: -x[0])
        future = sum(len(v) for t, v in plan.items() if t > 0)
        allowed = min(len(now), cap, stock, max(0, stock - future))
        launches = [i for _, i in now[:allowed]]

    # ---- gun ----
    gun = None
    if ammo > 0:
        bestk = None
        for j in tids:
            rr = threats[j][3]
            if rr > gr:
                continue
            unc = j not in covered and j not in launches
            if not unc and rr > 60.0:
                continue
            key = (1 if unc else 0, -rr)
            if bestk is None or key > bestk:
                bestk = key
                gun = j

    return {"intercept": launches, "retarget": retarget, "gun": gun}
