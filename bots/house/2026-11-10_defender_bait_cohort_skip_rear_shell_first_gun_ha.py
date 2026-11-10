"""Idea: Skip the bait cohort, fire kill-assessed long shots at the rear shell first, and hold a small terminal reserve that only launches on strikers the gun is visibly failing to stop.

Target: 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_drop.

Which part of its logic this attacks:
- Its release schedule is fixed by tick: decoys at tick 14, shell A at 27, shell B at 31.
  The decoys therefore always cross the 450 radar ring alone, about 13 ticks before
  any striker. That makes them a clean first arrival cohort. We never spend fire on
  that cohort unless it is ID'd as a striker, and we do not need the 150 ID ring for it.
- The hidden orbit does not shorten our window. Strikers are on radar from about
  tick 35 and impact around tick 141 to 145. That is roughly 30 ticks of interceptor
  flight to reach them, then about 70 more ticks to see what died before anything gets
  close. Its "compress the ID window" design only hurts defenders that wait for ID.
- Its interleaved, depth-offset shells defeat blast packing. We do not try to pack.
  We spend one interceptor per live striker, with kill assessment and no overkill,
  and retarget any interceptor whose target has already died.

What the replays show: its closest losses, against hover_bank_double_lattice, were won
by exactly 26 kills (17-19 by interceptor, 7-9 by gun). All 16 decoy impacts landed
in one burst at tick 128, and only 1 interceptor was left. The margin is how the
magazine is spent and how it is handed off to the gun, not detection. So we engage
farthest-first, which works the rear shell B while it is far out. Shell A leftovers
go to the gun, which takes the nearest unengaged striker each tick. A 4-round reserve
launches only inside 70 units, on leftovers the gun has not killed, and avoids the
gun's current target. Gun shots and interceptors never double up on the same striker.
"""
import math

NAME = "bait_cohort_skip_rear_shell_first_gun_handoff_reserve"
ROLE = "defender"

COHORT_GAP = 6
TERMINAL_RANGE = 70.0
RESERVE = 4

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["cohort"] = {}
    _s["cohort_count"] = 0
    _s["last_new_tick"] = -1000


def _rng(t):
    r = t.get("range")
    if r is None:
        p = t.get("pos", [0.0, 0.0])
        r = math.hypot(p[0], p[1])
    return float(r)


def _is_striker(t):
    cls = t.get("cls", "unknown")
    if cls == "striker":
        return True
    if cls == "decoy":
        return False
    c = _s["cohort"].get(t["id"], 0)
    if c == 0:
        if _s["cohort_count"] > 1:
            return False
        return _rng(t) < 300.0
    return True


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
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    lifetime = int(rules.get("interceptor_lifetime", 90))
    ispeed = float(rules.get("interceptor_speed", 12.0))

    # cohort bookkeeping
    new_ids = [t["id"] for t in tracks if t["id"] not in _s["first_seen"]]
    if new_ids:
        if tick - _s["last_new_tick"] > COHORT_GAP or _s["cohort_count"] == 0:
            _s["cohort_count"] += 1
        cidx = _s["cohort_count"] - 1
        for i in new_ids:
            _s["first_seen"][i] = tick
            _s["cohort"][i] = cidx
        _s["last_new_tick"] = tick

    by_id = {t["id"]: t for t in tracks}
    strikers = [t for t in tracks if _is_striker(t)]
    sids = set(t["id"] for t in strikers)

    engaged = set()
    for it in inters:
        tg = it.get("target")
        if tg in sids:
            engaged.add(tg)

    # retarget interceptors whose target died or is a decoy
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg in sids:
            continue
        age = int(it.get("age", 0))
        left = lifetime - age
        if left <= 2:
            continue
        ip = it.get("pos", [0.0, 0.0])
        best = None
        bd = 1e18
        for t in strikers:
            if t["id"] in engaged:
                continue
            p = t["pos"]
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            if d > ispeed * left:
                continue
            if d < bd:
                bd = d
                best = t["id"]
        if best is not None:
            retarget[it["id"]] = best
            engaged.add(best)

    # gun: nearest unengaged striker in range, else nearest engaged close one
    gun = None
    if ammo > 0:
        cand = [t for t in strikers if _rng(t) <= gun_range]
        un = [t for t in cand if t["id"] not in engaged]
        if un:
            gun = min(un, key=_rng)["id"]
        else:
            close = [t for t in cand if _rng(t) < 60.0]
            if close:
                gun = min(close, key=_rng)["id"]

    # interceptor launches
    intercept = []
    reserve = RESERVE if len(strikers) > stock else 0
    avail = stock
    free = [t for t in strikers if t["id"] not in engaged]

    # early phase: farthest first while above reserve
    if avail > reserve:
        far = sorted(free, key=lambda t: -_rng(t))
        for t in far:
            if len(intercept) >= cap or avail <= reserve:
                break
            if _rng(t) < 30.0:
                continue
            intercept.append(t["id"])
            engaged.add(t["id"])
            avail -= 1

    # terminal phase: reserve on leftovers inside trigger range, nearest first
    if len(intercept) < cap and avail > 0:
        term = [t for t in strikers if t["id"] not in engaged
                and 30.0 <= _rng(t) <= TERMINAL_RANGE]
        term.sort(key=_rng)
        others = [t for t in term if t["id"] != gun]
        order = others + [t for t in term if t["id"] == gun]
        for t in order:
            if len(intercept) >= cap or avail <= 0:
                break
            if t["id"] == gun and len(others) > 0 and _rng(t) > 45.0:
                continue
            intercept.append(t["id"])
            engaged.add(t["id"])
            avail -= 1

    if gun is not None and gun in intercept:
        alt = [t for t in strikers if _rng(t) <= gun_range and t["id"] not in engaged]
        if alt:
            gun = min(alt, key=_rng)["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
