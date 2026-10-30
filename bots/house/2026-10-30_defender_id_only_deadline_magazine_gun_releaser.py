"""Idea: Never spend a round on an unidentified track, pour the whole magazine onto strikers in order of their deadlines the moment they are identified, and use the gun to free in-flight interceptors so they can be retargeted onto the strikers nobody is covering.

Target: the decoy-screen-first plan in hidden_orbit_screen_then_interleaved_drop, together with its "compressed ID window" assumption.
- The attacker sends 16 decoys about 52 units ahead of 26 strikers.
- Its docstring bets that defenders will fire at unknowns, or that a defender which waits for ID cannot launch fast enough when all strikers cross r=150 together.

What the replays show:
- In its two closest losses (hover_bank_double_lattice, seeds 3 and 5) every impact was a decoy, at tick 128.
- The defender spent 19 interceptors and lost none of them to decoys.
- Gun kills were 7-9 and interceptor kills were 17-19. All 26 strikers died and the asset stayed at full HP.
- So the screen buys nothing against a shooter that only fires on identified strikers.
- Shell A is identified around tick 110 and shell B around tick 114. That leaves about 10 ticks of launch capacity: 20 rounds at 2 per tick.
- Those interceptors meet strikers at roughly r=85-110, well outside the asset.
- The gun then has about 23 ticks of close-range shots, from about tick 122 to 145.
- Its job is the uncovered tail of about 6 strikers plus about 3 interceptor misses. That is about 9 kills, and losing 2 strikers is still survivable.

How this differs from the cohort and timing counters: it makes no assumption about launch order or radar-entry timing. Two things are added:
- The gun targets the nearest striker that no interceptor is about to reach. It may also hit a covered striker whose interceptor is still far away.
- Any interceptor whose target dies (to the gun or to another blast) is retargeted at once to the uncovered striker with the earliest deadline. Misses and overlaps never strand a round.
"""
import math

NAME = "id_only_deadline_magazine_gun_releaser"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()


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
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    s_spd = float(rules.get("striker_speed", 4.0)) or 4.0
    i_spd = float(rules.get("interceptor_speed", 12.0)) or 12.0
    life = float(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []

    strikers = {}
    for t in tracks:
        if t.get("cls") != "striker":
            continue
        p = t.get("pos", [0.0, 0.0])
        px, py = float(p[0]), float(p[1])
        r = math.hypot(px - ax, py - ay)
        tti = max(0.0, (r - arad) / s_spd)
        strikers[t["id"]] = (px, py, r, tti)

    # coverage by live interceptors
    cover = {}  # track id -> min eta
    orphans = []
    for it in ints:
        tid = it.get("target")
        p = it.get("pos", [ax, ay])
        ix, iy = float(p[0]), float(p[1])
        if tid in strikers:
            sx, sy, _, _ = strikers[tid]
            eta = math.hypot(sx - ix, sy - iy) / (i_spd + s_spd)
            if tid not in cover or eta < cover[tid]:
                cover[tid] = eta
        else:
            orphans.append((it.get("id"), ix, iy, float(it.get("age", 0) or 0)))

    retarget = {}
    # retarget orphaned interceptors onto uncovered strikers by deadline
    for iid, ix, iy, age in orphans:
        best = None
        for tid, (sx, sy, r, tti) in strikers.items():
            if tid in cover:
                continue
            eta = math.hypot(sx - ix, sy - iy) / (i_spd + s_spd)
            if eta > tti + 1.0 or age + eta > life - 1:
                continue
            key = (tti, eta)
            if best is None or key < best[0]:
                best = (key, tid, eta)
        if best is not None and iid is not None:
            retarget[iid] = best[1]
            cover[best[1]] = best[2]

    # launches: uncovered identified strikers, earliest deadline first
    intercept = []
    n = min(cap, stock)
    if n > 0:
        cand = sorted((v[3], tid) for tid, v in strikers.items() if tid not in cover)
        for tti, tid in cand[:n]:
            intercept.append(tid)
            r = strikers[tid][2]
            cover[tid] = r / (i_spd + s_spd)

    # gun: nearest uncovered striker; else covered one whose interceptor is far
    gun = None
    if ammo > 0:
        inr = [(v[2], tid) for tid, v in strikers.items() if v[2] <= gun_range]
        if inr:
            inr.sort()
            unc = [x for x in inr if x[1] not in cover]
            if unc:
                gun = unc[0][1]
            else:
                far = [x for x in inr if cover.get(x[1], 0.0) > 1.5]
                gun = far[0][1] if far else inr[0][1]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
