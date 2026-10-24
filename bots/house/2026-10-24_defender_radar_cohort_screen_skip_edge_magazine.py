"""Idea: Classify every track by the radar-entry cohort it arrives in, so the first cohort is treated as decoys and is never shot, and the later cohort is engaged as strikers at the radar edge, about 300 units before the ID ring.

Target: the fixed launch queue and release schedule of hidden_orbit_screen_then_interleaved_drop.
- The bot always builds the queue as 16 decoys followed by 26 strikers.
- It releases decoys at tick 14 and the striker shells at ticks 27 and 31.
- So the whole decoy screen crosses the 450 radar edge about 13 ticks (about 52 units)
  before any striker.
- The cohort that appears first is therefore the screen, and everything that appears
  roughly 10 or more ticks later is a striker.
- The docstring of that bot assumes the defender either fires at unknowns and wastes
  rounds on the screen, or waits for ID at 150 and gets squeezed by the 2-per-tick
  launch cap. This bot does neither.

What the replays show:
- In its closest losses (hover_bank_double_lattice, seeds 3 and 5), all 16 decoys
  impact together at tick 128 and the asset still has 30 hp. The screen does no damage.
- The defender held only when nearly the full magazine went into strikers: 17-19
  interceptor kills from 19 launches, with the gun cleaning up 7-9.
- That bot still scored about 0.34 mean there, so the margin is thin. The limit is
  how many strikers leak past the interceptors.

What this bot does differently:
- It never spends interceptors or gun rounds on the first cohort.
- It launches the whole magazine at strikers as soon as they cross the radar edge,
  2 per tick. Misses then resolve near r~330, so any freed or missed round is re-tasked
  long before the gun fight.
- It saves all gun shots for strikers, firing nearest-to-impact first.

Robustness:
- A revealed class always overrides the cohort guess.
- If any first-cohort track is revealed as a striker, the cohort presumption is dropped.
"""
import math

NAME = "radar_cohort_screen_skip_edge_magazine"
ROLE = "defender"

COHORT_GAP = 6

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["t_first"] = None
    _s["cohort_valid"] = True
    _s["recent"] = {}
    _s["known"] = {}


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
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))

    fs = _s["first_seen"]
    known = _s["known"]
    for t in tracks:
        tid = t["id"]
        if tid not in fs:
            fs[tid] = tick
            if _s["t_first"] is None:
                _s["t_first"] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            known[tid] = c

    t_first = _s["t_first"]

    def in_first_cohort(tid):
        return t_first is not None and fs.get(tid, 10**9) <= t_first + COHORT_GAP

    # If a first-cohort track turns out to be a striker, drop the presumption.
    if _s["cohort_valid"]:
        for tid, c in known.items():
            if c == "striker" and in_first_cohort(tid):
                _s["cohort_valid"] = False
                break

    def is_striker(tid):
        c = known.get(tid)
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if _s["cohort_valid"] and in_first_cohort(tid):
            return False
        return True

    live = {t["id"]: t for t in tracks}
    strikers = [t for t in tracks if is_striker(t["id"])]

    # engagement bookkeeping
    engaged = {}
    for it in inters:
        tg = it.get("target")
        if tg is not None:
            engaged[tg] = engaged.get(tg, 0) + 1
    rec = _s["recent"]
    for tid in list(rec.keys()):
        if tick - rec[tid] > 3 or tid not in live:
            del rec[tid]
        elif tid not in engaged:
            engaged[tid] = engaged.get(tid, 0) + 1

    def unengaged():
        return [t for t in strikers if engaged.get(t["id"], 0) == 0]

    # retarget interceptors whose target is gone or is a decoy
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg in live and is_striker(tg):
            continue
        cands = unengaged()
        if not cands:
            continue
        ip = it.get("pos", [0.0, 0.0])
        best = min(cands, key=lambda t: math.hypot(t["pos"][0] - ip[0],
                                                   t["pos"][1] - ip[1]))
        retarget[it["id"]] = best["id"]
        engaged[best["id"]] = engaged.get(best["id"], 0) + 1
        if tg in engaged:
            engaged[tg] -= 1

    # launch at unengaged strikers, nearest first
    intercept = []
    if stock > 0:
        cands = sorted(unengaged(), key=lambda t: t.get("range", 1e9))
        for t in cands:
            if len(intercept) >= min(cap, stock):
                break
            intercept.append(t["id"])
            rec[t["id"]] = tick
            engaged[t["id"]] = 1

    # gun: strikers only, nearest to impact first
    gun = None
    if ammo > 0:
        inr = [t for t in strikers if t.get("range", 1e9) <= gun_range]
        if inr:
            # prefer targets without an interceptor about to arrive
            def imminent(tid):
                tp = live[tid]["pos"]
                for it in inters:
                    if it.get("target") == tid:
                        ip = it.get("pos", [1e9, 1e9])
                        if math.hypot(tp[0] - ip[0], tp[1] - ip[1]) < 20.0:
                            return True
                return False
            free = [t for t in inr if not imminent(t["id"])]
            pool = free if free else inr
            gun = min(pool, key=lambda t: t.get("range", 1e9))["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
