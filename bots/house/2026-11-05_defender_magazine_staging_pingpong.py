"""
Idea: Launch the whole magazine early and keep it circling over the asset by switching each interceptor's target every tick, then release every interceptor in the same tick so the shots are no longer spaced out by the 2-per-tick launch cap.

NAME: magazine_staging_pingpong

The core idea: "staged magazine"
--------------------------------
synchronized_ring wins against the ledger through the launch-rate cap. Thirty
strikers turn inbound on the same tick. A defender that launches only at the
moment of engagement can put out just 2 interceptors per tick, so its shots are
spread over time and space and each blast meets one striker.

This bot splits launching from engaging. As soon as an inbound wave is about
20 ticks away from the planned meeting point, it launches interceptors at 2 per
tick. It does not send them out. Each tick it retargets every launched
interceptor to the track most nearly opposite its current offset from the
asset. Each interceptor then swings back and forth through the origin, within
about 12 units, so it stays parked overhead and loses only a little of its
lifetime. While the strikers are still far out, the bot builds a "staged
magazine" of up to 20 interceptors.

When the ring has shrunk until neighbouring strikers are inside blast radius
(meeting radius about 38, where 30 strikers are about 8 units apart), the bot
commits the whole staged pool in ONE tick. It uses a greedy cover: each
interceptor goes to the striker whose predicted meeting point covers the most
strikers that are still uncovered. A first pass covers every striker once. A
second pass uses the spare interceptors to cover strikers twice. Each blast
covers about 3 strikers, so 10 interceptors cover the ring and the other 10
give a second kill chance. The gun works the uncovered strikers in the meantime.

Why this is not the obvious counter
-----------------------------------
The obvious counters to the source are:
(a) remove the id gate and shoot the loiterers parked at 190, or
(b) schedule convergence blasts by back-timing launches through the launch cap.
The ladder already holds variants of both: hover-ring, deadline packers and
convergence schedulers.
This bot does neither. It never fires at parked tracks. It also does not plan
launches around the launch cap. It removes the launch cap from the
engagement-time problem altogether by using retargeting as a holding pattern.
That turns the interceptor stock into a pool that can be fired in the same
tick. As far as the ladder shows, no other defender uses retarget to hold
interceptors in place rather than to correct their course.
"""
import math

NAME = "magazine_staging_pingpong"
ROLE = "defender"

_S = {}


def reset(seed=None):
    global _S
    _S = {"committed": {}}


