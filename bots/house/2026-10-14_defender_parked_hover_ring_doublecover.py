"""Idea: Park interceptors in a jittering hover next to the asset, then fire the whole magazine together at the collapsing ring once its spacing falls inside one blast width, so every striker is covered by two blasts.

Weakness exploited
------------------
2026-10-09_attacker_attacker_blast_isolated_synchronized_rel stages 26 strikers on a
ring at r=130. It then releases them all on the same tick. Its spacing math assumes the
defender commits at r~40. The pairing that exposes it is that attacker vs gun_only
(mean score_defender 0.316). There, 26 strikers arriving together overwhelmed a
single-target gun, but the attacker still had no way to stay spread out once the ring
had shrunk. The same synchronization that beats a single-target gun gives a
multi-kill defender a perfectly regular, rigidly shrinking ring. At a meeting radius of
about 31, the neighbour chord is about 0.24*31 ~ 7.5 < blast 10. One blast on any
striker therefore takes both of its neighbours too.

The attacker's real constraint is that the launch cap is 2 per tick. It assumes a
defender cannot get 20 interceptors to the ring in the 3-4 ticks the ring spends inside
blast-overlap range. This bot removes that cap. While the ring falls from r~120, it
launches interceptors 2 per tick and holds them near the asset. Each tick it retargets
every parked interceptor to whichever track lies most nearly opposite the interceptor's
current offset. That makes the interceptor jitter back and forth near the origin
instead of flying out. When the ring crosses r~42, all parked interceptors are
retargeted on one tick:
  - Pass 1 picks greedy triple covers so that every striker is inside one blast.
  - Pass 2 spends the spare interceptors on a second, shifted cover so that most
    strikers are inside two blasts.
Two independent 0.85 shots leave about 2% per striker. The gun handles the last few.
The bot does not engage the ring while it is staged and not closing.
"""
import math

NAME = "parked_hover_ring_doublecover"
ROLE = "defender"

_S = {}

ANG = 0.29        # radians: neighbours inside one blast at meeting radius ~31
DR = 8.0          # radial tolerance for "same blast"
RC = 42.0         # commit radius
LAUNCH_ETA = 24.0


def reset(seed=None):
    _S.clear()


def _st():
    if not _S:
        _S.update(filt={}, commit={}, parked=set(), seen=set(), direct=set())
    return _S


