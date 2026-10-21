"""Idea: Classify the hidden-orbit swarm by when each track first appears on radar, so the whole magazine goes to strikers before ID range, and hold a small reserve for whatever survives.

Target: 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_dro.

Which part of its logic this attacks:
The attacker uses fixed release ticks. It releases every decoy at DECOY_RELEASE=14
and the strikers at SHELL_A_RELEASE=27 and SHELL_B_RELEASE=31, all from the same
hidden orbit at r~482. As a result, the 16 decoys cross the 450 radar edge together
as one tight cohort. The 26 strikers cross about 13 to 17 ticks later as a separate
cohort. The decoy screen only works on defenders that need the 150 ID ring to tell
the two groups apart. The radar first-seen tick already tells them apart, at 450 range.

What in the replays shows it breaks there:
- The closest calls were both against hover_bank_double_lattice (score 0.76).
  - All 16 decoys hit at tick 128 and did no damage. The asset finished at hp 30.
  - All 26 strikers were killed: 17 or 19 by interceptor plus 7 or 9 by gun,
    using 19 of 20 interceptors.
  - So the swarm loses whenever no interceptor is spent on the screen and the gun
    gets clean, uncontested strikers late. Only the full 20+gun budget matters.
- Defenders that fire at unknowns were crushed (nearest_first 0.08, layered 0.10,
  annealed_eager 0.09). Their magazine went into the decoy screen.

How this defender handles it:
- Cohort timing:
  - The first radar cohort is presumed decoy whenever a later cohort exists.
  - Every later-cohort track is presumed striker.
  - The ID ring only confirms these labels.
- Magazine use:
  - One interceptor per presumed striker, launched as soon as it appears near 450.
    Intercepts land around r~330, long before the gun window.
  - A reserve of 4 is held until strikers come within 190. It then goes to the
    survivors, including any interceptor misses.
- Gun: it fires only at strikers with no interceptor inbound, nearest first. Its
  window covers both shells, about 23 ticks.
- Retargeting: an interceptor whose target died or proved to be a decoy is
  redirected to the nearest uncovered striker.
- Margin: the asset can absorb 2 striker hits (hp 30, damage 10), which gives slack.
"""
import math

NAME = "radar_cohort_presort_reserve_finisher"
ROLE = "defender"

COHORT_GAP = 5
RESERVE = 4
URGENT_R = 190.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    icpts = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    # Record the first tick each track appeared on radar.
    fs = _s["first_seen"]
    for t in tracks:
        if t["id"] not in fs:
            fs[t["id"]] = tick

    # Group first-seen ticks into cohorts split by gaps of COHORT_GAP or more.
    ticks_sorted = sorted(set(fs.values()))
    coh_of_tick = {}
    c = 0
    prev = None
    for tk in ticks_sorted:
        if prev is not None and tk - prev >= COHORT_GAP:
            c += 1
        coh_of_tick[tk] = c
        prev = tk
    ncoh = c + 1
    size0 = sum(1 for v in fs.values() if coh_of_tick.get(v, 0) == 0)

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t["pos"]
            r = math.hypot(p[0] - ax, p[1] - ay)
        return float(r)

    def kind(t):
        cls = t.get("cls", "unknown")
        if cls == "striker":
            return "S"
        if cls == "decoy":
            return "D"
        coh = coh_of_tick.get(fs.get(t["id"], tick), 0)
        if coh >= 1:
            return "S"
        if ncoh >= 2 and size0 >= 6:
            return "D"
        if rng(t) < 120.0:
            return "S"
        return "U"

    live = {}
    kinds = {}
    for t in tracks:
        live[t["id"]] = t
        kinds[t["id"]] = kind(t)

    # Count interceptors already inbound on each track.
    inbound = {}
    for ic in icpts:
        tg = ic.get("target")
        if tg in live and kinds.get(tg) == "S":
            inbound[tg] = inbound.get(tg, 0) + 1

    strikers = [t for t in tracks if kinds[t["id"]] == "S"]

    # Retarget interceptors whose target is gone or is a decoy.
    retarget = {}
    for ic in icpts:
        tg = ic.get("target")
        if tg in live and kinds.get(tg) == "S":
            continue
        ip = ic.get("pos", [ax, ay]) or [ax, ay]
        best = None
        bd = 1e18
        for t in strikers:
            if inbound.get(t["id"], 0) > 0:
                continue
            d = math.hypot(t["pos"][0] - ip[0], t["pos"][1] - ip[1])
            if d < bd:
                bd = d
                best = t["id"]
        if best is not None:
            retarget[ic["id"]] = best
            inbound[best] = inbound.get(best, 0) + 1

    # Launch interceptors, holding back RESERVE until a striker is urgent.
    launches = []
    urgent = any(rng(t) < URGENT_R for t in strikers)
    allowed = stock if urgent else max(0, stock - RESERVE)
    allowed = min(allowed, cap)
    uncovered = sorted([t for t in strikers if inbound.get(t["id"], 0) == 0], key=rng)
    for t in uncovered:
        if len(launches) >= allowed:
            break
        launches.append(t["id"])
        inbound[t["id"]] = 1
    if urgent and len(launches) < allowed:
        doubles = sorted([t for t in strikers if inbound.get(t["id"], 0) == 1
                          and rng(t) < 110.0 and t["id"] not in launches], key=rng)
        for t in doubles:
            if len(launches) >= allowed:
                break
            launches.append(t["id"])
            inbound[t["id"]] += 1

    # Gun: nearest striker with no interceptor inbound, otherwise nearest striker.
    gun = None
    if ammo > 0:
        inr = [t for t in strikers if rng(t) <= gun_range]
        if inr:
            free = [t for t in inr if inbound.get(t["id"], 0) == 0]
            pool = free if free else inr
            gun = min(pool, key=rng)["id"]
        else:
            unk = [t for t in tracks if kinds[t["id"]] == "U" and rng(t) <= gun_range]
            if unk:
                gun = min(unk, key=rng)["id"]

    return {"intercept": launches, "retarget": retarget, "gun": gun}
