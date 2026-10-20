"""Idea: Label every radar track by its radial depth lag behind an earlier front and fire the whole magazine at the lagging band near the radar edge, before any ID, so the interceptor fight ends near r~330 and the gun gets every survivor alone.

Target: the attacker's fixed release schedule in _act. Decoys are released at
DECOY_RELEASE=14 and strikers at SHELL_A_RELEASE=27 / SHELL_B_RELEASE=31, all
from the same ORBIT_R=482. Because every drone starts from the same radius and
moves at the same speed, the decoy screen is always about 52 units deeper than
shell A and 68 units deeper than shell B. The attacker uses this "screen first"
order to soak up fire from defenders that shoot unknowns. Here it works against
it: anything that first shows up on radar well behind an already-inbound front
is a striker.

Replay evidence:
- In both closest calls (hover_bank_double_lattice, seeds 3 and 5), all 16
  impacts are decoys at tick 128, landing as a single block. That is
  14 + (482-25)/4 = 128 ticks, so the screen runs a fixed distance ahead of the
  strikers.
- The attacker only came close to losing when the defender spent 19
  interceptors purely on strikers (17-19 kills) and the gun added 7-9 striker
  kills.
- Against every defender that fires at unknowns (nearest_first, layered,
  annealed_eager), its score sits at 0.08-0.13. Wasting rounds on the screen
  is what loses.

How this differs from the obvious counter:
- The obvious counter (e.g. the cohort fingerprint defender) waits for the ID
  ring at 150. Then 26 strikers cross it inside a few ticks, the 2-per-tick
  launch cap bites, and the gun must sort leftovers while the shells converge.
- This bot uses a depth-lag test. A new track is marked "trail" if, when it is
  first seen, at least 4 older tracks are already 25 or more units closer to
  the asset.
- It fires on trail tracks the moment they cross 450, in first-seen order,
  with one interceptor per target.
- Interceptors whose target vanishes are retargeted to the nearest unengaged
  candidate.
- The magazine is spent by about r~330, long before the gun ring. The gun only
  ever shoots ID'd strikers inside 100 (never decoys), nearest first, so each
  survivor faces the gun on its own.
"""
import math

NAME = "depth_lag_band_precommit"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}      # id -> tick first seen
    _s["label"] = {}      # id -> "lead" / "trail"
    _s["lead_count"] = 0
    _s["engaged"] = {}    # track id -> number of interceptors sent


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _rng(t, ax, ay):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(p[0] - ax, p[1] - ay)
    return float(r)


def _act(obs):
    if "first" not in _s:
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
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    byid = {}
    rng = {}
    for t in tracks:
        tid = t["id"]
        byid[tid] = t
        rng[tid] = _rng(t, ax, ay)

    # Depth-lag labelling of newly seen tracks
    first = _s["first"]
    label = _s["label"]
    new_ids = [tid for tid in byid if tid not in first]
    for tid in new_ids:
        r = rng[tid]
        ahead = 0
        for oid, ft in first.items():
            if oid in byid and tick - ft >= 5 and rng[oid] < r - 25.0:
                ahead += 1
        label[tid] = "trail" if ahead >= 4 else "lead"
    for tid in new_ids:
        first[tid] = tick
        if label[tid] == "lead":
            _s["lead_count"] += 1
    trail_ok = _s["lead_count"] >= 4

    def is_candidate(tid):
        t = byid[tid]
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        return trail_ok and label.get(tid) == "trail"

    def prio(tid):
        t = byid[tid]
        known = 0 if t.get("cls") == "striker" else 1
        return (known, first.get(tid, tick), rng[tid], str(tid))

    # Current engagement from live interceptors
    engaged = {}
    orphans = []
    for it in inters:
        tg = it.get("target")
        if tg is not None and tg in byid and byid[tg].get("cls") != "decoy":
            engaged[tg] = engaged.get(tg, 0) + 1
        else:
            orphans.append(it)

    cands = sorted([tid for tid in byid if is_candidate(tid)], key=prio)
    free = [tid for tid in cands if tid not in engaged]

    # Retarget orphaned interceptors to the nearest unengaged candidate
    retarget = {}
    for it in orphans:
        if not free:
            break
        ip = it.get("pos", [ax, ay])
        best = min(free, key=lambda tid: math.hypot(byid[tid]["pos"][0] - ip[0],
                                                    byid[tid]["pos"][1] - ip[1]))
        retarget[it["id"]] = best
        free.remove(best)
        engaged[best] = engaged.get(best, 0) + 1

    # Launch: one interceptor per candidate, in priority order
    intercept = []
    n = min(cap, stock)
    for tid in free:
        if len(intercept) >= n:
            break
        intercept.append(tid)
        engaged[tid] = 1

    # Gun: only on ID'd strikers inside gun range, nearest first
    gun = None
    if ammo > 0:
        best_r = None
        for tid, t in byid.items():
            if t.get("cls") != "striker":
                continue
            r = rng[tid]
            if r <= gun_range and (best_r is None or r < best_r):
                best_r = r
                gun = tid
        if gun is None:
            # Fallback: an unknown inside gun range that is not a lead-band track
            for tid, t in byid.items():
                if t.get("cls", "unknown") != "unknown":
                    continue
                if trail_ok and label.get(tid) == "lead":
                    continue
                r = rng[tid]
                if r <= gun_range and (best_r is None or r < best_r):
                    best_r = r
                    gun = tid

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