def _angdiff(a, b):
    d = abs(a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    st = _st()
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    gun_range = float(rules.get("gun_range", 100.0))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    lpt = int(rules.get("interceptor_launches_per_tick", 2))

    # ---- filter tracks (alpha-beta) ----
    filt = st["filt"]
    tracks = obs.get("tracks", []) or []
    live = set()
    T = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        live.add(tid)
        zx = float(t["pos"][0]) - ax
        zy = float(t["pos"][1]) - ay
        vel = t.get("vel") or [0.0, 0.0]
        if tid not in filt:
            filt[tid] = [zx, zy, float(vel[0]), float(vel[1])]
        else:
            f = filt[tid]
            px, py = f[0] + f[2], f[1] + f[3]
            rx, ry = zx - px, zy - py
            f[0] = px + 0.5 * rx
            f[1] = py + 0.5 * ry
            f[2] += 0.15 * rx
            f[3] += 0.15 * ry
        f = filt[tid]
        x, y = f[0], f[1]
        r = math.hypot(x, y)
        if r > 1e-6:
            vr = (x * f[2] + y * f[3]) / r
        else:
            vr = -4.0
        cls = t.get("cls", "unknown")
        closing = vr < -1.5
        eta = (r - arad) / max(-vr, 0.1) if closing else float("inf")
        T[tid] = dict(id=tid, x=x, y=y, r=r, th=math.atan2(y, x), vr=vr,
                      eta=eta, cls=cls, closing=closing, cov=0)
    for tid in list(filt.keys()):
        if tid not in live:
            del filt[tid]

    threats = {k: v for k, v in T.items() if v["cls"] != "decoy"}

    def nb(a, b):
        return _angdiff(a["th"], b["th"]) <= ANG and abs(a["r"] - b["r"]) <= DR

    # ---- interceptor bookkeeping ----
    commit = st["commit"]
    parked = st["parked"]
    seen = st["seen"]
    direct = st["direct"]
    ints = obs.get("interceptors", []) or []
    I = {}
    for it in ints:
        iid = it.get("id")
        if iid is None:
            continue
        p = it.get("pos") or [ax, ay]
        I[iid] = dict(id=iid, target=it.get("target"),
                      x=float(p[0]) - ax, y=float(p[1]) - ay,
                      age=int(it.get("age", 0) or 0))
        if iid not in seen:
            seen.add(iid)
            tg = it.get("target")
            if tg in direct:
                commit[iid] = tg
                direct.discard(tg)
            else:
                parked.add(iid)
    for iid in list(commit.keys()):
        if iid not in I:
            del commit[iid]
    for iid in list(parked):
        if iid not in I:
            parked.discard(iid)
    # orphans -> parked
    for iid in list(commit.keys()):
        if commit[iid] not in T:
            del commit[iid]
            parked.add(iid)
    direct.intersection_update(set(T.keys()))

    retarget = {}

    def add_cov(tid):
        c = T.get(tid)
        if c is None:
            return
        for o in threats.values():
            if o["id"] == tid or nb(c, o):
                o["cov"] += 1

    for iid, tg in commit.items():
        add_cov(tg)

    def nearest_parked(c):
        best, bd = None, None
        for iid in parked:
            ip = I[iid]
            d = math.hypot(ip["x"] - c["x"], ip["y"] - c["y"])
            if bd is None or d < bd:
                best, bd = iid, d
        return best

    def do_commit(iid, tid):
        parked.discard(iid)
        commit[iid] = tid
        retarget[iid] = tid
        add_cov(tid)

    # ---- expiring parked interceptors ----
    for iid in list(parked):
        if I[iid]["age"] >= 80:
            cands = [t for t in threats.values() if t["closing"]] or list(threats.values())
            if cands:
                c = min(cands, key=lambda t: (t["cov"], t["r"]))
                do_commit(iid, c["id"])

    # ---- commit phase ----
    zone = [t for t in threats.values() if t["closing"] and (t["r"] <= RC or t["eta"] <= 4.5)]
    while parked:
        unc = [t for t in zone if t["cov"] == 0]
        if not unc:
            break
        best, bv = None, -1
        for c in zone:
            v = sum(1 for o in unc if o is c or nb(c, o))
            if v > bv or (v == bv and best is not None and c["r"] < best["r"]):
                best, bv = c, v
        if best is None or bv <= 0:
            break
        iid = nearest_parked(best)
        do_commit(iid, best["id"])

    outside = [t for t in threats.values() if t["closing"] and t not in zone and t["eta"] <= 40]
    reserve = int(math.ceil(len(outside) / 2.2))
    while len(parked) > reserve:
        once = [t for t in zone if t["cov"] == 1]
        if not once:
            break
        best, bv = None, -1
        for c in zone:
            v = sum(1 for o in once if o is c or nb(c, o))
            if v > bv:
                best, bv = c, v
        if best is None or bv <= 0:
            break
        iid = nearest_parked(best)
        do_commit(iid, best["id"])

    # ---- hover steering for parked interceptors ----
    far = [t for t in T.values() if t["r"] > 60] or list(T.values())
    for iid in list(parked):
        ip = I[iid]
        if not far:
            break
        px, py = ip["x"], ip["y"]
        pm = math.hypot(px, py)
        if pm < 1e-6:
            c = max(far, key=lambda t: t["r"])
        else:
            c = min(far, key=lambda t: (t["x"] * px + t["y"] * py) / max(t["r"], 1e-6))
        if ip["target"] != c["id"]:
            retarget[iid] = c["id"]

    # ---- launches ----
    launches = []
    if stock > 0:
        urgent = sorted([t for t in zone if t["cov"] == 0], key=lambda t: t["eta"])
        for t in urgent:
            if len(launches) >= min(lpt, stock):
                break
            launches.append(t["id"])
            direct.add(t["id"])
            add_cov(t["id"])
        soon = [t for t in threats.values() if t["closing"] and t["eta"] <= LAUNCH_ETA and t["cov"] == 0]
        need = int(math.ceil(0.8 * len(soon))) + 1 if soon else 0
        while len(launches) < min(lpt, stock) and len(parked) + len(launches) < need:
            cands = [t for t in soon if t["id"] not in direct] or soon
            c = min(cands, key=lambda t: t["eta"])
            launches.append(c["id"])

    # ---- gun ----
    gun = None
    if ammo > 0:
        cands = [t for t in threats.values() if t["r"] <= gun_range]
        if cands:
            g = min(cands, key=lambda t: (t["cov"] > 0, 0 if t["cls"] == "striker" else 1, t["r"]))
            gun = g["id"]
        else:
            dc = [t for t in T.values() if t["r"] <= gun_range and t["closing"]]
            if dc:
                gun = min(dc, key=lambda t: t["r"])["id"]

    return {"intercept": launches, "retarget": retarget, "gun": gun}
