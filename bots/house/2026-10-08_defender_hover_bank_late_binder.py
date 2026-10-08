"""
Idea: Bank interceptor flight time by hovering the whole magazine over the asset with alternating retargets, then bind every interceptor to a cluster at the last safe tick so overlapping blasts cover each converging striker twice.

NAME: hover_bank_late_binder

Why this is not the obvious counter
-----------------------------------
The obvious answer to synchronized_ring is a convergence scheduler. It works
out when the shrinking ring will be dense and times its launches so the
interceptors arrive then. That approach has a weak point: only 2 launches are
allowed per tick, so 20 interceptors take 10 ticks to get out. They then
arrive spread over about 40 units of the strikers' approach, and only the last
few blasts land where the ring is tight.

This bot does not plan its launches around arrival at all.
* As soon as an approach is detected, it pushes the whole magazine into the
  air.
* Each untasked interceptor "hovers" within about 12 units of the asset. Every
  tick it is retargeted onto a far track that lies on the opposite side of the
  asset from itself, so it oscillates instead of leaving.
* The launch-rate cap is paid early, while the ring is still far away.
* All hovering interceptors are released in a single tick, at the moment the
  predicted meet radius drops to about 32. There the strikers are about 6-7
  units apart, so one 10 m blast covers 3 of them.
* A greedy coverage pass picks the anchors so that every due striker sits in 2
  blasts. That gives a per-striker kill chance of about 0.98 instead of 0.85.

The gun fires at whichever in-range track is least covered.
"""
import math

NAME = "hover_bank_late_binder"
ROLE = "defender"

_S = {}


def reset(seed=None):
    global _S
    _S = {"hist": {}, "strike": {}, "pending": {}, "seen_i": set()}


