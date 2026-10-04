"""
Idea: Launch-cap laundering. Interceptors are launched early, held over the asset by flipping their target between tracks on opposite sides every tick, and then the whole magazine is released on one tick as a double comb of blasts that meets the contracting ring where its spacing is tighter than the blast radius.

NAME: dither_parked_magazine

Why this is not the obvious counter to synchronized_ring
--------------------------------------------------------
The obvious counter is to close the ledger's id-gate loophole and snipe the
ring while it is parked at radius 190. That trades one interceptor for at most
one striker (about 0.85 kills each). With 20 interceptors against 30 strikers,
about 13 strikers survive and then release together. This bot does the opposite
and leaves the parked ring alone, because the ring's even spacing is what we
want to use.

The other likely counter is a convergence-blast scheduler that times launches
so interceptors meet the shrinking ring near the asset. On a 30-drone ring,
neighbours are closer than the 10-unit blast radius only inside about r=47.
With 2 launches per tick and 4 units of drone travel per tick, only about 12
launches fit in that window, so a launch-timed scheduler gets roughly 12 good
blasts at most.

Here the launch timing and the detonation timing are separate. Interceptors
are launched during the 40 ticks of the ring's run-in and held near the asset.
Each tick, a held interceptor is retargeted to whichever track lies on the far
side of the asset from it. Pure pursuit then moves it back toward the centre,
so it oscillates in place. Retargets are not capped, so all held interceptors
can be fired on the same tick when the ring reaches the right radius.

Targets are chosen greedily over angle-smoothed tracks. The weighting makes
each striker lie inside two independent blasts (survival about 0.0225). The
picks form two interleaved every-third-drone combs that use the whole magazine
of 20. If an interceptor's target dies, it is retargeted to the nearest
survivor. The gun covers whatever is left, giving priority to tracks that no
interceptor is assigned to.

Against attackers that do not form a ring, the same mechanism works as a
per-threat schedule. Launches scale with the number of inbound threats,
interceptors are held until each threat is in range, and held interceptors
that are close to expiring are fired at the nearest threat.
"""
import math

NAME = "dither_parked_magazine"
ROLE = "defender"

_S = {}


def reset(seed=None):
    _S.clear()
    _S["trk"] = {}
    _S["fired"] = set()


