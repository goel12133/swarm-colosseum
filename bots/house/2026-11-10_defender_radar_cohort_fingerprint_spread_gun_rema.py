"""Idea: Fingerprint the hidden-orbit swarm by radar-arrival cohort, so the first burst is treated as decoys and the later bursts as strikers before any ID, then spend exactly one interceptor per striker far out and leave a depth-spread remainder for a deadline-ordered gun.

What this bot attacks in hidden_orbit_screen_then_interleaved_drop:
- The release schedule is fixed. Decoys leave the r~482 orbit at tick 14, shell A
  at tick 27 and shell B at tick 31, and all of them move at speed 4. So the 16
  decoys cross the 450 radar ring as one burst, and the 26 strikers cross about
  13 ticks later in two bursts 4 ticks apart. The order in which tracks appear on
  radar gives away their type, even though every track still reads "unknown".
  The replays show this. Against hover_bank_double_lattice (seeds 3 and 5) all 16
  decoy impacts land on the same tick, 128, and the striker kills come about 13
  ticks later. That is one clean decoy cohort followed by one clean striker
  cohort. Their docstring admits the screen only works on defenders that fire at
  unknowns. We fire at unknowns, but only at the later cohort.
- The hidden staging means every striker shows up at the radar edge about 75
  ticks before the ID ring. ID-gated defenders waste that time. We launch at
  r~400 and intercept near r~280. Each kill or miss is known long before the gun
  window opens. Missed strikers go back into the pool with no double-targeting
  and no interceptor wasted on a decoy.
- The interleaved shells are built to stop blast packing, not to stop
  one-on-one engagement. We do not try to pack blasts. In the closest calls,
  17-19 interceptor kills plus 7-9 gun kills were just enough. So we keep the
  interceptors on strikers only, and we choose which strikers to leave for the
  gun so they are spread across both shells (Bresenham spacing over range
  order). The gun can then work shell A from the first tick it is in range and
  carry on into shell B, about 23 ticks of shooting instead of 19. Gun shots go
  earliest-deadline-first and skip strikers that an inbound interceptor will
  reach in time.
- Fallback: if no second cohort appears within 25 ticks, the first cohort is
  treated as threats. Any track that IDs as a striker is always a threat.
"""
import math

NAME = "radar_cohort_fingerprint_spread_gun_remainder"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["t0"] = None
    _s["last_new"] = -999
    _s["release"] = False
    _s["pending"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _rng(t, ax, ay):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(p[0] - ax, p[1] - ay)
    return float(r)


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    a_r = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    s_spd = max(float(rules.get("striker_speed", 4.0)), 0.5)
    i_spd = float(rules.get("interceptor_speed", 12.0))

    fs = _s["first_seen"]
    for t in tracks:
        tid = t["id"]
        if tid not in fs:
            fs[tid] = tick
            _s["last_new"] = tick
            if _s["t0"] is None:
                _s["t0"] = tick
    t0 = _s["t0"]
    if t0 is not None and not _s["release"]:
        second = any(v >= t0 + 6 for v in fs.values())
        if not second and tick >= t0 + 25:
            _s["release"] = True

    def is_threat(t):
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if _s["release"] or t0 is None:
            return True
        return fs.get(t["id"], tick) > t0 + 4

    tmap = {t["id"]: t for t in tracks}
    rng = {t["id"]: _rng(t, ax, ay) for t in tracks}
    threats = {tid for tid, t in tmap.items() if is_threat(t)}

    # pending launches (not yet visible as interceptors)
    pend = _s["pending"]
    for k in list(pend.keys()):
        if tick - pend[k] > 2 or k not in tmap:
            pend.pop(k, None)
    in_flight = set()
    for it in inters:
        tg = it.get("target")
        if tg is not None:
            in_flight.add(tg)
    for k in list(pend.keys()):
        if k in in_flight:
            pend.pop(k, None)
    assigned = set(in_flight) | set(pend.keys())

    # retarget interceptors whose target is gone or not a threat
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg in tmap and tg in threats:
            continue
        ip = it.get("pos", [ax, ay])
        best, bd = None, 1e18
        for tid in threats:
            if tid in assigned:
                continue
            p = tmap[tid]["pos"]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d < bd:
                bd, best = d, tid
        if best is not None:
            retarget[it["id"]] = best
            assigned.add(best)

    # launches
    intercept = []
    cands = sorted([tid for tid in threats if tid not in assigned and rng[tid] > a_r + 6],
                   key=lambda k: rng[k])
    if cands and stock > 0:
        go = (tick - _s["last_new"] >= 6) or rng[cands[0]] < 340.0
        if go:
            n = len(cands)
            if n > stock:
                keep = []
                for i in range(n):
                    if ((i + 1) * stock) // n > (i * stock) // n:
                        keep.append(cands[i])
                # urgent ones always eligible
                urgent = [c for c in cands if rng[c] < 160.0 and c not in keep]
                keep = sorted(set(keep) | set(urgent), key=lambda k: rng[k])
            else:
                keep = cands
            for tid in keep[:min(cap, stock)]:
                intercept.append(tid)
                pend[tid] = tick
                assigned.add(tid)

    # gun: earliest deadline among strikers not covered in time
    gun = None
    if ammo > 0:
        eta = {}
        for it in inters:
            tg = retarget.get(it["id"], it.get("target"))
            if tg in tmap:
                ip = it.get("pos", [ax, ay])
                p = tmap[tg]["pos"]
                e = math.hypot(p[0] - ip[0], p[1] - ip[1]) / (i_spd + s_spd)
                eta[tg] = min(eta.get(tg, 1e9), e)
        uncovered, covered = [], []
        for tid in threats:
            r = rng[tid]
            if r > gun_range:
                continue
            deadline = (r - a_r) / s_spd
            if tid in eta and eta[tid] < deadline - 1.0:
                covered.append(tid)
            elif tid in pend and r > a_r + 40:
                covered.append(tid)
            else:
                uncovered.append(tid)
        if uncovered:
            gun = min(uncovered, key=lambda k: rng[k])
        elif covered:
            gun = min(covered, key=lambda k: rng[k])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