reset()


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    i_speed = float(rules.get("interceptor_speed", 12.0))
    blast = float(rules.get("blast_radius", 10.0))
    gun_range = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []

    cover_d = blast * 0.9
    meet_target = arad + 7.0

    # ---- track bookkeeping
    T = {}
    hist = S["hist"]
    for t in tracks:
        tid = t.get("id")
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(x, y)
        h = hist.setdefault(tid, [])
        h.append(r)
        if len(h) > 7:
            del h[0]
        vh = None
        if len(h) >= 2:
            vh = (h[0] - h[-1]) / (len(h) - 1)
        vo = None
        v = t.get("vel")
        if v and r > 1e-6:
            try:
                vo = -(float(v[0]) * x + float(v[1]) * y) / r
            except Exception:
                vo = None
        if vh is not None and vo is not None:
            vr = 0.5 * vh + 0.5 * vo
        elif vh is not None:
            vr = vh
        elif vo is not None:
            vr = vo
        else:
            vr = 0.0
        T[tid] = {"x": x, "y": y, "r": r, "v": vr, "cls": t.get("cls", "unknown")}
    for k in list(hist.keys()):
        if k not in T:
            del hist[k]

    threats = [k for k in T if T[k]["cls"] != "decoy"]

    def dist(a, b):
        return math.hypot(T[a]["x"] - T[b]["x"], T[a]["y"] - T[b]["y"])

    # ---- interceptor bookkeeping
    strike = S["strike"]
    pend = S["pending"]
    I = {}
    for it in ints:
        iid = it.get("id")
        p = it.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        I[iid] = {"x": float(p[0]) - ax, "y": float(p[1]) - ay,
                  "age": int(it.get("age", 0) or 0), "target": it.get("target")}
        if iid not in S["seen_i"]:
            S["seen_i"].add(iid)
            tg = it.get("target")
            if pend.get(tg, 0) > 0:
                pend[tg] -= 1
                strike[iid] = tg
    for k in list(strike.keys()):
        if k not in I:
            del strike[k]
    S["pending"] = {}
    pend = S["pending"]

    retarget = {}
    intercept = []
    launches_left = min(cap, stock)

    # strike interceptors whose anchor died -> nearest threat
    for iid, anc in list(strike.items()):
        if anc not in T or anc not in threats:
            if threats:
                ix, iy = I[iid]["x"], I[iid]["y"]
                best = min(threats, key=lambda k: math.hypot(T[k]["x"] - ix, T[k]["y"] - iy))
                strike[iid] = best
                retarget[iid] = best
            continue
        if I[iid]["target"] != anc:
            retarget[iid] = anc

    cov = {k: 0 for k in threats}
    anchor_use = {}
    for iid, anc in strike.items():
        if anc not in T:
            continue
        anchor_use[anc] = anchor_use.get(anc, 0) + 1
        for k in threats:
            if dist(anc, k) <= cover_d:
                cov[k] += 1

    # ---- due set
    due = []
    for k in threats:
        r, v = T[k]["r"], T[k]["v"]
        is_due = False
        if v > 1.0:
            if i_speed * r / (i_speed + v) <= meet_target:
                is_due = True
            if (r - arad) / v <= 5.0:
                is_due = True
        if r <= meet_target + 12.0:
            is_due = True
        if is_due:
            due.append(k)

    hover = [i for i in I if i not in strike]
    deficit = {k: max(0, 2 - cov[k]) for k in due}

    # ---- greedy late binding
    guard = 0
    while sum(deficit.values()) > 0 and (hover or launches_left > 0) and guard < 60:
        guard += 1
        best, bs = None, 0.0
        for a in threats:
            if T[a]["r"] > 120:
                continue
            s = 0.0
            for d, df in deficit.items():
                if df > 0 and dist(a, d) <= cover_d:
                    s += df
            s -= 0.3 * anchor_use.get(a, 0)
            if s > bs:
                bs, best = s, a
        if best is None or bs <= 0:
            break
        if hover:
            hx, hy = T[best]["x"], T[best]["y"]
            hi = min(hover, key=lambda i: math.hypot(I[i]["x"] - hx, I[i]["y"] - hy))
            hover.remove(hi)
            strike[hi] = best
            retarget[hi] = best
        else:
            intercept.append(best)
            pend[best] = pend.get(best, 0) + 1
            launches_left -= 1
        anchor_use[best] = anchor_use.get(best, 0) + 1
        for d in deficit:
            if dist(best, d) <= cover_d:
                deficit[d] = max(0, deficit[d] - 1)
                cov[d] = cov.get(d, 0) + 1

    # ---- hover pool sizing / launches
    soon = 0
    for k in threats:
        r, v = T[k]["r"], T[k]["v"]
        if r < 120 or (v > 1.5 and (r - 40.0) / v <= 45.0):
            soon += 1
    air = len(I) + len(intercept)
    desired = 0
    if soon > 0:
        desired = min(air + stock, int(math.ceil(soon * 2.0 / 3.0)) + 1)
    far = [k for k in T if T[k]["r"] > 60]
    while launches_left > 0 and air < desired and far:
        tgt = max(far, key=lambda k: T[k]["r"])
        intercept.append(tgt)
        launches_left -= 1
        air += 1

    # ---- hover control
    for iid in hover:
        it = I[iid]
        if it["age"] >= life - 6:
            if threats:
                best = min(threats, key=lambda k: T[k]["r"])
                strike[iid] = best
                retarget[iid] = best
            continue
        ix, iy = it["x"], it["y"]
        ir = math.hypot(ix, iy)
        cands = [k for k in T if T[k]["r"] > 60 and
                 math.hypot(T[k]["x"] - ix, T[k]["y"] - iy) > 30]
        if not cands:
            if threats:
                best = min(threats, key=lambda k: T[k]["r"])
                strike[iid] = best
                retarget[iid] = best
            continue
        if ir < 3.0:
            tgt = max(cands, key=lambda k: T[k]["r"])
        else:
            ux, uy = -ix / ir, -iy / ir

            def score(k):
                dx, dy = T[k]["x"] - ix, T[k]["y"] - iy
                dd = math.hypot(dx, dy) or 1.0
                return (dx * ux + dy * uy) / dd
            tgt = max(cands, key=score)
        retarget[iid] = tgt

    # ---- gun
    gun = None
    if ammo > 0:
        inr = [k for k in threats if T[k]["r"] <= gun_range]
        if inr:
            gun = min(inr, key=lambda k: (1 if cov.get(k, 0) >= 2 else 0, T[k]["r"]))

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
