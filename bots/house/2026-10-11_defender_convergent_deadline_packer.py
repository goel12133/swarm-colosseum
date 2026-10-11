"""Idea: Launches are held back until a capacity-aware deadline forces them, and the delay is spent hunting for intercept moments where one blast covers several identified strikers.

Why it holds up across the attacker field:
- Synchronized, phase-locked and interleaved rings win by arriving together and outnumbering
  the magazine. Strikers on converging radial paths draw closer to each other as they approach.
  So this bot only fires on its own schedule. It fires when a predicted blast covers two or more
  uncovered strikers, or when a per-target commit deadline arrives. The deadline is checked
  against the launch-rate cap: it counts how many strikers must be served in the next k ticks
  and compares that with cap*k launch slots. A simultaneous wave therefore never jams the
  launcher. The commit radius moves inward when the magazine is scarce, which buys more
  convergence per interceptor.
- Decoy screens, staggered trickles, magazine-drain parks and shadow pairs are cheap and
  numerous. Interceptors are spent only on tracks identified as strikers. A striker always
  enters identification range at least 30 ticks before impact, which is ample for a
  12-speed interceptor, so a decoy is never bought with a 4-cost round. Interceptors whose
  target dies or turns out to be a decoy are retargeted to the best uncovered striker
  instead of being wasted.
- Depth-shell saturation and trishell blast denial spread drones out to defeat blasts. Against
  those, the cluster rule simply finds nothing, and the bot falls back to one-shot-one-kill
  deadline scheduling. A striker whose interceptor missed is released and re-served.
- The gun is the last layer. It fires every tick at the most urgent striker inside gun range,
  or at an unknown track if no striker is in range. It skips targets an interceptor is about
  to hit, and it never fires at decoys.
Velocity is smoothed over several ticks to reduce track noise. The bot is deterministic and
uses only the standard library.
"""

import math

NAME = "convergent_deadline_packer"
ROLE = "defender"

_S = {}


def reset(seed=None):
    _S.clear()


def _st():
    if "hist" not in _S:
        _S["hist"] = {}          # track id -> list of (tick, x, y)
        _S["collat"] = {}        # interceptor id -> set of track ids covered as collateral
        _S["pending"] = {}       # launched target id -> (tick, set of collateral ids)
    return _S


