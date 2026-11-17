"""Idea: Sort radar tracks into birth cohorts by the tick they first appear, skip the first cohort as a screen, and fire the whole magazine at the second cohort near the radar edge, choosing targets so the strikers left for the gun are split evenly between its two depth shells.

Target: the attacker's fixed-tick release schedule in hidden_orbit_screen_then_interleaved_drop.
  It releases decoys at tick 14 and striker shells at ticks 27 and 31, all from the same
  r~482 orbit. The radar therefore sees two clean cohorts. The 16 decoys cross r=450
  at about tick 22. About 13 ticks later, the 26 strikers cross in two sub-waves about
  4 ticks apart. The swarm never reacts to interceptors and never re-mixes the types
  after release. The cohort time alone separates screen from strikers, with no need to
  wait for the 150 ID ring.
Replay evidence: in its two closest calls (hover_bank_double_lattice, seeds 3 and 5),
  all 16 decoys hit at tick 128 in one tick. That is one tight first cohort. The
  defender won only when 19 interceptors went at strikers and the gun took the
  remaining 7-9 inside ticks ~123-145. Defenders that spent rounds on the screen, or
  that waited for ID and then crowded launches into the 2-per-tick cap near r=150,
  lost. Its margin is the magazine-plus-gun count, so this bot wastes nothing:
  - No interceptor goes at the first cohort (if IDs show it is decoys, it stays skipped).
  - All 20 rounds go at second-cohort tracks at r~300+, so every result is known before
    the gun window opens.
  - The 6 strikers left without an interceptor are spread evenly by range. That puts
    about 3 in each interleaved shell, so the gun's ~22-tick window covers both arrival
    times instead of one crowded shell.
  - The gun shoots the closest identified striker and skips any target an interceptor
    is about to hit.
"""
import math

NAME = "birth_cohort_edge_magazine_shell_balanced_gun"
ROLE = "defender"

GAP = 5       # ticks without new tracks that starts a new cohort
STABLE = 4    # ticks without growth before a cohort is committed

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cohort_of"] = {}
    _s["cohorts"] = []          # list of dicts: first, last, ids
    _s["committed"] = set()
    _s["pending"] = []
    _s["cls_seen"] = {}
    _s["launched"] = {}         # track id -> tick of last launch


def _rng(t, ax, ay):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(p[0] - ax, p[1] - ay)
    return float(r)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _label(c):
    d = s = 0
    for tid in _s["cohorts"][c]["ids"]:
        k = _s["cls_seen"].get(tid)
        if k == "decoy":
            d += 1
        elif k == "striker":
            s += 1
    if s > 0 and s >= d:
        return "striker"
    if d > 0:
        return "decoy"
    return None


