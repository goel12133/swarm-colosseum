"""Idea: Sort radar-edge arrivals into cohorts by first-seen tick, skip the first cohort as the decoy screen, fire the whole magazine at the later cohorts from 450 out, and split the leftovers evenly between the two striker shells so the gun has the longest possible window.

Target: the fixed release schedule of hidden_orbit_screen_then_interleaved_drop.
- The attacker releases decoys at tick 14 and its two striker shells at ticks 27 and 31.
  Its release code ignores everything the defender does. All drones fly straight in
  from r~482.
- So the 16 decoys cross the 450 radar edge together, around tick 22. There are then
  about 13 quiet ticks. After that the two striker shells appear as two tight cohorts,
  around ticks 35 and 39.
- Cohort timing therefore classifies every track roughly 75 ticks before the 150 ID ring.
  The attacker's "unit-agnostic" orbit code cannot hide this.
- The interleaving is built to make blast and convergence packers miss, but it has a cost.
  Each shell is synchronised, so the leftovers from shell A all impact near tick 141 and
  the leftovers from shell B near tick 145.

Replay evidence (its two closest calls, both against hover_bank_double_lattice):
- All 16 decoys impacted together at tick 128 with zero interceptors spent on them, so
  the screen bought nothing against a defender that ignored it.
- 19 interceptors produced 17 striker kills, which is the expected 0.85 kill probability.
  The gun then needed 7 to 9 kills from 22 shots.
- The match was decided entirely by the gun's leftover workload.

How this bot uses that:
- No interceptor is ever spent on the screen.
- All 20 interceptors launch early, as soon as the striker cohorts have settled.
- Targets are always taken from whichever shell has the most uncovered strikers. The
  roughly 6 strikers left uncovered, plus any misses, are then split between shells A
  and B. This gives the gun about 23 usable ticks (r=100 to impact) instead of 19 for
  one shell.
- The gun prefers uncovered strikers and shoots the nearest first.
"""
import math

NAME = "cohort_screen_skip_shell_balanced_gun"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["first_any"] = None
    _s["last_new"] = None
    _s["pending"] = {}  # track id -> tick when an interceptor was requested


def _cohorts(first_seen):
    """Group tracks into cohorts: consecutive first-seen ticks with gaps of 3 or less."""
    ticks = sorted(set(first_seen.values()))
    tick_to_c = {}
    starts = []
    c = -1
    prev = None
    for t in ticks:
        if prev is None or t - prev > 3:
            c += 1
            starts.append(t)
        tick_to_c[t] = c
        prev = t
    return {tid: tick_to_c[t] for tid, t in first_seen.items()}, starts


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
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    gun_range = float(rules.get("gun_range", 100.0))
    launch_cap = int(rules.get("interceptor_launches_per_tick", 2))

    # Per-track range and first-seen bookkeeping.
    rng = {}
    tmap = {}
    for t in tracks:
        tid = t["id"]
        tmap[tid] = t
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0.0, 0.0])
            r = math.hypot(p[0] - ax, p[1] - ay)
        rng[tid] = float(r)
        if tid not in _s["first_seen"]:
            _s["first_seen"][tid] = tick
            _s["last_new"] = tick
            if _s["first_any"] is None:
                _s["first_any"] = tick

    cmap, starts = _cohorts(_s["first_seen"])

    # The first cohort is the screen if a clearly separated later cohort follows it.
    screen = False
    if len(starts) >= 2 and starts[1] - starts[0] >= 6:
        n0 = sum(1 for v in cmap.values() if v == 0)
        if n0 >= 4:
            screen = True

    ready = (_s["first_any"] is not None and _s["last_new"] is not None
             and tick - _s["last_new"] >= 3 and tick - _s["first_any"] >= 15)

    def is_candidate(tid):
        t = tmap[tid]
        cls = t.get("cls", "unknown")
        if cls == "decoy":
            return False
        if cls == "striker":
            return True
        # Unknown track.
        if screen and cmap.get(tid) == 0:
            return False
        if screen and ready:
            return True
        return rng[tid] < 200.0  # fallback when no clear cohort pattern

    cands = [tid for tid in tmap if is_candidate(tid)]

    # Coverage from interceptors already in flight.
    covered = {}
    stale = []
    for it in inters:
        tg = it.get("target")
        if tg in tmap:
            covered[tg] = covered.get(tg, 0) + 1
        else:
            stale.append(it)
    # Drop pending entries once the interceptor shows up in flight, or after a timeout.
    pend = _s["pending"]
    for tid in list(pend.keys()):
        if tid in covered or tick - pend[tid] > 3 or tid not in tmap:
            pend.pop(tid, None)

    def is_cov(tid):
        return covered.get(tid, 0) > 0 or tid in pend

    # Retarget interceptors whose target has vanished.
    retarget = {}
    for it in stale:
        best = None
        bd = 1e18
        ip = it.get("pos", [ax, ay])
        for tid in cands:
            if is_cov(tid) or tid in retarget.values():
                continue
            p = tmap[tid].get("pos", [ax, ay])
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d < bd:
                bd = d
                best = tid
        if best is not None:
            retarget[it["id"]] = best
            covered[best] = covered.get(best, 0) + 1

    # Launch: always draw from the cohort with the most uncovered candidates.
    intercept = []
    avail = stock
    while avail > 0 and len(intercept) < launch_cap:
        unc = [tid for tid in cands if not is_cov(tid) and tid not in intercept]
        if not unc:
            break
        cnt = {}
        for tid in unc:
            c = cmap.get(tid, 0)
            cnt[c] = cnt.get(c, 0) + 1
        bestc = max(cnt.keys(), key=lambda c: (cnt[c], -c))
        pool = [tid for tid in unc if cmap.get(tid, 0) == bestc]
        pool.sort(key=lambda tid: (rng[tid], str(tid)))
        tid = pool[0]
        intercept.append(tid)
        pend[tid] = tick
        avail -= 1

    # Gun: prefer uncovered strikers, nearest first.
    gun = None
    if ammo > 0:
        inr = [tid for tid in tmap
               if rng[tid] <= gun_range and tmap[tid].get("cls") != "decoy"]
        if inr:
            inr.sort(key=lambda tid: (covered.get(tid, 0) > 0,
                                      0 if tmap[tid].get("cls") == "striker" else 1,
                                      rng[tid], str(tid)))
            gun = inr[0]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
