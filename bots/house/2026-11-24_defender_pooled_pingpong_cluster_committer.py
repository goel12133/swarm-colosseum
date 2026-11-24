"""Idea: Park the interceptor magazine at the asset with ping-pong retargeting, then commit it in blast-radius clusters once a wave has converged.

How it works: interceptors launch only for identified strikers, or for unknown tracks that are
inside id range, approaching or close. Until a threat reaches the commit band, each interceptor
in the pool is retargeted every tick to whichever track pulls it back toward the origin. That
keeps the magazine hovering at the asset with full speed and fuel in hand.

Commit timing: a threat enters the commit band when an interceptor leaving from the centre
would meet it at the planned kill radius. For a dense, synchronized wave that radius is about
40 units, where ring spacing is under one blast radius. For a lone drone it is about 60 units,
which leaves time for a second shot.

Assignment: the planner is greedy. It aims each blast at the drone with the most uncovered
neighbours inside the blast radius. Drones that a blast should already cover get no second
interceptor, and any drone that survives a miss is committed again from the pool next tick.
The gun shoots the nearest threat inside gun range that no interceptor is committed to.

Why it holds up across the field:
- Synchronized and phase-locked rings: no launch-rate cap matters, because the whole magazine
  is already airborne at the centre when the ring arrives. Bunching lets single blasts take
  several strikers.
- Decoy drains, bait-count attacks and clear-sky waves: nothing launches at an unidentified
  track beyond id range, and identified decoys are never engaged. Bait cannot empty the
  magazine.
- Staggered trickles and depth shells: commits happen per threat as each one enters the band.
  Misses are retried, and the gun covers leakers, so there is no single all-in timing to
  exploit.
- Orbit and shadow attacks: drones that loiter out of reach do not trigger launches unless they
  are approaching. Any interceptor about to expire is spent on the nearest threat instead of
  being wasted.
"""
import math

NAME = "pooled_pingpong_cluster_committer"
ROLE = "defender"

_S = {}