def _threat(t):
    cls = t.get("cls", "unknown")
    if cls == "striker":
        return True
    if cls == "decoy":
        return False
    c = _s["cohort_of"].get(t["id"])
    if c is None:
        return False
    lab = _label(c)
    if lab == "decoy":
        return False
    if lab == "striker":
        return True
    return c >= 1


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    i_speed = float(rules.get("interceptor_speed", 12.0))

    tmap = {}
    for t in tracks:
        tmap[t["id"]] = t
        cls = t.get("cls", "unknown")
        if cls in ("striker", "decoy"):
            _s["cls_seen"][t["id"]] = cls

    # Assign each new track to a birth cohort.
    new_ids = [t["id"] for t in tracks if t["id"] not in _s["first_seen"]]
    for tid in new_ids:
        _s["first_seen"][tid] = tick
        cs = _s["cohorts"]
        if not cs or tick - cs[-1]["last"] > GAP:
            cs.append({"first": tick, "last": tick, "ids": set()})
        cs[-1]["ids"].add(tid)
        cs[-1]["last"] = tick
        _s["cohort_of"][tid] = len(cs) - 1

    # A track is covered if an interceptor is on it or one was just launched at it.
    covered = set()
    for i in inters:
        if i.get("target") is not None:
            covered.add(i.get("target"))
    for tid, lt in list(_s["launched"].items()):
        if tick - lt <= 2:
            covered.add(tid)

    pend = [tid for tid in _s["pending"]
            if tid in tmap and tid not in covered and _threat(tmap[tid])]
    _s["pending"] = pend

    # Commit stable non-screen cohorts and pick shell-balanced targets.
    for c, co in enumerate(_s["cohorts"]):
        if c in _s["committed"]:
            continue
        if tick - co["last"] < STABLE:
            continue
        lab = _label(c)
        if c == 0 and lab != "striker":
            continue
        _s["committed"].add(c)
        cands = [tmap[tid] for tid in co["ids"]
                 if tid in tmap and tid not in covered and _threat(tmap[tid])
                 and tid not in _s["pending"]]
        if not cands:
            continue
        cands.sort(key=lambda t: _rng(t, ax, ay))
        avail = max(0, stock - len(_s["pending"]))
        n = len(cands)
        if avail >= n:
            chosen = cands
        elif avail <= 0:
            chosen = []
        else:
            m = n - avail
            skip = set()
            for k in range(m):
                idx = int((k + 0.5) * n / m)
                while idx in skip and idx < n - 1:
                    idx += 1
                skip.add(min(idx, n - 1))
            chosen = [t for j, t in enumerate(cands) if j not in skip]
            chosen = chosen[:avail]
        _s["pending"].extend(t["id"] for t in chosen)

    # Launches: urgent identified strikers first, then the planned targets.
    launch = []
    budget = min(cap, stock)
    if budget > 0:
        ided = [t for t in tracks if t.get("cls") == "striker"
                and t["id"] not in covered and t["id"] not in _s["pending"]
                and _rng(t, ax, ay) > 30.0]
        ided.sort(key=lambda t: _rng(t, ax, ay))
        plan = sorted([tmap[tid] for tid in _s["pending"]],
                      key=lambda t: _rng(t, ax, ay))
        for t in ided + plan:
            if len(launch) >= budget:
                break
            if t["id"] in covered or t["id"] in launch:
                continue
            launch.append(t["id"])
        for tid in launch:
            _s["launched"][tid] = tick
            covered.add(tid)
        _s["pending"] = [tid for tid in _s["pending"] if tid not in launch]

    # Retarget interceptors whose target is gone or turned out to be a decoy.
    retarget = {}
    used = set()
    for i in inters:
        tg = i.get("target")
        tt = tmap.get(tg)
        if tt is not None and tt.get("cls") != "decoy":
            continue
        ip = i.get("pos", [ax, ay])
        best, bd = None, 1e18
        for t in tracks:
            if t["id"] in covered or t["id"] in used or not _threat(t):
                continue
            p = t["pos"]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d < bd:
                bd, best = d, t["id"]
        if best is not None:
            retarget[i["id"]] = best
            used.add(best)
            covered.add(best)

    # Gun: nearest striker in range, skipping targets an interceptor is about to hit.
    gun = None
    if ammo > 0:
        imminent = set()
        for i in inters:
            tt = tmap.get(i.get("target"))
            if tt is None:
                continue
            ip = i.get("pos", [ax, ay])
            if math.hypot(tt["pos"][0] - ip[0], tt["pos"][1] - ip[1]) < 2.0 * (i_speed + 4.0):
                imminent.add(tt["id"])
        best, bkey = None, None
        for t in tracks:
            cls = t.get("cls", "unknown")
            if cls == "decoy":
                continue
            r = _rng(t, ax, ay)
            if r > gun_range:
                continue
            key = (0 if cls == "striker" else 1,
                   1 if t["id"] in imminent else 0, r)
            if bkey is None or key < bkey:
                bkey, best = key, t["id"]
        gun = best

    return {"intercept": launch, "retarget": retarget, "gun": gun}
