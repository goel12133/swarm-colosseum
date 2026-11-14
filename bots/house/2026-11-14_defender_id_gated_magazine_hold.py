"""Idea: Hold every interceptor until the radar's ID gate confirms a track is a striker, so decoy floods can never drain the magazine, then spend the full stock on the released striker wave and recycle missed or orphaned interceptors.

Weakness targeted: 2026-10-15_attacker_2026_10_15_attacker_dark_ring_release only
wins if the defender fires interceptors at unidentified tracks. It parks strikers at
radius ~475, outside the 450 radar, and sends decoys first. Defenders that commit to
the nearest unknown track spend all 20 interceptors on 0.5-credit decoys. The strikers
are then released together and saturate the single gun.

Pairing that shows it: 2026-10-15_attacker_2026_10_15_attacker_dark_ring_release vs
2026-10-06_defender_contracting_ring_blaster (mean score_defender 0.054). In seed 0
that defender fired 20 interceptors, killed 2 decoys, and ended with stock_left 0.
It also fired 20 gun shots, so 7 strikers impacted together at tick 296 while
100 gun rounds were still unused.

Counter: decoys do no damage, so ignore them completely. Identification happens at
150 units. From there a striker needs about 31 ticks to reach the asset. An
interceptor closes the gap in about 9 ticks, and the 2-per-tick launch cap empties the
magazine into a 20-striker wave in 10 ticks, so waiting costs nothing. Each confirmed
striker gets one interceptor, nearest first. An interceptor whose target vanished is
retargeted onto an uncovered striker. A striker whose interceptor missed becomes
uncovered again and is re-engaged. The gun shoots the closest striker inside 100 units
and prefers one with no interceptor already on it. It never shoots a decoy.
"""

NAME = "id_gated_magazine_hold"
ROLE = "defender"

_state = {}


def reset(seed):
    _state.clear()


def _dist(p):
    try:
        return (float(p[0]) ** 2 + float(p[1]) ** 2) ** 0.5
    except Exception:
        return 1e9


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    gun_range = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    apos = (obs.get("asset", {}) or {}).get("pos", [0.0, 0.0]) or [0.0, 0.0]

    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []

    info = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        pos = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        r = t.get("range")
        if r is None:
            r = _dist([pos[0] - apos[0], pos[1] - apos[1]])
        info[tid] = (float(r), t.get("cls", "unknown"))

    # Threats: confirmed strikers. Unknown tracks deep inside the ID gate are a
    # fallback, in case ID is noisy.
    strikers = sorted([tid for tid, (r, c) in info.items() if c == "striker"],
                      key=lambda k: info[k][0])
    close_unknown = sorted([tid for tid, (r, c) in info.items()
                            if c == "unknown" and r < 110.0],
                           key=lambda k: info[k][0])
    threats = strikers + close_unknown

    covered = {}
    orphans = []
    for it in inters:
        iid = it.get("id")
        tgt = it.get("target")
        age = int(it.get("age", 0) or 0)
        if tgt in info and info[tgt][1] != "decoy":
            covered[tgt] = covered.get(tgt, 0) + 1
        elif iid is not None and age < life - 8:
            orphans.append((age, iid))
    orphans.sort()

    uncovered = [t for t in threats if covered.get(t, 0) == 0]

    # Retarget orphaned interceptors (target dead or a decoy) onto uncovered threats.
    retarget = {}
    for _, iid in orphans:
        if not uncovered:
            break
        tgt = uncovered.pop(0)
        retarget[iid] = tgt
        covered[tgt] = covered.get(tgt, 0) + 1

    # Launch new interceptors at remaining uncovered threats, nearest first.
    intercept = []
    n = min(per_tick, stock)
    while uncovered and len(intercept) < n:
        tgt = uncovered.pop(0)
        intercept.append(tgt)
        covered[tgt] = covered.get(tgt, 0) + 1

    # With spare stock, double-cover strikers that are already close and fast-approaching.
    if len(intercept) < n and stock - len(intercept) > len(strikers):
        for tgt in strikers:
            if len(intercept) >= n:
                break
            if info[tgt][0] < 90.0 and covered.get(tgt, 0) < 2:
                intercept.append(tgt)
                covered[tgt] = covered.get(tgt, 0) + 1

    # Gun: closest threat in range, preferring ones without interceptor coverage.
    gun = None
    if ammo > 0:
        in_range = [t for t in threats if info[t][0] <= gun_range]
        if in_range:
            in_range.sort(key=lambda k: (covered.get(k, 0) > 0, info[k][0]))
            # Always prioritise anything about to impact, regardless of coverage.
            nearest = min(in_range, key=lambda k: info[k][0])
            if info[nearest][0] < 45.0:
                gun = nearest
            else:
                gun = in_range[0]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