def _intercept_time(dx, dy, vx, vy, s):
    a = vx * vx + vy * vy - s * s
    b = 2.0 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    if abs(a) < 1e-9:
        if b >= 0:
            return None
        return -c / b
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    cands = [t for t in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)) if t > 0]
    return min(cands) if cands else None


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    st = _st()
    rules = obs.get("rules", {}) or {}
    tick = obs.get("tick", 0)
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    s_int = float(rules.get("interceptor_speed", 12.0))
    blast = float(rules.get("blast_radius", 10.0))
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []

    # Track state with smoothed velocity.
    hist = st["hist"]
    T = {}
    for tr in tracks:
        tid = tr.get("id")
        p = tr.get("pos") or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        h = hist.setdefault(tid, [])
        h.append((tick, x, y))
        if len(h) > 8:
            del h[0]
        v = tr.get("vel") or [0.0, 0.0]
        vx, vy = float(v[0]), float(v[1])
        if len(h) >= 3:
            t0, x0, y0 = h[0]
            dt = tick - t0
            if dt > 0:
                svx, svy = (x - x0) / dt, (y - y0) / dt
                vx, vy = 0.5 * vx + 0.5 * svx, 0.5 * vy + 0.5 * svy
        r = math.hypot(x, y)
        T[tid] = {"x": x, "y": y, "vx": vx, "vy": vy, "r": r,
                  "cls": tr.get("cls", "unknown")}
    for tid in list(hist.keys()):
        if tid not in T:
            del hist[tid]

    # Interceptor bookkeeping.
    collat = st["collat"]
    pending = st["pending"]
    live_ids = set()
    covered = {}
    for it in inters:
        iid = it.get("id")
        live_ids.add(iid)
        tgt = it.get("target")
        if iid not in collat:
            if tgt in pending:
                collat[iid] = pending.pop(tgt)[1]
            else:
                collat[iid] = set()
    for iid in list(collat.keys()):
        if iid not in live_ids:
            del collat[iid]
    for k in list(pending.keys()):
        if tick - pending[k][0] > 3:
            del pending[k]

    def is_striker(tid):
        return tid in T and T[tid]["cls"] == "striker"

    def pred(tid, t):
        d = T[tid]
        return d["x"] + d["vx"] * t, d["y"] + d["vy"] * t

    retarget = {}
    free_inters = []
    for it in inters:
        iid = it.get("id")
        tgt = it.get("target")
        if tgt in T and T[tgt]["cls"] != "decoy":
            covered[tgt] = covered.get(tgt, 0) + 1
            for c in collat.get(iid, ()):
                covered[c] = covered.get(c, 0) + 1
        else:
            free_inters.append(it)
    for k, (_, cs) in pending.items():
        covered[k] = covered.get(k, 0) + 1
        for c in cs:
            covered[c] = covered.get(c, 0) + 1

    def uncovered_strikers():
        return [tid for tid in T if is_striker(tid) and covered.get(tid, 0) == 0]

    # Retarget interceptors whose target is gone or is a decoy.
    for it in free_inters:
        iid = it.get("id")
        ip = it.get("pos") or [ax, ay]
        ix, iy = float(ip[0]) - ax, float(ip[1]) - ay
        age = int(it.get("age", 0))
        life_left = max(1, int(rules.get("interceptor_lifetime", 90)) - age)
        best, bt = None, None
        for tid in uncovered_strikers():
            d = T[tid]
            t = _intercept_time(d["x"] - ix, d["y"] - iy, d["vx"], d["vy"], s_int)
            if t is None or t > life_left:
                continue
            if bt is None or t < bt:
                best, bt = tid, t
        if best is not None:
            retarget[iid] = best
            covered[best] = covered.get(best, 0) + 1
            collat[iid] = set()

    # Launch scheduling.
    unc = uncovered_strikers()
    n_unknown = sum(1 for d in T.values() if d["cls"] == "unknown")
    scarce = (len(unc) + 0.5 * n_unknown) > stock
    r_commit = arad + 20.0 if scarce else arad + 42.0

    info = {}
    for tid in unc:
        d = T[tid]
        t = _intercept_time(d["x"], d["y"], d["vx"], d["vy"], s_int)
        if t is None:
            t = d["r"] / s_int
        px, py = pred(tid, t)
        r_int = math.hypot(px, py)
        vr = 0.0
        if d["r"] > 1e-6:
            vr = -(d["x"] * d["vx"] + d["y"] * d["vy"]) / d["r"]
        vr = max(0.5, vr)
        rate = vr * s_int / (s_int + vr)
        t_commit = (r_int - r_commit) / rate
        clu = set()
        for oj in unc:
            if oj == tid:
                continue
            qx, qy = pred(oj, t)
            if math.hypot(qx - px, qy - py) < 0.8 * blast:
                clu.add(oj)
        info[tid] = {"t": t, "r_int": r_int, "tc": t_commit, "clu": clu}

    launches = []
    used = set()
    slots = min(cap, stock)

    order = sorted(unc, key=lambda k: info[k]["tc"])
    must = 0
    for i, tid in enumerate(order):
        if info[tid]["tc"] <= (i // max(1, cap)):
            must = i + 1
    for tid in order[:must]:
        if len(launches) >= slots:
            break
        if tid in used:
            continue
        launches.append(tid)
        cs = set(c for c in info[tid]["clu"] if c not in used)
        used.add(tid)
        used |= cs
        pending[tid] = (tick, cs)

    if len(launches) < slots:
        opp = [k for k in unc if k not in used and len(info[k]["clu"]) >= 1
               and info[k]["r_int"] > arad + 12.0]
        opp.sort(key=lambda k: (-len(info[k]["clu"]), info[k]["tc"]))
        for tid in opp:
            if len(launches) >= slots:
                break
            if tid in used:
                continue
            cs = set(c for c in info[tid]["clu"] if c not in used)
            if not cs:
                continue
            launches.append(tid)
            used.add(tid)
            used |= cs
            pending[tid] = (tick, cs)

    # Gun: most urgent striker in range, else unknown; skip targets about to be hit.
    gun = None
    if ammo > 0:
        inter_pos = []
        for it in inters:
            ip = it.get("pos") or [ax, ay]
            inter_pos.append((it.get("target"), float(ip[0]) - ax, float(ip[1]) - ay))
        best_key = None
        for tid, d in T.items():
            if d["cls"] == "decoy" or d["r"] > gun_range:
                continue
            imminent = False
            for (tg, ix, iy) in inter_pos:
                if tg == tid and math.hypot(ix - d["x"], iy - d["y"]) < 2 * s_int:
                    imminent = True
                    break
            pri = 0 if d["cls"] == "striker" else 1
            key = (1 if imminent else 0, pri, d["r"])
            if best_key is None or key < best_key:
                best_key, gun = key, tid

    return {"intercept": launches, "retarget": retarget, "gun": gun}
