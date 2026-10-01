"""
Idea: Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.

Which part of synchronized_ring's logic this attacks
----------------------------------------------------
synchronized_ring places all 30 strikers on evenly spaced slots on a ring of
radius 190, 12 degrees apart. It releases them all on the same tick, and every
striker flies straight at the asset. Spreading them out was meant to stop one
10-unit blast from killing several strikers. That only holds at large radius.

The release is synchronized and every path is radial, so the strikers stay a
ring that shrinks. The spacing between neighbours is 2*pi*r/30, about 0.21*r.
It falls below the blast radius at about r = 48. The tighter the ring
converges, the better each blast pays off.

What in the replays shows it breaks there
-----------------------------------------
* Every defender uses its stock early and almost entirely on single kills. For
  example, nearest_first, annealed_assignment_eager and the
  reveal_timed_prelaunch replays show 16 to 18 interceptor kills from 20
  launches, against 30 strikers. Stock reaches 0 and about 10 survivors arrive
  within 1 to 3 ticks of each other, which overloads the one-target gun.
* In the rush replays the ledger killed 30 strikers with 20 interceptors,
  because the strikers were clustered. synchronized_ring builds that same
  cluster near the asset, just late. This bot waits for it.
* The closest call (identify_then_engage, asset hp 10) came from engaging
  later than the others. This bot pushes that idea to its geometric limit.

How it works
------------
* Each track gets an alpha-beta filter on range and closing speed, plus a
  smoothed bearing. This suppresses the track noise so the geometry can be
  predicted along radial paths.
* Tracks that are loitering (not closing) are ignored. This bot fires nothing
  while the ring is holding.
* Each tick the bot plans "blast groups". It predicts positions at the moment
  the most urgent uncovered track reaches the deadline radius (about 40). It
  then picks the aim track whose predicted neighbourhood within 0.9 * blast
  radius covers the most uncovered strikers.
* Earliest-deadline-first scheduling under the 2-per-tick launch cap decides
  how many launches must go this tick. Launches happen as late as feasible, so
  intercepts land where the ring is densest.
* Spare stock is spent on a second, later coverage layer (radius about 31).
  Orphaned interceptors are retargeted. The gun shoots the threat closest to
  impact, preferring tracks no interceptor covers.
* Late engagement happens inside id range, so decoys are usually already
  revealed and ignored.
"""
import math

NAME = "convergence_blast_scheduler"
ROLE = "defender"

_S = {}


def reset(seed=None):
    global _S
    _S = {"F": {}, "pending": []}


reset()


