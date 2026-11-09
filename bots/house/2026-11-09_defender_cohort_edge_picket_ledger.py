"""Idea: Treat the second radar contact cohort as strikers, hit them with one interceptor each as they cross the radar edge, and keep a live ledger so orphaned interceptors are retargeted and the gun only shoots strikers that no interceptor will reach.

Target: the fixed release schedule in hidden_orbit_screen_then_interleaved_drop.
DECOY_RELEASE=14 and SHELL_A/B_RELEASE=27/31 are constants. The swarm orbits at
r~482, outside the 450 radar, so every decoy crosses the radar edge together at
about tick 22. Every striker crosses at about tick 35 or 39. That leaves a gap of
about 13 ticks between contact cohorts. The attacker chose this schedule to keep
its staging hidden, but the schedule also labels each drone by when it first
appears. Type ID at 150 is not needed to sort them.

Replay evidence: in both closest calls (hover_bank_double_lattice, seeds 3 and 5)
all 16 decoy impacts land on the same tick (128). The decoys are one tight,
harmless cohort. The defender held only because nothing was spent on them: 19
interceptors and 22 gun shots went entirely to strikers (17+9 and 19+7 kills).
Defenders that lost to this bot either spent rounds on the screen or waited for
the ID ring. Waiting for ID squeezes 26 strikers into a short window against the
2-per-tick launch cap.

How this differs from ID-gated screen skipping: this bot fires at strikers near
the 450 radar edge, about 100 ticks before impact. Every missed shot is resolved
about 60 ticks before the gun window opens. If an interceptor's target dies or
turns out to be a decoy, the ledger retargets that interceptor. The gun ignores
decoys and any striker an interceptor is about to reach. It always shoots the
closest striker that is not covered, so its roughly 23 shots land where they
add kills.
"""
import math

NAME = "cohort_edge_picket_ledger"
ROLE = "defender"

COHORT_GAP = 4

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cohort_of"] = {}
    _s["cohort_last"] = []
    _s["cohort_striker"] = []
    _s["cohort_decoy"] = []
    _s["known_cls"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    gun_range = float(rules.get("gun_range", 100.0))
    launch_cap = int(rules.get("interceptor_launches_per_tick", 2))
    i_speed = float(rules.get("interceptor_speed", 12.0))

    # Sort new contacts into cohorts by the tick they first appear.
    for t in tracks:
        tid = t["id"]
        if tid not in _s["first_seen"]:
            _s["first_seen"][tid] = tick
            cl = _s["cohort_last"]
            if cl and tick - cl[-1] <= COHORT_GAP:
                c = len(cl) - 1
                cl[-1] = tick
            else:
                cl.append(tick)
                _s["cohort_striker"].append(0)
                _s["cohort_decoy"].append(0)
                c = len(cl) - 1
            _s["cohort_of"][tid] = c
        cls = t.get("cls", "unknown")
        if cls in ("striker", "decoy") and _s["known_cls"].get(tid) != cls:
            _s["known_cls"][tid] = cls
            c = _s["cohort_of"][tid]
            if cls == "striker":
                _s["cohort_striker"][c] += 1
            else:
                _s["cohort_decoy"][c] += 1

    def rng(t):
        r = t.get("range")
        if r is None:
            r = math.hypot(t["pos"][0] - ax, t["pos"][1] - ay)
        return float(r)

    def presumed_striker(t):
        cls = t.get("cls", "unknown")
        if cls == "striker":
            return True
        if cls == "decoy":
            return False
        c = _s["cohort_of"].get(t["id"], 0)
        ns = _s["cohort_striker"][c]
        nd = _s["cohort_decoy"][c]
        if ns > 0 and ns >= nd:
            return True
        if nd > 0 and ns == 0:
            return False
        # Later cohorts are presumed strikers. The first cohort is the screen.
        return c > 0

    strikers = [t for t in tracks if presumed_striker(t)]
    by_id = {t["id"]: t for t in tracks}
    striker_ids = set(t["id"] for t in strikers)

    # Ledger: which interceptors cover which striker.
    assigned = {}
    orphans = []
    for it in inters:
        tg = it.get("target")
        if tg in striker_ids:
            assigned.setdefault(tg, []).append(it)
        else:
            orphans.append(it)

    retarget = {}
    # Retarget orphans to the nearest uncovered striker.
    for it in orphans:
        ip = it.get("pos", [ax, ay])
        best = None
        bd = 1e18
        for t in strikers:
            if assigned.get(t["id"]):
                continue
            d = math.hypot(t["pos"][0] - ip[0], t["pos"][1] - ip[1])
            if d < bd:
                bd = d
                best = t
        if best is not None:
            retarget[it["id"]] = best["id"]
            assigned.setdefault(best["id"], []).append(it)

    # Launches: one per uncovered striker, earliest impact first.
    intercept = []
    uncovered = sorted([t for t in strikers if not assigned.get(t["id"])], key=rng)
    n = min(launch_cap, stock)
    for t in uncovered[:n]:
        intercept.append(t["id"])
        assigned.setdefault(t["id"], []).append({"pos": [ax, ay], "id": None})

    # Gun: closest striker in range that no interceptor will reach in the next ~2 ticks.
    gun = None
    if ammo > 0:
        best_score = 1e18
        for t in strikers:
            r = rng(t)
            if r > gun_range:
                continue
            score = r
            for it in assigned.get(t["id"], []):
                if it.get("id") is None:
                    # Fresh launch: arrives after about r / (i_speed + 4) ticks.
                    eta = r / (i_speed + 4.0)
                else:
                    ip = it.get("pos", [ax, ay])
                    d = math.hypot(t["pos"][0] - ip[0], t["pos"][1] - ip[1])
                    eta = d / (i_speed + 4.0)
                if eta < 2.5 and r > 40.0:
                    score += 200.0
                    break
            if score < best_score:
                best_score = score
                gun = t["id"]
        if gun is None:
            # No striker in range: shoot the closest unknown in range, never a confirmed decoy.
            best_r = gun_range
            for t in tracks:
                if t.get("cls") == "decoy":
                    continue
                r = rng(t)
                if r <= best_r and not presumed_striker(t) and t.get("cls") == "unknown" \
                        and _s["cohort_of"].get(t["id"], 0) > 0:
                    best_r = r
                    gun = t["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