reset()


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0) or 0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)) or 25.0)
    ispd = float(rules.get("interceptor_speed", 12.0))
    life = int(rules.get("interceptor_lifetime", 90))
    lcap = int(rules.get("interceptor_launches_per_tick", 2))
    brad = float(rules.get("blast_radius", 10.0))
    grange = float(rules.get("gun_range", 100.0))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    tracks = obs.get("tracks", []) or []
    icps = obs.get("interceptors", []) or []

    # ---- track filtering (bearing EMA, radius alpha filter, inbound speed) ----
    trk = S["trk"]
    T = {}
    for t in tracks:
        tid = t.get("id")
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(x, y)
        if r < 1e-6:
            r = 1e-6
        v = t.get("vel", [0.0, 0.0]) or [0.0, 0.0]
        vx, vy = float(v[0]), float(v[1])
        sr = -(vx * x + vy * y) / r
        e = trk.get(tid)
        if e is None:
            e = {"ux": x / r, "uy": y / r, "r": r, "s": max(0.0, sr)}
        else:
            ux = 0.8 * e["ux"] + 0.2 * x / r
            uy = 0.8 * e["uy"] + 0.2 * y / r
            n = math.hypot(ux, uy) or 1.0
            e["ux"], e["uy"] = ux / n, uy / n
            pred = e["r"] - e["s"]
            e["r"] = pred + 0.4 * (r - pred)
            e["s"] = e["s"] + 0.3 * (sr - e["s"])
        trk[tid] = e
        T[tid] = {"id": tid, "x": x, "y": y, "r": r, "rh": max(0.0, e["r"]),
                  "s": e["s"], "ux": e["ux"], "uy": e["uy"],
                  "cls": t.get("cls", "unknown")}
    for k in list(trk.keys()):
        if k not in T:
            del trk[k]

    threats = [t for t in T.values() if t["cls"] != "decoy"]

    def pp(t, tau):
        rr = max(0.0, t["rh"] - max(0.0, t["s"]) * tau)
        return t["ux"] * rr, t["uy"] * rr

    # ---- interceptors ----
    I = []
    for ic in icps:
        p = ic.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        I.append({"id": ic.get("id"), "target": ic.get("target"),
                  "x": float(p[0]) - ax, "y": float(p[1]) - ay,
                  "age": int(ic.get("age", 0) or 0)})
    alive_ids = set(i["id"] for i in I)
    S["fired"] = set(f for f in S["fired"] if f in alive_ids)
    fired = S["fired"]
    held = [i for i in I if i["id"] not in fired]
    flying = [i for i in I if i["id"] in fired]

    retarget = {}
    cov = {t["id"]: 0 for t in threats}
    nb = 0.9 * brad

    def add_cov(tgt, tau):
        cx, cy = pp(tgt, tau)
        for u in threats:
            ux_, uy_ = pp(u, tau)
            if math.hypot(ux_ - cx, uy_ - cy) <= nb:
                cov[u["id"]] += 1

    # In-flight interceptors: keep them on a live target, and record coverage.
    for i in flying:
        tg = T.get(i["target"])
        if tg is None or tg["cls"] == "decoy":
            best, bd = None, 1e18
            for u in threats:
                d = math.hypot(u["x"] - i["x"], u["y"] - i["y"]) + 15.0 * cov[u["id"]]
                if d < bd:
                    bd, best = d, u
            if best is None:
                continue
            retarget[i["id"]] = best["id"]
            tg = best
        dist = math.hypot(tg["x"] - i["x"], tg["y"] - i["y"])
        add_cov(tg, dist / (ispd + max(0.0, tg["s"])))

    # ---- fire held interceptors ----
    rmeet_goal = arad + 14.0
    ready = []
    for t in threats:
        s = max(0.0, t["s"])
        tau = t["rh"] / (ispd + s)
        rm = t["rh"] - s * tau
        if (s > 1.0 and rm <= rmeet_goal) or t["rh"] < arad + 35.0:
            ready.append((t, tau))

    def fire(i, tgt, tau):
        retarget[i["id"]] = tgt["id"]
        fired.add(i["id"])
        add_cov(tgt, tau)

    pool = list(held)
    while pool and ready:
        best, bg, btau = None, 0.0, 0.0
        for t, tau in ready:
            cx, cy = pp(t, tau)
            g = 0.0
            for u in threats:
                ux_, uy_ = pp(u, tau)
                if math.hypot(ux_ - cx, uy_ - cy) <= nb:
                    g += 0.15 ** cov[u["id"]]
            if g > bg:
                bg, best, btau = g, t, tau
        if best is None or bg < 0.12:
            break
        bi, bd = None, 1e18
        for i in pool:
            d = math.hypot(best["x"] - i["x"], best["y"] - i["y"])
            if d < bd:
                bd, bi = d, i
        pool.remove(bi)
        fire(bi, best, btau)

    # Expiring or drifted held interceptors fire at the nearest threat.
    rest = []
    for i in pool:
        if threats and (i["age"] >= life - 15 or math.hypot(i["x"], i["y"]) > 50.0):
            tg = min(threats, key=lambda u: math.hypot(u["x"] - i["x"], u["y"] - i["y"]))
            fire(i, tg, tg["rh"] / (ispd + max(0.0, tg["s"])))
        else:
            rest.append(i)

    # ---- dither-hold remaining interceptors over the asset ----
    allt = list(T.values())
    for i in rest:
        if not allt:
            break
        m = math.hypot(i["x"], i["y"])
        if m > 3.0:
            dx, dy = -i["x"] / m, -i["y"] / m
        else:
            h = (hash(str(i["id"])) % 628) / 100.0
            dx, dy = math.cos(h), math.sin(h)
        best, bc = None, -2.0
        for u in allt:
            ex, ey = u["x"] - i["x"], u["y"] - i["y"]
            dd = math.hypot(ex, ey)
            if dd < 40.0:
                continue
            c = (ex * dx + ey * dy) / dd
            if c > bc:
                bc, best = c, u
        if best is not None and best["id"] != i["target"]:
            retarget[i["id"]] = best["id"]

    # ---- launches: scale with the number of inbound threats ----
    intercept = []
    inbound = [t for t in threats
               if (t["rh"] < 180.0 and t["s"] > 1.5) or t["rh"] < 110.0]
    if inbound and stock > 0:
        need = int(math.ceil(len(inbound) * 2.0 / 3.0)) + 1
        airborne = len(I)
        n = min(lcap, stock, need - airborne)
        if n > 0:
            tg = min(inbound, key=lambda u: u["rh"])
            for _ in range(n):
                intercept.append(tg["id"])

    # ---- gun: prefer threats no interceptor covers, then the closest ----
    gun = None
    if ammo > 0:
        best, bk = None, None
        for t in threats:
            if min(t["r"], t["rh"]) <= grange:
                k = (1 if cov.get(t["id"], 0) > 0 else 0, t["rh"])
                if bk is None or k < bk:
                    bk, best = k, t
        if best is not None:
            gun = best["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
