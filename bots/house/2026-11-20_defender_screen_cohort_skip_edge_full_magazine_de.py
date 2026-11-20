"""Idea: Fingerprint the decoy screen by its single radar-entry tick, then fire the whole magazine at the second (striker) cohort from the radar edge, long before ID, and finish with a nearest-deadline gun.

Target: 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_drop.

Which part of its logic this attacks:
- Its staging is fully scripted. All 16 decoys leave the hidden orbit together at
  DECOY_RELEASE=14. The 26 strikers leave at ticks 27 and 31. So the decoys cross
  the 450 radar ring in one tick, about 13 ticks before any striker shows up.
- The replays show this. In every close call, all 16 decoy impacts land on tick 128
  exactly. That means the screen moves as one rigid cohort. It also arrives as a
  group: no striker is first seen within a few ticks of the decoys.
- The bot's own docstring says it wins by squeezing the "ID-then-engage window".
  Strikers reach the 150 ID ring within about 4 ticks of each other, and the defender
  is capped at 2 launches per tick.
- So we do not wait for ID. The first cohort is treated as bait and never engaged
  unless it is IDed as a striker. Every track first seen at least 6 ticks later is
  treated as a striker.
- Interceptors go out at 2 per tick from about r=440. That gives 10 or more ticks of
  launches, not the 2 or 3 left at the ID ring. Each striker gets exactly one
  interceptor (no doubling), and interceptors whose target is gone are retargeted.
- The close calls were won with 17 interceptor kills plus 9 gun kills, and only 19
  interceptors were launched. That was a defender holding for ID. Spending all 20,
  early, on strikers only is the margin we take.
- Its blast-proof interleave is not contested. One interceptor per striker never
  needs a double kill.
- The gun shoots the closest striker that no interceptor is assigned to. Leakers are
  shot in deadline order, and gun shots go to strikers no interceptor is already
  covering.
"""
import math

NAME = "screen_cohort_skip_edge_full_magazine_deadline_gun"
ROLE = "defender"

COHORT_GAP = 6

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["first_range"] = {}
    _s["t0"] = None
    _s["cohort1"] = set()
    _s["cohort2"] = set()
    _s["flip"] = False


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
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    gun_range = float(rules.get("gun_range", 100.0))
    radar = float(rules.get("radar_range", 450.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    info = {}
    for t in tracks:
        tid = t["id"]
        px, py = float(t["pos"][0]) - ax, float(t["pos"][1]) - ay
        r = math.hypot(px, py)
        info[tid] = (t, r, px, py)

    # cohort bookkeeping
    fs = _s["first_seen"]
    c1, c2 = _s["cohort1"], _s["cohort2"]
    for tid, (t, r, px, py) in info.items():
        if tid in fs:
            continue
        fs[tid] = tick
        _s["first_range"][tid] = r
        if _s["t0"] is None:
            _s["t0"] = tick
        if tick <= _s["t0"] + COHORT_GAP:
            c1.add(tid)
        elif r >= radar - 40.0:
            c2.add(tid)
        else:
            # re-acquired track deep inside radar: match by range band
            live1 = [info[x][1] for x in c1 if x in info]
            live2 = [info[x][1] for x in c2 if x in info]
            d1 = min([abs(r - v) for v in live1], default=1e9)
            d2 = min([abs(r - v) for v in live2], default=1e9)
            if d1 < d2:
                c1.add(tid)
            else:
                c2.add(tid)

    # if the first cohort turns out to be strikers, stop skipping it
    for tid in c1:
        if tid in info and info[tid][0].get("cls") == "striker":
            _s["flip"] = True

    def is_striker(tid):
        t = info[tid][0]
        cls = t.get("cls", "unknown")
        if cls == "striker":
            return True
        if cls == "decoy":
            return False
        if tid in c1:
            return _s["flip"]
        if tid in c2:
            return True
        return False

    strikers = [tid for tid in info if is_striker(tid)]

    # current assignment
    assigned = {}
    retarget = {}
    orphans = []
    for it in inters:
        tg = it.get("target")
        if tg in info and is_striker(tg) and assigned.get(tg, 0) == 0:
            assigned[tg] = 1
        else:
            orphans.append(it)

    def unassigned_sorted():
        u = [tid for tid in strikers if assigned.get(tid, 0) == 0]
        u.sort(key=lambda x: info[x][1])
        return u

    # retarget orphaned interceptors to nearest unassigned striker
    for it in orphans:
        u = unassigned_sorted()
        if not u:
            break
        ipos = it.get("pos", [ax, ay]) or [ax, ay]
        best = min(u, key=lambda x: math.hypot(info[x][0]["pos"][0] - ipos[0],
                                                info[x][0]["pos"][1] - ipos[1]))
        retarget[it["id"]] = best
        assigned[best] = 1

    # launch: one interceptor per striker, most urgent first
    intercept = []
    if stock > 0:
        for tid in unassigned_sorted():
            if len(intercept) >= min(cap, stock):
                break
            intercept.append(tid)
            assigned[tid] = 1

    # gun: nearest striker in range, preferring ones no interceptor covers
    gun = None
    if ammo > 0:
        inrange = [tid for tid in strikers if info[tid][1] <= gun_range + 3.0]
        if inrange:
            free = [tid for tid in inrange if assigned.get(tid, 0) == 0
                    or tid in intercept]
            pool = free if free else inrange
            gun = min(pool, key=lambda x: info[x][1])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
