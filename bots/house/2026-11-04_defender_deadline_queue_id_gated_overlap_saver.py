"""Idea: Hold every interceptor until a track is identified as a striker, then launch on a deadline-ordered schedule that respects the two-per-tick launch cap, and lean on blast overlap only when the magazine is actually short.

Why it holds up across the attacker field:
- Bait, decoy-screen and "count then clear sky" attackers (bait_count_then_clear_sky_wave,
  staggered_screen_trickle, hidden_orbit_screen):
  - Nothing is spent on tracks beyond identification range, or on tracks identified as decoys.
  - Launches start only around 90 units out, well inside the 150-unit ID range, so the
    magazine is still full when the real wave arrives.
- Synchronized and phase-locked rings:
  - Simultaneous arrivals beat defenders that react tick by tick, because only two
    interceptors can launch per tick.
  - Here every uncovered threat is sorted by its launch deadline. The k-th threat must
    leave by tick k//2, so a dense ring triggers launches early enough that every
    striker gets an interceptor before the last safe intercept radius.
  - Rings converge, so once threats outnumber stock, drones flying in formation near an
    already-targeted drone (inside the blast radius) count as covered. Each interceptor
    can then remove several drones.
- Depth-shell and interleaved-shell saturation:
  - The deadline schedule is computed per track from its smoothed radial closing rate,
    so staggered depths fill the launch slots in order instead of bunching up.
  - Interceptors whose target dies, or turns out to be a decoy, retarget to the nearest
    uncovered striker instead of being wasted.
- Orbit and loiter tricks:
  - Time-to-intercept uses the smoothed radial speed, with a floor, so tracks circling
    outside do not trigger launches. A dive is picked up as soon as the closing rate
    rises.
- Leakers and misses (a single interceptor kills with probability 0.85):
  - The preferred intercept radius leaves time for a second interceptor before the
    40-unit limit.
  - The gun always fires at the most urgent threat in range, favouring threats with no
    interceptor assigned.
"""

import math

NAME = "deadline_queue_id_gated_overlap_saver"
ROLE = "defender"

_state = {}


def reset(seed=None):
    _state.clear()
    _state["smooth"] = {}
    _state["last_tick"] = -1


def _g(rules, key, default):
    try:
        v = rules.get(key, default)
        return default if v is None else v
    except Exception:
        return default


def _smooth(tracks):
    sm = _state.setdefault("smooth", {})
    seen = set()
    out = {}
    for t in tracks:
        tid = t.get("id")
        try:
            px, py = float(t["pos"][0]), float(t["pos"][1])
        except Exception:
            continue
        try:
            vx, vy = float(t["vel"][0]), float(t["vel"][1])
        except Exception:
            vx, vy = 0.0, 0.0
        seen.add(tid)
        prev = sm.get(tid)
        if prev is None:
            s = [px, py, vx, vy, 1]
        else:
            n = prev[4] + 1
            a = 0.45 if n > 3 else 0.7
            predx = prev[0] + prev[2]
            predy = prev[1] + prev[3]
            nx = a * px + (1 - a) * predx
            ny = a * py + (1 - a) * predy
            b = 0.35
            nvx = b * vx + (1 - b) * prev[2]
            nvy = b * vy + (1 - b) * prev[3]
            s = [nx, ny, nvx, nvy, n]
        sm[tid] = s
        out[tid] = s
    for k in list(sm.keys()):
        if k not in seen:
            del sm[k]
    return out


