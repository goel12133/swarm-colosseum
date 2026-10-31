"""Idea: Ignore the first radar cohort, which arrives alone with a quiet gap behind it, as a presumed decoy screen. Spend every interceptor one-for-one on the later striker cohorts, balancing them across the two shells, and keep the gun on identified strikers only.

What we attack: the release schedule in hidden_orbit_screen_then_interleaved_drop.
DECOY_RELEASE=14, SHELL_A_RELEASE=27 and SHELL_B_RELEASE=31 are fixed, and every
drone leaves the same r~482 orbit. So all 16 decoys cross the 450 radar edge on
the same tick, about 13 ticks before any striker. Shell A crosses as one block,
and shell B follows 4 ticks later. The bot hides type until 150, but its
first-seen ticks give type away: the first cohort, with a gap behind it, is the
screen. We never fire at it.

What the replays show: in its closest calls (hover_bank_double_lattice, seeds 3
and 5), the 16 decoys all impact together at tick 128. That one tick is the
signature of a single synchronized screen. The defender killed all 26 strikers
with 17-19 interceptors and 7-9 gun kills, but it kept one interceptor unused.
Defenders that fire on unknowns (nearest_first 0.08, layered 0.10,
annealed_eager 0.09) lose because the screen drains their magazine. So the
match turns on two things: no interceptor spent on decoys, and no round left
in the magazine.

How we answer:
- Cohort gate. Tracks first seen within 3 ticks of first contact count as
  presumed decoys once a later cohort (6+ ticks after) appears. If no later
  cohort ever shows up, they are engaged inside r<280 as a fallback.
  Revealed class always overrides the guess.
- No overkill, full magazine. Each interceptor gets one live striker. The
  last 4 interceptors are held until the first salvo resolves. Then they go to
  whichever shell has more unengaged survivors. This leaves the gun survivors
  split across both shells' arrival times, which gives the gun the widest
  shooting window.
- Gun. It fires only at identified strikers, nearest first. It prefers ones
  with no interceptor inbound and never shoots the decoys arriving at tick 128.
"""
import math

NAME = "first_cohort_screen_skip_balanced_magazine"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cls"] = {}
    _s["fc"] = None
    _s["launched"] = 0
    _s["tick"] = 0


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = int(obs.get("tick", _s["tick"] + 1))
    _s["tick"] = tick
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    fs = _s["first_seen"]
    tmap = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        tmap[tid] = t
        if tid not in fs:
            fs[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            _s["cls"][tid] = c
        if _s["fc"] is None:
            _s["fc"] = tick
    fc = _s["fc"]

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0.0, 0.0])
            r = math.hypot(p[0], p[1])
        return float(r)

    later_wave = False
    if fc is not None:
        for v in fs.values():
            if v >= fc + 6:
                later_wave = True
                break

    def is_threat(tid):
        t = tmap.get(tid)
        if t is None:
            return False
        c = _s["cls"].get(tid, "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if fc is not None and fs.get(tid, 0) <= fc + 3:
            if later_wave:
                return False
            return rng(t) < 280.0
        return True

    # cohort index from first-seen ticks (gap > 2 ticks starts a new cohort)
    ticks_sorted = sorted(set(fs.values()))
    cohort_of_tick = {}
    ci = -1
    prev = None
    for tk in ticks_sorted:
        if prev is None or tk - prev > 2:
            ci += 1
        cohort_of_tick[tk] = ci
        prev = tk

    # interceptor bookkeeping
    engaged = {}
    retarget = {}
    in_flight = 0
    for it in inters:
        iid = it.get("id")
        tgt = it.get("target")
        in_flight += 1
        if tgt is not None and tgt in tmap and is_threat(tgt):
            engaged[tgt] = engaged.get(tgt, 0) + 1
        else:
            retarget[iid] = None  # to be filled

    threats = [tid for tid in tmap if is_threat(tid)]
    unengaged = [tid for tid in threats if engaged.get(tid, 0) == 0]

    def pick(cands):
        if not cands:
            return None
        counts = {}
        for tid in cands:
            c = cohort_of_tick.get(fs.get(tid, 0), 0)
            counts[c] = counts.get(c, 0) + 1
        best_c = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        pool = [tid for tid in cands
                if cohort_of_tick.get(fs.get(tid, 0), 0) == best_c]
        pool.sort(key=lambda tid: (rng(tmap[tid]), str(tid)))
        return pool[0]

    # fill retargets for interceptors with dead or decoy targets
    final_retarget = {}
    for iid in list(retarget.keys()):
        cands = [tid for tid in unengaged if rng(tmap[tid]) > 15.0]
        tid = pick(cands)
        if tid is None:
            continue
        final_retarget[iid] = tid
        engaged[tid] = engaged.get(tid, 0) + 1
        unengaged.remove(tid)

    # launches with a balancing holdback
    intercept = []
    min_r = min([rng(tmap[t]) for t in threats], default=1e9)
    reserve = 4
    release = (_s["launched"] >= 16 and in_flight == 0) or min_r < 230.0
    avail = stock if release else max(0, stock - reserve)
    n = min(cap, avail)
    for _ in range(n):
        cands = [tid for tid in unengaged if rng(tmap[tid]) > 30.0]
        tid = pick(cands)
        if tid is None:
            break
        intercept.append(tid)
        engaged[tid] = 1
        unengaged.remove(tid)
        _s["launched"] += 1

    # gun: identified/credible strikers in range, nearest first, prefer uncovered
    gun = None
    if ammo > 0:
        inr = [tid for tid in threats if rng(tmap[tid]) <= gun_range]
        if inr:
            inr.sort(key=lambda tid: (engaged.get(tid, 0) > 0,
                                      rng(tmap[tid]), str(tid)))
            gun = inr[0]

    return {"intercept": intercept, "retarget": final_retarget, "gun": gun}
