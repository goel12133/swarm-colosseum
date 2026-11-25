"""Idea: Classify every drone by its radar-entry cohort at 450 units, so the first burst is written off as the decoy screen and all 20 interceptors go to strikers the moment they cross the radar edge, with no wait for ID.

Target: the fixed release schedule in hidden_orbit_screen_then_interleaved_drop.
- DECOY_RELEASE=14 and SHELL_A/B_RELEASE=27/31. Everything orbits at r~482 and then
  drops radially at speed 4.
- So all 16 decoys cross the 450 radar edge together around tick 22.
- The 26 strikers cross about 13 ticks later, in two bursts 4 ticks apart.
- That gap gives away every drone's type at 450, long before the 150 ID ring.
- Its main weapon is cramming all strikers through the ID ring together against a
  2-per-tick launch cap. That does nothing to a defender that never waits for ID.

What the replays show:
- In its two closest calls (hover_bank_double_lattice), all 16 decoys reached the
  asset unengaged at tick 128.
- Every interceptor went to a striker (17-19 interceptor kills), and the gun cleaned
  up the remaining 7-9 strikers.
- When the magazine goes only to strikers, the swarm fails. Defenders that fire at
  unknowns (nearest_first 0.08, layered 0.10) or that wait for ID lose.

This bot:
- Hold fire until a second, later cohort exists, then engage it at the radar edge.
  Early launches give the full engagement depth.
- Fire 2 per tick, nearest uncovered first, one interceptor per distinct striker.
- Retarget an interceptor if its target vanishes or is revealed as a decoy.
- Fire the gun every tick at the nearest striker in range, and never at a decoy.
- Fallback for other attackers: anything the ID ring reveals as a striker is engaged.
"""
import math

NAME = "radar_entry_cohort_screen_writeoff"
ROLE = "defender"

COHORT_GAP = 6

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cls"] = {}
    _s["pending"] = {}


def _cohorts():
    ticks = sorted(set(_s["first"].values()))
    if not ticks:
        return None, False
    first_end = ticks[0]
    second = False
    for t in ticks[1:]:
        if t - first_end > COHORT_GAP:
            second = True
            break
        first_end = t
    return first_end, second


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))

    info = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        if tid not in _s["first"]:
            _s["first"][tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            _s["cls"][tid] = c
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(float(p[0]) - ax, float(p[1]) - ay)
        info[tid] = r

    first_end, second = _cohorts()

    def is_striker(tid):
        c = _s["cls"].get(tid)
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if first_end is None:
            return False
        if _s["first"].get(tid, 0) <= first_end:
            # First cohort: the screen. Wait for ID.
            return False
        # A later cohort is the strike wave.
        return True

    cands = [tid for tid in info if is_striker(tid)]

    # Coverage counts
    covered = {}
    for it in inters:
        tg = it.get("target")
        if tg is not None:
            covered[tg] = covered.get(tg, 0) + 1
    pend = _s["pending"]
    for tid in list(pend.keys()):
        if tick - pend[tid] > 2 or covered.get(tid, 0) > 0:
            del pend[tid]
    for tid in pend:
        covered[tid] = covered.get(tid, 0) + 1

    # Retarget interceptors with lost or decoy targets
    retarget = {}
    free = sorted([tid for tid in cands if covered.get(tid, 0) == 0],
                  key=lambda x: info[x])
    for it in inters:
        iid = it.get("id")
        tg = it.get("target")
        bad = (tg not in info) or (_s["cls"].get(tg) == "decoy")
        if bad and free:
            ip = it.get("pos", [ax, ay])
            best = min(free, key=lambda x: info[x])
            try:
                # Choose the free striker nearest the interceptor.
                best = None
                bd = 1e18
                for x in free:
                    tt = next(t for t in tracks if t.get("id") == x)
                    d = math.hypot(tt["pos"][0] - ip[0], tt["pos"][1] - ip[1])
                    if d < bd:
                        bd = d
                        best = x
            except Exception:
                pass
            if best is not None:
                retarget[iid] = best
                free.remove(best)
                covered[best] = covered.get(best, 0) + 1

    # Launches
    intercept = []
    n = min(cap, stock)
    for tid in free:
        if len(intercept) >= n:
            break
        if covered.get(tid, 0) > 0:
            continue
        intercept.append(tid)
        pend[tid] = tick

    # Gun
    gun = None
    if ammo > 0:
        best = None
        br = 1e18
        for tid, r in info.items():
            if r > gun_range:
                continue
            c = _s["cls"].get(tid)
            if c == "decoy":
                continue
            if c != "striker" and not is_striker(tid):
                # Unknown inside the gun range: shoot it anyway (cheap).
                if c is not None:
                    continue
            if r < br:
                br = r
                best = tid
        gun = best

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