reset()


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    isp = float(rules.get("interceptor_speed", 12.0))
    life = int(rules.get("interceptor_lifetime", 90))
    blast = float(rules.get("blast_radius", 10.0))
    gun_range = float(rules.get("gun_range", 100.0))
    lcap = int(rules.get("interceptor_launches_per_tick", 2))
    cover_d = blast * 0.9

    # Collect tracks and work out which ones are inbound threats.
    tinfo = {}
    threats = []
    for t in tracks:
        tid = t.get("id")
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        v = t.get("vel", [0.0, 0.0]) or [0.0, 0.0]
        qx, qy = float(p[0]) - ax, float(p[1]) - ay
        vx, vy = float(v[0]), float(v[1])
        r = math.hypot(qx, qy)
        cls = t.get("cls", "unknown")
        info = {"id": tid, "qx": qx, "qy": qy, "vx": vx, "vy": vy,
                "r": r, "cls": cls}
        tinfo[tid] = info
        if cls == "decoy":
            continue
        vin = -(qx * vx + qy * vy) / r if r > 1e-6 else 0.0
        info["vin"] = vin
        inbound = (vin > 1.5) or (r < 70.0)
        if not inbound:
            continue
        threats.append(info)

    dense = sum(1 for th in threats if th["r"] < 160.0) >= 6
    meetR = 38.0 if dense else 70.0

    for th in threats:
        vin = max(th["vin"], 0.0)
        timp = th["r"] / (isp + vin)
        mx = th["qx"] + th["vx"] * timp
        my = th["qy"] + th["vy"] * timp
        th["mx"], th["my"] = mx, my
        commit_r = meetR * (isp + vin) / isp
        th["eligible"] = (math.hypot(mx, my) <= meetR) or th["r"] <= commit_r \
            or th["r"] <= 45.0
        th["tte"] = (th["r"] - commit_r) / max(vin, 0.5)
        th["cov"] = 0

    tmap = {th["id"]: th for th in threats}

    # Bookkeeping for interceptors already sent at a target.
    present = {}
    for it in inters:
        present[it.get("id")] = it
    committed = S["committed"]
    for iid in list(committed.keys()):
        if iid not in present:
            del committed[iid]

    def meet_of(tid):
        th = tmap.get(tid)
        if th is not None:
            return th["mx"], th["my"]
        ti = tinfo.get(tid)
        if ti is not None:
            return ti["qx"], ti["qy"]
        return None

    def add_cov(mx, my):
        for th in threats:
            if math.hypot(th["mx"] - mx, th["my"] - my) <= cover_d:
                th["cov"] += 1

    # If a committed interceptor lost its target, give it a new one or put it
    # back in the staged pool.
    for iid in list(committed.keys()):
        tid = committed[iid]
        if tid in tinfo:
            continue
        it = present[iid]
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        px, py = float(ip[0]) - ax, float(ip[1]) - ay
        best, bd = None, 1e9
        for th in threats:
            if th["r"] > 120.0:
                continue
            d = math.hypot(th["qx"] - px, th["qy"] - py)
            if d < bd:
                bd, best = d, th
        if best is not None:
            committed[iid] = best["id"]
        else:
            del committed[iid]

    for iid, tid in committed.items():
        m = meet_of(tid)
        if m is not None:
            add_cov(m[0], m[1])

    staged = [it for it in inters if it.get("id") not in committed]

    # Interceptors near the end of their lifetime go to the nearest track so
    # they are not wasted.
    rest = []
    for it in staged:
        age = int(it.get("age", 0) or 0)
        if age >= life - 22:
            ip = it.get("pos", [ax, ay]) or [ax, ay]
            px, py = float(ip[0]) - ax, float(ip[1]) - ay
            pool = threats if threats else [ti for ti in tinfo.values()
                                            if ti["cls"] != "decoy"]
            best, bd = None, 1e9
            for th in pool:
                d = math.hypot(th["qx"] - px, th["qy"] - py)
                if d < bd:
                    bd, best = d, th
            if best is not None:
                committed[it.get("id")] = best["id"]
                if "mx" in best:
                    add_cov(best["mx"], best["my"])
                continue
        rest.append(it)
    staged = rest

    # Commit the staged pool in one tick, using a greedy cover.
    E = [th for th in threats if th["eligible"]]
    reserve = sum(1 for th in threats
                  if not th["eligible"] and th["tte"] < 24 and th["cov"] == 0)

    def nearest_staged(mx, my):
        best, bd = None, 1e9
        for it in staged:
            ip = it.get("pos", [ax, ay]) or [ax, ay]
            d = math.hypot(float(ip[0]) - ax - mx, float(ip[1]) - ay - my)
            if d < bd:
                bd, best = d, it
        return best

    def greedy(level, limit):
        used = 0
        while staged and used < limit:
            best, bg = None, 0
            for c in E:
                g = 0
                for th in E:
                    if th["cov"] < level and math.hypot(
                            th["mx"] - c["mx"], th["my"] - c["my"]) <= cover_d:
                        g += 1
                if g > bg or (g == bg and g > 0 and best is not None
                              and c["r"] < best["r"]):
                    bg, best = g, c
            if best is None or bg == 0:
                break
            it = nearest_staged(best["mx"], best["my"])
            if it is None:
                break
            staged.remove(it)
            committed[it.get("id")] = best["id"]
            add_cov(best["mx"], best["my"])
            used += 1

    if E:
        greedy(1, len(staged))
        spare = len(staged) - reserve
        if spare > 0:
            greedy(2, spare)

    # Retarget committed interceptors, and keep staged ones circling.
    retarget = {}
    for iid, tid in committed.items():
        if tid in tinfo:
            retarget[iid] = tid
    alltr = list(tinfo.values())
    for it in staged:
        if not alltr:
            break
        ip = it.get("pos", [ax, ay]) or [ax, ay]
        px, py = float(ip[0]) - ax, float(ip[1]) - ay
        pr = math.hypot(px, py)
        best, bs = None, -1e9
        for ti in alltr:
            if ti["r"] < 30.0:
                continue
            if pr < 2.0:
                s = ti["r"]
            else:
                s = -(ti["qx"] * px + ti["qy"] * py) / (ti["r"] * pr + 1e-9)
            if s > bs:
                bs, best = s, ti
        if best is not None:
            retarget[it.get("id")] = best["id"]

    # Launch interceptors into the staged pool.
    launch = []
    window = [th for th in threats if th["cov"] == 0
              and (th["eligible"] or th["tte"] < 22)]
    window.sort(key=lambda th: th["r"])
    need = min(len(window), stock) - len(staged)
    n = max(0, min(need, lcap, stock))
    for k in range(n):
        launch.append(window[k % len(window)]["id"])

    # Gun: prefer the closest threat that is not yet covered.
    gun = None
    if ammo > 0:
        best, bs = None, 1e9
        for ti in tinfo.values():
            if ti["cls"] == "decoy" or ti["r"] > gun_range:
                continue
            th = tmap.get(ti["id"])
            covered = th is not None and th["cov"] > 0
            s = ti["r"] + (30.0 if covered else 0.0)
            if s < bs:
                bs, best = s, ti
        if best is not None:
            gun = best["id"]

    return {"intercept": launch, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
