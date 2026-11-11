"""Idea: Label the hidden-orbit swarm by birth cohort, so the first burst on radar is treated as decoys and later bursts as strikers. Fire 16 interceptors at the strikers as soon as they cross 450, before ID, and keep 4 as a deadline reserve for leakers the gun cannot finish.

What I attack in hidden_orbit_screen_then_interleaved_drop:
- Its release schedule is fixed: decoys at tick 14, then shells at ticks 27 and 31.
  Every drone leaves the same r~482 orbit, so the 16-decoy screen always crosses the
  450 radar edge about 13 ticks before any striker. The bot relies on defenders being
  blind to type until 150, but arrival time already tells the cohorts apart.
  Firing on a track that appears first and alone is exactly what its screen punishes.
  Firing on the cohort that shows up 13 ticks later is safe.
- Its docstring argues that strikers reaching the 150 ID ring together squeeze the
  ID-then-engage window. My plan does not use that window. Interceptors launch at
  2 per tick from about tick 35, with targets at r~450. Every engagement is decided
  far outside gun range, so the gun only meets confirmed survivors.
- The replays show where it breaks. In both close calls against
  hover_bank_double_lattice, all 16 decoys hit at tick 128 and drew no fire. Every
  striker died: 17-19 to interceptors and 7-9 to the gun, from only 22 shots with
  98 ammo left. The gun is limited by shot-ticks, not ammo. My gun always shoots
  the closest striker with no interceptor inbound, so no shot is spent on a target
  already covered.
- Its interleaved blast-proof spacing only blocks double kills. I never plan on
  double kills. The 4 reserve interceptors launch at strikers that get within 70 of
  the asset with no interceptor assigned. When several leakers arrive together, the
  2-per-tick launch cap handles more of them than the single gun shot per tick can.
  Reserve rounds that are not needed stay unspent, which helps CER.
- Fallback: any track with a revealed class overrides the cohort guess. If there is
  only one cohort, it waits for ID, like an identify-then-engage defender.
"""
import math

NAME = "birth_cohort_prefire_deadline_reserve"
ROLE = "defender"

RESERVE = 4
COHORT_GAP = 6
RES_RANGE = 70.0
GUN_HANDOFF = 45.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cls"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = obs.get("tick", 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    ics = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))

    fs = _s["first_seen"]
    known = _s["cls"]
    tinfo = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        p = t.get("pos", [0.0, 0.0])
        px, py = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(px, py)
        tinfo[tid] = (px, py, r)
        if tid not in fs:
            fs[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            known[tid] = c

    # birth cohorts
    order = sorted(fs.items(), key=lambda kv: kv[1])
    cohort_of = {}
    ci = 0
    prev = None
    for tid, ft in order:
        if prev is not None and ft - prev > COHORT_GAP:
            ci += 1
        cohort_of[tid] = ci
        prev = ft
    ncoh = ci + 1
    stats = {}
    for tid, c in known.items():
        k = cohort_of.get(tid)
        if k is None:
            continue
        st = stats.setdefault(k, [0, 0])
        if c == "striker":
            st[0] += 1
        else:
            st[1] += 1

    def cohort_striker(k):
        st = stats.get(k)
        if st and st[0] != st[1]:
            return st[0] > st[1]
        if ncoh < 2:
            return False
        return k >= 1

    def is_striker(tid):
        c = known.get(tid)
        if c == "striker":
            return True
        if c == "decoy":
            return False
        k = cohort_of.get(tid)
        if k is None:
            return False
        return cohort_striker(k)

    strikers = [tid for tid in tinfo if is_striker(tid)]
    sset = set(strikers)

    # interceptor assignments and retargeting
    assigned = {}
    retarget = {}
    free_ics = []
    for ic in ics:
        tg = ic.get("target")
        if tg in sset:
            assigned[tg] = assigned.get(tg, 0) + 1
        else:
            free_ics.append(ic)
    for ic in free_ics:
        ip = ic.get("pos", [ax, ay]) or [ax, ay]
        ix, iy = float(ip[0]) - ax, float(ip[1]) - ay
        best = None
        bd = 1e18
        for tid in strikers:
            if assigned.get(tid, 0) > 0:
                continue
            px, py, r = tinfo[tid]
            d = math.hypot(px - ix, py - iy)
            if d < bd:
                bd = d
                best = tid
        if best is not None:
            retarget[ic.get("id")] = best
            assigned[best] = 1

    uncovered = sorted([tid for tid in strikers if assigned.get(tid, 0) == 0],
                       key=lambda tid: tinfo[tid][2])

    launch = []
    left = stock
    # early phase: pre-ID engagement of presumed strikers
    for tid in uncovered:
        if len(launch) >= cap or left <= RESERVE:
            break
        launch.append(tid)
        assigned[tid] = 1
        left -= 1

    # deadline reserve
    uncovered = [tid for tid in uncovered if assigned.get(tid, 0) == 0]
    gun_pref = None
    for tid in uncovered:
        if tinfo[tid][2] <= gun_range:
            gun_pref = tid
            break
    for tid in uncovered:
        if len(launch) >= cap or left <= 0:
            break
        r = tinfo[tid][2]
        if r >= RES_RANGE:
            break
        if tid == gun_pref and r > GUN_HANDOFF:
            continue
        launch.append(tid)
        assigned[tid] = 1
        left -= 1

    # gun: closest uncovered striker, else closest striker
    gun = None
    if ammo > 0:
        inr = sorted([tid for tid in strikers if tinfo[tid][2] <= gun_range],
                     key=lambda tid: tinfo[tid][2])
        for tid in inr:
            if assigned.get(tid, 0) == 0:
                gun = tid
                break
        if gun is None and inr:
            gun = inr[0]

    return {"intercept": launch, "retarget": retarget, "gun": gun}
