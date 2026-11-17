"""Idea: Hold every interceptor until the decoy screen identifies itself at the ID ring, treat every later unknown as a striker, and spend the magazine on the rear shell first so the gun always has a steady stream of front-shell targets.

What this attacks in hidden_orbit_screen_then_interleaved_drop:
- Its screen timing is fixed. Decoys release at tick 14 and strikers at ticks
  27 and 31, all from r~482. So the 16 decoys reach the 150 ID ring at about
  tick 97. At that point shell A is still near r~202 and shell B near r~218.
  The screen exposes itself while the strikers still have about 45 ticks to go.
- Many defenders guess at unknowns, and some skip cohorts a priori. This bot
  does neither. It fires nothing until the first radar cohort is mostly ID'd as
  decoys. Then the "screen revealed" latch flips. Every unknown that showed up
  after that cohort is treated as a striker. Twenty interceptors at 2 per tick
  launch in 10 ticks, with intercepts near r 130-170, well before gun range.
  If the first cohort turns out to be strikers instead, the bot falls back to
  pure ID gating, which still leaves time at the 150 ring.
- The two shells are only 16 units (4 ticks) apart. Defenders that fire
  nearest-first clear shell A and leave about 9 shell-B survivors. Those reach
  the gun at nearly the same moment, the gun saturates, and strikers leak.
  This bot fires at the rear shell first. Shell A survivors then reach the gun
  from tick ~122. The gun gets close targets on every tick for its whole window
  instead of a crowded last few ticks.
- A small reserve fires only at strikers inside 75 that the gun is not already
  working on. Any interceptor whose target the gun kills is retargeted.

Replay evidence: in its closest calls against hover_bank_double_lattice, the 16
decoy impacts all land on tick 128. That is the screen running exactly 13 ticks
ahead of the strikers and costing the defender nothing when left alone. The
defender stopped all 26 strikers only because the gun scored 7-9 kills from 22
shots on top of 17-19 interceptor kills. Gun utilisation in the final window
decides the match, and that is what rear-shell-first ordering protects.
"""
import math

NAME = "screen_reveal_rear_shell_first"
ROLE = "defender"

RESERVE = 4
RESERVE_TRIGGER = 75.0
MIN_LAUNCH_RANGE = 36.0
COHORT_WIN = 3
WAVE_DEPTH = 60.0
IMMINENT = 20.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["t0"] = None
    _s["first"] = {}
    _s["cls"] = {}
    _s["revealed"] = False


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0) or 0)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    gun_range = float(rules.get("gun_range", 100.0))
    id_range = float(rules.get("id_range", 150.0))
    i_speed = float(rules.get("interceptor_speed", 12.0))
    i_life = float(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))

    first = _s["first"]
    cls = _s["cls"]

    T = {}
    for tr in tracks:
        tid = tr.get("id")
        if tid is None:
            continue
        pos = tr.get("pos") or [0.0, 0.0]
        px, py = float(pos[0]), float(pos[1])
        rng = tr.get("range")
        if rng is None:
            rng = math.hypot(px - ax, py - ay)
        rng = float(rng)
        if _s["t0"] is None:
            _s["t0"] = tick
        if tid not in first:
            first[tid] = tick
        c = tr.get("cls", "unknown")
        if c in ("striker", "decoy"):
            cls[tid] = c
        T[tid] = (px, py, rng)

    t0 = _s["t0"]

    # screen reveal latch
    if not _s["revealed"] and t0 is not None and tick > t0 + COHORT_WIN:
        c1 = [t for t, f in first.items() if f <= t0 + COHORT_WIN]
        known = [cls[t] for t in c1 if t in cls]
        if len(c1) >= 4 and len(known) >= max(3, len(c1) // 3):
            dec = sum(1 for k in known if k == "decoy")
            if dec >= 0.75 * len(known):
                _s["revealed"] = True

    def is_target(tid):
        c = cls.get(tid)
        if c == "striker":
            return True
        if c == "decoy":
            return False
        rng = T[tid][2]
        if rng < 0.9 * id_range:
            return True
        if _s["revealed"] and t0 is not None and first.get(tid, 0) > t0 + COHORT_WIN:
            return True
        return False

    targets = [t for t in T if is_target(t)]
    tset = set(targets)

    # engagement bookkeeping
    engaged = {}
    free = []
    for it in inters:
        iid = it.get("id")
        if iid is None:
            continue
        tg = it.get("target")
        if tg in tset and tg not in engaged:
            engaged[tg] = it
        else:
            free.append(it)

    # retarget free interceptors to nearest reachable unengaged target
    retarget = {}
    for it in free:
        ip = it.get("pos") or [ax, ay]
        ix, iy = float(ip[0]), float(ip[1])
        reach = max(0.0, (i_life - float(it.get("age", 0) or 0)) * i_speed)
        best, bd = None, None
        for t in targets:
            if t in engaged:
                continue
            d = math.hypot(T[t][0] - ix, T[t][1] - iy)
            if d > reach:
                continue
            if bd is None or d < bd:
                best, bd = t, d
        if best is not None:
            retarget[it["id"]] = best
            engaged[best] = it

    # gun: nearest target in range, skipping ones about to be hit
    gun = None
    if ammo > 0:
        inrange = [t for t in targets if T[t][2] <= gun_range]
        if inrange:
            imminent = set()
            for t, it in engaged.items():
                ip = it.get("pos") if isinstance(it, dict) else None
                if ip:
                    if math.hypot(T[t][0] - float(ip[0]), T[t][1] - float(ip[1])) < IMMINENT:
                        imminent.add(t)
            pool = [t for t in inrange if t not in imminent] or inrange
            gun = min(pool, key=lambda t: T[t][2])

    # launches
    launch = []
    avail = min(cap, stock)
    if avail > 0:
        unengaged = [t for t in targets if t not in engaged and T[t][2] > MIN_LAUNCH_RANGE]
        urgent = [t for t in unengaged if T[t][2] < RESERVE_TRIGGER]
        # farthest urgent first; the gun is working on the nearest
        urgent.sort(key=lambda t: (t == gun, -T[t][2]))
        rest = [t for t in unengaged if T[t][2] >= RESERVE_TRIGGER]
        if rest:
            mn = min(T[t][2] for t in rest)
            rest = [t for t in rest if T[t][2] <= mn + WAVE_DEPTH]
            rest.sort(key=lambda t: -T[t][2])  # rear shell first
        left = stock
        for t in urgent:
            if len(launch) >= avail or left <= 0:
                break
            launch.append(t)
            left -= 1
        for t in rest:
            if len(launch) >= avail or left <= RESERVE:
                break
            launch.append(t)
            left -= 1

    return {"intercept": launch, "retarget": retarget, "gun": gun}