def _act(obs):
    if "smooth" not in _state:
        reset(0)
    rules = obs.get("rules", {}) or {}
    asset_r = float(_g(rules, "asset_radius", 25.0))
    id_range = float(_g(rules, "id_range", 150.0))
    i_speed = float(_g(rules, "interceptor_speed", 12.0))
    d_speed = float(_g(rules, "striker_speed", 4.0))
    blast = float(_g(rules, "blast_radius", 10.0))
    gun_range = float(_g(rules, "gun_range", 100.0))
    lpt = int(_g(rules, "interceptor_launches_per_tick", 2))
    lifetime = float(_g(rules, "interceptor_lifetime", 90))

    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    sm = _smooth(tracks)

    R_PREF = 70.0
    R_MIN = 40.0

    info = {}
    threats = []
    for t in tracks:
        tid = t.get("id")
        if tid not in sm:
            continue
        s = sm[tid]
        sx, sy, vx, vy = s[0], s[1], s[2], s[3]
        try:
            raw_r = float(t.get("range", math.hypot(sx, sy)))
        except Exception:
            raw_r = math.hypot(sx, sy)
        r = math.hypot(sx, sy)
        if r < 1e-6:
            r = 1e-6
        vr = -(sx * vx + sy * vy) / r
        vr_eff = max(vr, 0.25 * d_speed)
        tti = max(0.0, (r - asset_r)) / vr_eff
        cls = t.get("cls", "unknown")
        is_threat = (cls == "striker") or (cls == "unknown" and raw_r <= id_range * 1.02)
        # predicted intercept radius if launched now from origin
        r_i = i_speed * r / (i_speed + vr_eff)
        rate = vr_eff * i_speed / (i_speed + vr_eff)
        d = {"id": tid, "x": sx, "y": sy, "vx": vx, "vy": vy, "r": r,
             "raw_r": raw_r, "tti": tti, "cls": cls, "r_i": r_i, "rate": rate,
             "threat": is_threat}
        info[tid] = d
        if is_threat:
            threats.append(d)

    threat_ids = set(d["id"] for d in threats)
    scarce = stock + len(inters) < len(threats)

    def near_formation(a, b):
        dx = a["x"] - b["x"]
        dy = a["y"] - b["y"]
        if dx * dx + dy * dy > (0.7 * blast) ** 2:
            return False
        dvx = a["vx"] - b["vx"]
        dvy = a["vy"] - b["vy"]
        return dvx * dvx + dvy * dvy < 1.5 * 1.5

    covered = set()

    def cover(tid):
        covered.add(tid)
        if scarce and tid in info:
            a = info[tid]
            for b in threats:
                if b["id"] not in covered and near_formation(a, b):
                    covered.add(b["id"])

    retarget = {}
    orphans = []
    for it in inters:
        tgt = it.get("target")
        if tgt in threat_ids:
            cover(tgt)
        else:
            orphans.append(it)

    # retarget orphans to nearest uncovered threat
    for it in orphans:
        try:
            ix, iy = float(it["pos"][0]), float(it["pos"][1])
        except Exception:
            continue
        age = float(it.get("age", 0) or 0)
        remaining = max(1.0, lifetime - age)
        best = None
        bestd = 1e18
        for d in threats:
            dist = math.hypot(d["x"] - ix, d["y"] - iy)
            if dist > remaining * (i_speed + d_speed):
                continue
            pen = 0.0 if d["id"] not in covered else 1000.0
            score = dist + pen
            if score < bestd:
                bestd = score
                best = d
        if best is not None:
            retarget[it.get("id")] = best["id"]
            cover(best["id"])

    # deadline-ordered launch scheduling
    launches = []
    cand = [d for d in threats if d["id"] not in covered and d["r_i"] > asset_r + 3.0]
    for d in cand:
        d["slack"] = (d["r_i"] - R_MIN) / max(d["rate"], 1e-3)
        d["pref"] = (d["r_i"] - R_PREF) / max(d["rate"], 1e-3)
    cand.sort(key=lambda d: d["slack"])
    cap = min(lpt, stock)
    if cap > 0 and cand:
        trigger = False
        for k, d in enumerate(cand):
            if d["pref"] <= (k // max(1, lpt)):
                trigger = True
                break
        if trigger:
            for d in cand:
                if len(launches) >= cap:
                    break
                if d["id"] in covered:
                    continue
                # do not launch absurdly early (beyond lifetime reach)
                t_hit = d["r"] / (i_speed + max(d["rate"], 0.1))
                if t_hit > lifetime * 0.9:
                    continue
                launches.append(d["id"])
                cover(d["id"])

    # gun: most urgent threat in range, prefer ones not covered
    gun = None
    if ammo > 0:
        best = None
        bestk = 1e18
        for d in threats:
            if d["raw_r"] > gun_range:
                continue
            k = d["tti"] + (12.0 if (d["id"] in covered and d["id"] not in launches) else 0.0)
            if k < bestk:
                bestk = k
                best = d
        if best is not None:
            gun = best["id"]

    return {"intercept": launches, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
