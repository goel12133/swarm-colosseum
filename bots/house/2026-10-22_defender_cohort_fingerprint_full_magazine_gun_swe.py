"""Idea: Label every radar track by its arrival cohort, so the first wave that crosses the radar edge alone is treated as bait. Then fire all 20 interceptors at the later wave from 450 units out, one per striker, and gun the leakers nearest first.

What I attack: the fixed release schedule in hidden_orbit_screen_then_interleaved_drop.
DECOY_RELEASE=14, SHELL_A_RELEASE=27 and SHELL_B_RELEASE=31 are constants, and
every drone leaves the same r~482 orbit and flies radially. So all 16 decoys cross
the 450 radar ring together around tick 22. No striker can show up until about
tick 35, and the two striker shells arrive within about 4 ticks of each other.
The decoy screen is meant to make defenders who fire at unknowns waste their
magazine before the 150 ID ring. Its arrival-time fingerprint gives it away about
75 ticks before any ID happens.

What the replays show:
- In both of its closest calls every decoy impact is logged at tick 128 in a
  single tick. That is one cohort, released together and arriving together.
- Defenders that shoot at unknowns score worst against it: nearest_first 0.08,
  layered 0.10, annealed_eager 0.09.
- The only defender that beat it (hover_bank_double_lattice) did so by sending
  19 interceptors at strikers only, for 17 interceptor kills plus 9 gun kills.
  It still left one interceptor unused. The blast-proof spacing means no blast
  ever kills two drones, so the outcome turns on two things: never wasting a
  round, and the gun.

What this bot does:
- Groups tracks into cohorts by first-seen tick, splitting on a gap of more than 6 ticks.
- If the first cohort has no IDs yet and a later cohort exists, the first cohort
  is presumed decoy. Every later cohort is presumed striker. Real IDs override
  this, and a cohort flips class if any of its members is ID'd the other way.
- Fires all 20 interceptors at presumed strikers as soon as they appear, nearest
  first, 2 per tick. Interceptors whose target dies or turns out to be a decoy are
  retargeted to the nearest striker no interceptor is chasing.
- Gun: each tick, shoots the closest striker in range. It skips strikers that an
  interceptor is about to hit. Asset hp 30 against 10 damage means 2 leakers are
  survivable, so 24 kills out of 26 is enough.
"""
import math

NAME = "cohort_fingerprint_full_magazine_gun_sweep"
ROLE = "defender"

COHORT_GAP = 6
SOLO_COHORT_COMMIT_RANGE = 260.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["known"] = {}
    _s["pending"] = {}


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
    ints = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    fs = _s["first_seen"]
    known = _s["known"]
    live = {}
    for t in tracks:
        tid = t["id"]
        live[tid] = t
        if tid not in fs:
            fs[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            known[tid] = c

    # Group tracks into cohorts by first-seen tick.
    times = sorted(set(fs.values()))
    cohort_of_time = {}
    ci = -1
    prev = None
    for tm in times:
        if prev is None or tm - prev > COHORT_GAP:
            ci += 1
        cohort_of_time[tm] = ci
        prev = tm
    n_cohorts = ci + 1
    cstats = {}
    for tid, tm in fs.items():
        c = cohort_of_time[tm]
        st = cstats.setdefault(c, [0, 0])
        k = known.get(tid)
        if k == "striker":
            st[0] += 1
        elif k == "decoy":
            st[1] += 1

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t["pos"]
            r = math.hypot(p[0] - ax, p[1] - ay)
        return float(r)

    def presumed(tid):
        k = known.get(tid)
        if k:
            return k
        c = cohort_of_time.get(fs.get(tid, tick), 0)
        ns, nd = cstats.get(c, [0, 0])
        if ns > 0 and nd == 0:
            return "striker"
        if nd > 0 and ns == 0:
            return "decoy"
        if ns > 0 and nd > 0:
            return "striker"
        if c == 0:
            if n_cohorts > 1:
                return "decoy"
            t = live.get(tid)
            if t is not None and rng(t) < SOLO_COHORT_COMMIT_RANGE:
                return "striker"
            return "hold"
        return "striker"

    pres = {tid: presumed(tid) for tid in live}

    # Forget pending launches older than 2 ticks.
    pend = _s["pending"]
    for tid in list(pend.keys()):
        if tick - pend[tid] > 2 or tid not in live:
            del pend[tid]

    targeted = set(pend.keys())
    for i in ints:
        tg = i.get("target")
        if tg in live and pres.get(tg) == "striker":
            targeted.add(tg)

    # Retarget interceptors whose target is gone or is a decoy.
    retarget = {}
    for i in ints:
        tg = i.get("target")
        if tg in live and pres.get(tg) == "striker":
            continue
        ip = i.get("pos", [ax, ay]) or [ax, ay]
        best = None
        bd = 1e18
        for tid, t in live.items():
            if pres[tid] != "striker" or tid in targeted:
                continue
            p = t["pos"]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d < bd:
                bd = d
                best = tid
        if best is not None:
            retarget[i["id"]] = best
            targeted.add(best)

    # Launch interceptors at untargeted presumed strikers, nearest first.
    cands = [t for tid, t in live.items()
             if pres[tid] == "striker" and tid not in targeted]
    cands.sort(key=rng)
    intercept = []
    for t in cands:
        if len(intercept) >= min(cap, stock):
            break
        intercept.append(t["id"])
        pend[t["id"]] = tick

    # Gun: shoot the closest striker in range that no interceptor is about to hit.
    gun = None
    if ammo > 0:
        ipos = [(i.get("target"), i.get("pos")) for i in ints if i.get("pos")]
        primary = []
        backup = []
        for tid, t in live.items():
            r = rng(t)
            if r > gun_range:
                continue
            c = pres[tid]
            if c == "decoy":
                continue
            if c == "hold" and known.get(tid) != "striker":
                pass
            p = t["pos"]
            covered = False
            for tg, q in ipos:
                if tg == tid and math.hypot(q[0] - p[0], q[1] - p[1]) < 20.0:
                    covered = True
                    break
            (backup if covered else primary).append((r, tid))
        pool = primary or backup
        if pool:
            pool.sort()
            gun = pool[0][1]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
