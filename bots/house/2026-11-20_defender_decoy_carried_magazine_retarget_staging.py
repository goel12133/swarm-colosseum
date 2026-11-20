"""Idea: Launch the magazine early at the harmless decoy screen and retarget those interceptors in flight onto the striker shells the moment they cross the radar edge.

Target: the fixed release schedule in hidden_orbit_screen_then_interleaved_drop.
Its decoys always release at tick 14 and its strikers at ticks 27 and 31,
whatever the defender does. That puts a single 16-track cohort on radar at about
tick 22. Then there is a quiet gap of about 13 ticks. Then the 26-track striker
cohort arrives in two shells about 4 ticks apart. The replays show this lockstep
timing. In both closest calls, all 16 decoys impact on the same tick (128), so
the screen moves as one block well ahead of the strikers.

The attacker's plan has two parts. Strikers stay hidden until late, and the
defender is pushed into a compressed launch window at 2 per tick near the
150-unit ID ring. Most counters skip the screen and wait. This bot uses the
screen instead.

How the bot plays:
- About 16 interceptors are launched at the decoys between ticks 22 and 30, one
  per decoy, so they spread evenly around the ring. They fly outward on decoy
  bearings while no threat is visible. If one gets close to its decoy before any
  striker shows, it is turned toward the farthest decoy so it stays in the air.
- Any track first seen after the screen window is treated as a suspected striker.
  When those tracks appear, the in-flight interceptors are greedily retargeted to
  the nearest uncovered striker. Kills therefore happen near r~380 instead of
  inside 150. That avoids the launch-cap squeeze at the ID ring and leaves plenty
  of time before impact.
- 4 interceptors are kept in reserve. They are fired only when a striker the
  interceptors did not cover gets inside about 60 units and the gun has more than
  one target. This covers the far-field misses and gun failures.
- The gun only shoots strikers. It prefers uncovered strikers, nearest first.

Server ID results override the cohort guess: a track identified as a decoy frees
its interceptor for retargeting.
"""
import math

NAME = "decoy_carried_magazine_retarget_staging"
ROLE = "defender"

SCREEN_WIN = 4
STAGE = 16
RESERVE = 4
PINGPONG_DIST = 45.0
DEADLINE_R = 60.0
LAST_R = 45.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["fs"] = {}
    _s["fc"] = None
    _s["staged"] = 0
    _s["recent"] = {}
    _s["last_h"] = -999


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "fs" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gr = float(rules.get("gun_range", 100.0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]

    fs = _s["fs"]
    for t in tracks:
        if t["id"] not in fs:
            fs[t["id"]] = tick
    if tracks and _s["fc"] is None:
        _s["fc"] = tick
    fc = _s["fc"]

    def rng(t):
        r = t.get("range")
        if r is None:
            r = _d(t["pos"], ap)
        return float(r)

    def hostile(t):
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        return fc is not None and fs.get(t["id"], tick) > fc + SCREEN_WIN

    H = [t for t in tracks if hostile(t)]
    Hid = set(t["id"] for t in H)
    for t in H:
        if fs.get(t["id"]) == tick:
            _s["last_h"] = tick
    carriers = [t for t in tracks if t["id"] not in Hid]
    byid = {t["id"]: t for t in tracks}

    cov = {}
    for i in ints:
        tg = i.get("target")
        if tg in Hid:
            cov[tg] = cov.get(tg, 0) + 1
    rec = _s["recent"]
    for tid in list(rec.keys()):
        if tick - rec[tid] > 1:
            del rec[tid]
        elif tid in Hid and cov.get(tid, 0) == 0:
            cov[tid] = 1

    retarget = {}
    free = [i for i in ints if i.get("target") not in Hid]
    uncovered = [h for h in H if cov.get(h["id"], 0) == 0]

    # greedy nearest matching of free interceptors to uncovered hostiles
    if free and uncovered:
        pairs = []
        for i in free:
            for h in uncovered:
                pairs.append((_d(i["pos"], h["pos"]), i["id"], h["id"]))
        pairs.sort()
        used_i, used_h = set(), set()
        for dd, iid, hid in pairs:
            if iid in used_i or hid in used_h:
                continue
            used_i.add(iid)
            used_h.add(hid)
            retarget[iid] = hid
            cov[hid] = cov.get(hid, 0) + 1
        free = [i for i in free if i["id"] not in used_i]

    # leftover free interceptors: keep staged on the screen, or double cover
    quiet = (tick - _s["last_h"]) > 8
    for i in free:
        tg = i.get("target")
        tt = byid.get(tg)
        if H and quiet:
            best = min(H, key=lambda h: (cov.get(h["id"], 0), _d(i["pos"], h["pos"])))
            retarget[i["id"]] = best["id"]
            cov[best["id"]] = cov.get(best["id"], 0) + 1
            continue
        if not carriers:
            if H:
                best = min(H, key=lambda h: _d(i["pos"], h["pos"]))
                retarget[i["id"]] = best["id"]
            continue
        if tt is None or _d(i["pos"], tt["pos"]) < PINGPONG_DIST:
            far = max(carriers, key=lambda c: _d(i["pos"], c["pos"]))
            if far["id"] != tg:
                retarget[i["id"]] = far["id"]

    # launches
    intercept = []
    avail = min(cap, stock)
    unc = sorted([h for h in H if cov.get(h["id"], 0) == 0], key=rng)
    for h in unc:
        if len(intercept) >= avail:
            break
        if stock - len(intercept) > RESERVE:
            intercept.append(h["id"])
            cov[h["id"]] = 1
    unc = [h for h in unc if cov.get(h["id"], 0) == 0]
    in_gun = [h for h in unc if rng(h) <= gr]
    for h in unc:
        if len(intercept) >= avail or stock - len(intercept) <= 0:
            break
        r = rng(h)
        if r < LAST_R or (r < DEADLINE_R and len(in_gun) >= 2):
            intercept.append(h["id"])
            cov[h["id"]] = 1

    # staging on the decoy screen while no threat is visible
    if not H and carriers and _s["staged"] < STAGE:
        cnt = {}
        for i in ints:
            tg = i.get("target")
            cnt[tg] = cnt.get(tg, 0) + 1
        for tid in rec:
            cnt[tid] = cnt.get(tid, 0) + 1
        cands = [c for c in carriers if rng(c) > 250.0]
        cands.sort(key=lambda c: (cnt.get(c["id"], 0), -rng(c)))
        for c in cands:
            if len(intercept) >= avail or _s["staged"] >= STAGE:
                break
            if stock - len(intercept) <= RESERVE:
                break
            intercept.append(c["id"])
            _s["staged"] += 1

    for tid in intercept:
        rec[tid] = tick

    # gun
    gun = None
    if ammo > 0:
        inr = [h for h in H if rng(h) <= gr]
        if inr:
            u = [h for h in inr if cov.get(h["id"], 0) == 0]
            pool = u if u else inr
            gun = min(pool, key=rng)["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
