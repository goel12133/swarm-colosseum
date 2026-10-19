"""Idea: Sort radar tracks by the tick they first appear, treat the early lone cohort as the decoy screen, and fire the whole magazine at the second cohort the moment it crosses the radar edge, without waiting for ID.

Target: the staging and release timing of hidden_orbit_screen_then_interleaved_drop.
Its release schedule is fixed. Decoys leave the r~482 orbit at tick 14. Strikers leave
at ticks 27 and 31. So the decoy screen crosses the 450 radar ring about 13 ticks (about
52 units) before any striker, and both striker shells cross within about 4 ticks of each
other. The schedule hides type from radar, but it does not hide arrival order. Arrival
order is a perfect type label for this bot.

What the replays show:
- Its closest calls against hover_bank_double_lattice (seeds 3 and 5) have the same
  shape. All 16 decoys hit untouched at tick 128, so ignoring the screen costs nothing.
- In those games all 26 strikers died to 17-19 interceptors plus 7-9 gun kills, with the
  magazine down to 0-1. The defender lost nothing to the decoys. It nearly lost because
  every engagement was squeezed into the window after the 150 ID ring, as the docstring
  intends ("compresses the defender's ID-then-engage window").
- So the screen is not the danger. The ID-gated timing is.

This bot does not wait for ID. It fingerprints cohorts by first-seen tick. A first
cohort followed by a second cohort, separated by a gap of 7+ ticks, is held as suspected
decoys. The second cohort is engaged at about r=450, two launches per tick. Interceptors
meet strikers around r~330, so the whole magazine is in flight and resolved long before
the ID ring.

The early engagement has two effects:
- Misses show up while strikers are still far out. Stock and surviving interceptors are
  retargeted onto the leftovers.
- The gun gets the inner 100 units all to itself, firing only on strikers that have no
  interceptor inbound.

Fallbacks for other attackers:
- With a single cohort, the bot fires at unknowns inside r<300.
- An ID of "striker" anywhere in the first cohort lifts the suspicion.
"""
import math

NAME = "arrival_cohort_fingerprint_edge_strike"
ROLE = "defender"

GAP = 7
SINGLE_COHORT_FIRE_R = 300.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cls"] = {}


def _cohort0(first):
    """Return the set of ids in the first cohort, or empty if there is no second cohort."""
    if not first:
        return set()
    ticks = sorted(set(first.values()))
    end0 = ticks[0]
    second = False
    for t in ticks[1:]:
        if t - end0 >= GAP:
            second = True
            break
        end0 = t
    if not second:
        return set()
    return {i for i, t in first.items() if t <= end0}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = obs.get("tick", 0)
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    launch_cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))

    first = _s["first"]
    clsmem = _s["cls"]
    tmap = {}
    for t in tracks:
        tid = t["id"]
        tmap[tid] = t
        if tid not in first:
            first[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            clsmem[tid] = c

    c0 = _cohort0(first)
    if any(clsmem.get(i) == "striker" for i in c0):
        c0 = set()
    multi = bool(c0)

    def rng(t):
        r = t.get("range")
        if r is None:
            r = math.hypot(t["pos"][0] - ax, t["pos"][1] - ay)
        return float(r)

    def kind(t):
        c = clsmem.get(t["id"], t.get("cls", "unknown"))
        if c == "striker":
            return "striker"
        if c == "decoy":
            return "decoy"
        if t["id"] in c0:
            return "suspect"
        return "unknown"

    def engageable(t):
        k = kind(t)
        if k == "striker":
            return True
        if k == "unknown":
            if multi:
                return True
            return rng(t) < SINGLE_COHORT_FIRE_R
        return False

    # current assignments
    assigned = {}
    retarget = {}
    free_inters = []
    for it in inters:
        tg = it.get("target")
        t = tmap.get(tg)
        if t is None or not engageable(t):
            free_inters.append(it)
        else:
            assigned[tg] = assigned.get(tg, 0) + 1

    cands = [t for t in tracks if engageable(t)]
    cands.sort(key=lambda t: (0 if kind(t) == "striker" else 1, rng(t)))

    # retarget free interceptors onto nearest unassigned candidate
    for it in free_inters:
        ip = it.get("pos") or [ax, ay]
        best = None
        bd = 1e18
        for t in cands:
            if assigned.get(t["id"], 0) > 0:
                continue
            d = math.hypot(t["pos"][0] - ip[0], t["pos"][1] - ip[1])
            if d < bd:
                bd = d
                best = t
        if best is not None:
            retarget[it["id"]] = best["id"]
            assigned[best["id"]] = 1

    # launches
    intercept = []
    for t in cands:
        if len(intercept) >= launch_cap or stock - len(intercept) <= 0:
            break
        if assigned.get(t["id"], 0) > 0:
            continue
        intercept.append(t["id"])
        assigned[t["id"]] = 1

    # gun: nearest striker without inbound interceptor, then any striker, then unknown
    gun = None
    if ammo > 0:
        inr = [t for t in tracks if rng(t) <= gun_range and kind(t) != "decoy"]
        if inr:
            def gkey(t):
                k = kind(t)
                pri = 0 if k == "striker" else (1 if k == "unknown" else 2)
                cov = 1 if assigned.get(t["id"], 0) > 0 else 0
                return (pri, cov, rng(t))
            inr.sort(key=gkey)
            gun = inr[0]["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