def _d2(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    ar = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    V = float(rules.get("interceptor_speed", 12.0))
    spd = float(rules.get("striker_speed", 4.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    blast = float(rules.get("blast_radius", 10.0))
    gun_range = float(rules.get("gun_range", 100.0))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    CR = 0.9 * blast
    CR2 = CR * CR
    RD1 = ar + 15.0
    RD2 = ar + 6.0

    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    F = S["F"]

    # ---- filter update
    seen = set()
    meas = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        dx, dy = float(p[0]) - ax, float(p[1]) - ay
        R = math.hypot(dx, dy)
        if R < 1e-6:
            R = 1e-6
        mux, muy = dx / R, dy / R
        v = t.get("vel", [0.0, 0.0]) or [0.0, 0.0]
        try:
            vrad = -(dx * float(v[0]) + dy * float(v[1])) / R
        except Exception:
            vrad = 0.0
        f = F.get(tid)
        if f is None:
            f = {"r": R, "vr": vrad, "ux": mux, "uy": muy, "t": tick}
            F[tid] = f
        else:
            dt = max(1, tick - f["t"])
            rp = f["r"] - f["vr"] * dt
            res = R - rp
            f["r"] = rp + 0.5 * res
            f["vr"] = f["vr"] - 0.2 * res / dt
            f["vr"] = 0.7 * f["vr"] + 0.3 * vrad
            ux = f["ux"] + 0.4 * (mux - f["ux"])
            uy = f["uy"] + 0.4 * (muy - f["uy"])
            n = math.hypot(ux, uy)
            if n < 1e-6:
                ux, uy = mux, muy
            else:
                ux, uy = ux / n, uy / n
            f["ux"], f["uy"] = ux, uy
            f["t"] = tick
        f["cls"] = t.get("cls", "unknown")
        seen.add(tid)
        meas[tid] = R
    for k in list(F.keys()):
        if k not in seen and tick - F[k]["t"] > 5:
            del F[k]

    # ---- threats
    E = {}
    for tid in seen:
        f = F[tid]
        if f.get("cls") == "decoy":
            continue
        vr = f["vr"]
        r = max(f["r"], 0.0)
        closing = False
        if vr > 1.0:
            closing = True
            vr = min(max(vr, 0.75 * spd), 1.5 * spd)
        elif r < 100.0:
            closing = True
            vr = max(vr, 0.75 * spd)
        E[tid] = {"r": r, "vr": vr, "ux": f["ux"], "uy": f["uy"],
                  "closing": closing, "R": meas.get(tid, r),
                  "cls": f.get("cls")}
    C = sorted([k for k in E if E[k]["closing"]], key=lambda k: str(k))

    def pred(e, t):
        rr = max(e["r"] - e["vr"] * t, 0.0)
        return (e["ux"] * rr, e["uy"] * rr)

    def slack(e, Rd):
        return (e["r"] - Rd * (V + e["vr"]) / V) / e["vr"] - 1.0

    # ---- retarget orphaned interceptors
    retarget = {}
    tgt_count = {}
    for it in inters:
        tg = it.get("target")
        if tg in E:
            tgt_count[tg] = tgt_count.get(tg, 0) + 1
    live_inters = []
    for it in inters:
        iid = it.get("id")
        tg = it.get("target")
        if tg not in E or not E[tg]["closing"]:
            if C:
                best = min(C, key=lambda j: (tgt_count.get(j, 0),
                                             slack(E[j], RD2), str(j)))
                retarget[iid] = best
                tgt_count[best] = tgt_count.get(best, 0) + 1
                tg = best
            else:
                continue
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        live_inters.append(((float(ip[0]) - ax, float(ip[1]) - ay), tg))

    # pending launches from last tick not yet visible
    present_targets = set(t for _, t in live_inters)
    newpend = []
    for (tg, lt) in S["pending"]:
        if tick - lt <= 1 and tg in E and tg not in present_targets:
            live_inters.append(((0.0, 0.0), tg))
            newpend.append((tg, lt))
    S["pending"] = newpend

    # ---- coverage from in-flight interceptors
    cov = {j: 0 for j in C}
    for (ip, tg) in live_inters:
        e = E.get(tg)
        if e is None or not e["closing"]:
            continue
        tp = (e["ux"] * e["r"], e["uy"] * e["r"])
        d = math.sqrt(_d2(ip, tp))
        th = d / (V + max(e["vr"], 0.0))
        pt = pred(e, th)
        for j in C:
            if _d2(pred(E[j], th), pt) <= CR2:
                cov[j] += 1

    def plan(needset, Rd, maxg):
        groups = []
        needy = set(needset)
        slk = {j: slack(E[j], Rd) for j in C}
        while needy and len(groups) < maxg:
            i = min(needy, key=lambda j: (slk[j], str(j)))
            ei = E[i]
            ti = max((ei["r"] - Rd) / ei["vr"], 0.0)
            P = {j: pred(E[j], ti) for j in C}
            pi = P[i]
            best, bestcov, bestsc = i, [i], -1.0
            for c in C:
                pc = P[c]
                if _d2(pc, pi) > CR2:
                    continue
                cv = [j for j in needy if _d2(P[j], pc) <= CR2]
                sc = len(cv) + (0.5 if c == i else 0.0)
                if sc > bestsc:
                    bestsc, best, bestcov = sc, c, cv
            if i not in bestcov:
                bestcov = list(bestcov) + [i]
            groups.append((slk[i], best, bestcov))
            needy -= set(bestcov)
        groups.sort(key=lambda g: (g[0], str(g[1])))
        return groups

    def feasible(tid):
        e = E[tid]
        return e["r"] * V / (V + e["vr"]) >= ar

    launch = []
    if stock > 0 and C and cap > 0:
        need1 = [j for j in C if cov[j] == 0]
        prim = plan(need1, RD1, stock)
        n_must = 0
        for idx, g in enumerate(prim):
            k = max(0, int(math.floor(g[0])))
            n_must = max(n_must, (idx + 1) - cap * k)
        n_must = min(n_must, cap, stock)
        used = 0
        for g in prim[:n_must]:
            used += 1
            if feasible(g[1]):
                launch.append(g[1])
        # secondary layer with spare capacity
        cov2 = dict(cov)
        for g in prim:
            for j in g[2]:
                cov2[j] = cov2.get(j, 0) + 1
        avail = stock - len(launch) - (len(prim) - used)
        if avail > 0 and len(launch) < cap:
            need2 = [j for j in C if cov2.get(j, 0) < 2]
            sec = plan(need2, RD2, avail)
            for g in sec:
                if len(launch) >= cap or len(launch) >= stock:
                    break
                if g[0] <= 0.0 and feasible(g[1]):
                    launch.append(g[1])
    for tg in launch:
        S["pending"].append((tg, tick))

    # ---- gun
    gun = None
    if ammo > 0:
        best, bk = None, 1e18
        for tid, e in E.items():
            if e["R"] > gun_range:
                continue
            T = (e["r"] - ar) / max(e["vr"], 1.0)
            k = T + (4.0 if cov.get(tid, 0) > 0 else 0.0)
            if e["cls"] == "striker":
                k -= 0.5
            if k < bk or (k == bk and str(tid) < str(best)):
                bk, best = k, tid
        gun = best

    return {"intercept": launch, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