def reset(seed=None):
    _S.clear()


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _act(obs):
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(apos[0]), float(apos[1])
    aradius = float(rules.get("asset_radius", asset.get("radius", 25.0)))
    id_range = float(rules.get("id_range", 150.0))
    gun_range = float(rules.get("gun_range", 100.0))
    blast = float(rules.get("blast_radius", 10.0))
    life = int(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    commit = _S.setdefault("commit", {})
    prev = _S.setdefault("prev", {})
    pending = _S.setdefault("pending", set())
    seen = _S.setdefault("seen", set())
    rh = _S.setdefault("rh", {})

    # ---- tracks ----
    tracks = obs.get("tracks", []) or []
    T = {}
    for t in tracks:
        try:
            tid = t["id"]
            x = float(t["pos"][0]) - ax
            y = float(t["pos"][1]) - ay
            r = math.hypot(x, y)
            T[tid] = {"id": tid, "x": x, "y": y, "r": r,
                      "cls": t.get("cls", "unknown")}
        except Exception:
            continue

    # range history for approach detection
    for tid, t in T.items():
        h = rh.setdefault(tid, [])
        h.append(t["r"])
        if len(h) > 8:
            del h[0]
    for tid in list(rh.keys()):
        if tid not in T:
            del rh[tid]

    def approaching(t):
        h = rh.get(t["id"], [])
        if t["r"] < 100.0:
            return True
        return len(h) >= 5 and (h[0] - h[-1]) > 8.0

    threats = {}
    for tid, t in T.items():
        c = t["cls"]
        if c == "striker":
            threats[tid] = t
        elif c == "unknown" and (t["r"] <= id_range + 5.0 or t["r"] < 100.0):
            threats[tid] = t

    # ---- interceptors ----
    ints = []
    for it in obs.get("interceptors", []) or []:
        try:
            iid = it["id"]
            px = float(it["pos"][0]) - ax
            py = float(it["pos"][1]) - ay
            ints.append({"id": iid, "x": px, "y": py,
                         "target": it.get("target"),
                         "age": int(it.get("age", 0) or 0)})
        except Exception:
            continue
    alive_ids = set(i["id"] for i in ints)

    # new interceptors launched with commit intent
    for i in ints:
        if i["id"] not in seen:
            seen.add(i["id"])
            if i["target"] in pending and i["target"] in threats:
                commit[i["id"]] = i["target"]
    pending.clear()

    # clean commits
    for iid in list(commit.keys()):
        if iid not in alive_ids or commit[iid] not in threats:
            del commit[iid]
    for iid in list(prev.keys()):
        if iid not in alive_ids:
            del prev[iid]

    imap = {i["id"]: i for i in ints}
    pool = [i for i in ints if i["id"] not in commit]

    # ---- coverage ----
    direct = {}
    for iid, tid in commit.items():
        direct[tid] = direct.get(tid, 0) + 1
    cover_r = 0.8 * blast
    covered = set(direct.keys())
    tgt_pts = [(threats[tid]["x"], threats[tid]["y"]) for tid in direct if tid in threats]
    for tid, t in threats.items():
        if tid in covered:
            continue
        for (qx, qy) in tgt_pts:
            if math.hypot(t["x"] - qx, t["y"] - qy) <= cover_r:
                covered.add(tid)
                break

    # ---- commit band ----
    tl = list(threats.values())
    cands = []
    for t in tl:
        if t["id"] in covered:
            continue
        dense = 0
        for u in tl:
            if abs(u["r"] - t["r"]) <= 20.0:
                dense += 1
        rc = 52.0 if dense >= 5 else 78.0
        rc = max(rc, aradius + 20.0)
        if t["r"] <= rc:
            cands.append(t)

    def nearest_pool(t):
        best, bd = None, 1e18
        for i in pool:
            d = math.hypot(i["x"] - t["x"], i["y"] - t["y"])
            if d < bd:
                bd, best = d, i
        return best

    unc = {t["id"]: t for t in cands}
    while unc and pool:
        best, bs = None, None
        for t in unc.values():
            n = 0
            for u in unc.values():
                if math.hypot(u["x"] - t["x"], u["y"] - t["y"]) <= 0.9 * blast:
                    n += 1
            s = (n, -t["r"])
            if bs is None or s > bs:
                bs, best = s, t
        i = nearest_pool(best)
        if i is None:
            break
        pool.remove(i)
        commit[i["id"]] = best["id"]
        direct[best["id"]] = direct.get(best["id"], 0) + 1
        for uid in [u["id"] for u in unc.values()
                    if math.hypot(u["x"] - best["x"], u["y"] - best["y"]) <= 0.9 * blast]:
            unc.pop(uid, None)

    launches = []
    used = 0
    # direct launches for uncovered in-band threats when pool is empty
    for t in sorted(unc.values(), key=lambda z: z["r"]):
        if used >= cap or used >= stock:
            break
        launches.append(t["id"])
        pending.add(t["id"])
        used += 1

    # spare double cover on very close threats
    future = [t for t in tl if t["id"] not in direct and t["id"] not in covered
              and t["id"] not in unc]
    spare = len(pool) - len(future)
    if spare > 0:
        for t in sorted(tl, key=lambda z: z["r"]):
            if spare <= 0:
                break
            if t["r"] <= 45.0 and direct.get(t["id"], 0) == 1:
                i = nearest_pool(t)
                if i is None:
                    break
                pool.remove(i)
                commit[i["id"]] = t["id"]
                direct[t["id"]] = 2
                spare -= 1

    # age-out: spend expiring pool interceptors
    if tl:
        for i in list(pool):
            if i["age"] >= life - 8:
                t = min(tl, key=lambda z: math.hypot(z["x"] - i["x"], z["y"] - i["y"]))
                pool.remove(i)
                commit[i["id"]] = t["id"]

    # ---- pool launches ----
    act_threats = [t for t in tl if approaching(t)]
    need = len(act_threats) - len(ints) - used
    if act_threats:
        tgt = min(act_threats, key=lambda z: z["r"])["id"]
        while need > 0 and used < cap and used < stock:
            launches.append(tgt)
            used += 1
            need -= 1

    # ---- retargets ----
    retarget = {}
    for iid, tid in commit.items():
        i = imap.get(iid)
        if i is not None and i["target"] != tid:
            retarget[iid] = tid

    tlist = list(T.values())
    far = [t for t in tlist if t["r"] > 120.0] or tlist
    for i in pool:
        if not far:
            break
        px, py = i["x"], i["y"]
        d = math.hypot(px, py)
        if d > 8.0:
            dx, dy = -px / d, -py / d
        else:
            pp = prev.get(i["id"])
            if pp is not None:
                mx, my = px - pp[0], py - pp[1]
                m = math.hypot(mx, my)
                if m > 1e-6:
                    dx, dy = -mx / m, -my / m
                else:
                    dx, dy = 1.0, 0.0
            else:
                dx, dy = 1.0, 0.0
        best, bc = None, -2.0
        for t in far:
            vx, vy = t["x"] - px, t["y"] - py
            v = math.hypot(vx, vy)
            if v < 1e-6:
                continue
            c = (vx * dx + vy * dy) / v
            if c > bc:
                bc, best = c, t
        if best is not None and best["id"] != i["target"]:
            retarget[i["id"]] = best["id"]
    for i in ints:
        prev[i["id"]] = (i["x"], i["y"])

    # ---- gun ----
    gun = None
    if ammo > 0:
        inr = [t for t in tl if t["r"] <= gun_range]
        if inr:
            uncov = [t for t in inr if t["id"] not in direct]
            pick = uncov if uncov else inr
            gun = min(pick, key=lambda z: z["r"])["id"]

    return {"intercept": launches, "retarget": retarget, "gun": gun}
