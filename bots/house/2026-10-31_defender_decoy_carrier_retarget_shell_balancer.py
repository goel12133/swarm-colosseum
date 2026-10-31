"""Idea: Launch most of the magazine at the decoy screen as "carriers", then retarget it mid-flight onto both striker shells, balancing kills so the gun's leftover targets straddle both shells.

Target: 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_drop.

Which part of its logic this attacks:
- The release schedule. Decoys release at tick 14 and the striker shells at
  ticks 27 and 31, all from the same r~482 orbit. So the 16-track screen
  crosses the 450 radar edge alone, about 13 ticks before the strikers, and
  the two shells then appear about 4 ticks apart. Its tracks therefore form
  three clean birth cohorts: screen, shell A, shell B.
- Instead of holding fire on the screen, I launch interceptors at the screen
  tracks on purpose. Each screen track gets one carrier. When the striker
  cohorts stop appearing, or a carrier gets close to its screen target, every
  carrier is retargeted onto a striker. The screen itself is never hit, and
  the magazine is already in the air and halfway out when the shells appear.
- The interleaved two-shell drop. Each shell reaches the asset as a
  simultaneous wall, and the gun fires once per tick. If all the survivors
  sit in one shell, the gun gets about 19 ticks of shots. If they are split
  across both shells, it gets about 23. Every interceptor assignment and
  every reserve launch therefore goes to the shell with the most unclaimed
  strikers. Survivors stay balanced and the gun window stretches across both
  shells.

What in the replays shows this is where it breaks:
- In its two closest calls (seeds 3 and 5 vs hover_bank_double_lattice),
  all 16 decoys impacted untouched and 19 of 20 interceptors went to
  strikers. The interceptors killed 17 to 19 strikers, and the gun finished
  the remaining 7 to 9 over 22 shots spanning both shells. The attacker only
  loses when no interceptor is spent on the screen and the gun has survivors
  from both shells. This bot is built to produce exactly that every match.
  It also keeps a 4-round reserve, launched only after the early results
  are visible, so misses are covered before gun range.
"""
import math

NAME = "decoy_carrier_retarget_shell_balancer"
ROLE = "defender"

RESERVE = 4
COHORT_GAP = 3
QUIET_TICKS = 5
HOLD_DIST = 90.0
RESERVE_TTI = 60.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cohort"] = {}
    _s["ncoh"] = 0
    _s["last_new"] = None
    _s["later_seen"] = False
    _s["last_later_new"] = None
    _s["launched"] = 0
    _s["stock0"] = None


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ap = (float(ap[0]), float(ap[1]))
    ar = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    spd = float(rules.get("striker_speed", 4.0)) or 4.0
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    if _s["stock0"] is None:
        _s["stock0"] = stock + _s["launched"]
    early_n = max(0, _s["stock0"] - RESERVE)

    tracks = {}
    for t in obs.get("tracks", []) or []:
        tid = t.get("id")
        if tid is None:
            continue
        tracks[tid] = t
        if tid not in _s["first"]:
            _s["first"][tid] = tick
            if _s["last_new"] is None or tick - _s["last_new"] >= COHORT_GAP:
                _s["ncoh"] += 1
            _s["last_new"] = tick
            c = _s["ncoh"] - 1
            _s["cohort"][tid] = c
            if c >= 1:
                _s["later_seen"] = True
                _s["last_later_new"] = tick

    later = _s["later_seen"]
    quiet = later and (tick - _s["last_later_new"] >= QUIET_TICKS)

    info = {}
    for tid, t in tracks.items():
        p = t.get("pos", [0.0, 0.0])
        p = (float(p[0]), float(p[1]))
        r = _d(p, ap)
        cls = t.get("cls", "unknown")
        coh = _s["cohort"].get(tid, 0)
        if cls == "decoy":
            thr = False
        elif cls == "striker":
            thr = True
        else:
            thr = (coh >= 1) if later else True
        info[tid] = {"pos": p, "r": r, "tti": (r - ar) / spd,
                     "cls": cls, "coh": coh, "thr": thr}

    threats = [tid for tid in info if info[tid]["thr"]]

    def choose(frm, claimed, by_urgency):
        cands = [tid for tid in threats if tid not in claimed]
        if not cands:
            return None
        groups = {}
        for tid in cands:
            groups.setdefault(info[tid]["coh"], []).append(tid)
        best_g = max(groups, key=lambda g: (len(groups[g]), -g))
        pool = groups[best_g]
        if by_urgency:
            return min(pool, key=lambda tid: (info[tid]["tti"], str(tid)))
        return min(pool, key=lambda tid: (_d(frm, info[tid]["pos"]), str(tid)))

    icps = []
    for ic in obs.get("interceptors", []) or []:
        p = ic.get("pos", [0.0, 0.0])
        icps.append({"id": ic.get("id"), "target": ic.get("target"),
                     "pos": (float(p[0]), float(p[1]))})

    def cur_dist(ic):
        t = ic["target"]
        if t in info:
            return _d(ic["pos"], info[t]["pos"])
        return 1e9

    icps.sort(key=lambda ic: (cur_dist(ic), str(ic["id"])))
    claimed = set()
    retarget = {}
    need = []
    holding = 0
    for ic in icps:
        t = ic["target"]
        if t in info and info[t]["thr"] and t not in claimed:
            claimed.add(t)
            continue
        if (t in info and info[t]["cls"] != "decoy" and not info[t]["thr"]
                and not quiet and cur_dist(ic) > HOLD_DIST):
            holding += 1
            continue
        need.append(ic)

    need.sort(key=lambda ic: str(ic["id"]))
    for ic in need:
        t = ic["target"]
        nt = choose(ic["pos"], claimed, False)
        if nt is None:
            if (t in info and info[t]["cls"] != "decoy" and not info[t]["thr"]
                    and cur_dist(ic) > HOLD_DIST):
                continue
            if threats:
                nt = min(threats, key=lambda x: (_d(ic["pos"], info[x]["pos"]), str(x)))
            else:
                continue
        claimed.add(nt)
        if nt != t:
            retarget[ic["id"]] = nt

    # launches
    launches = []
    active = len(icps) - holding
    unclaimed = [tid for tid in threats if tid not in claimed]
    min_tti = min([info[t]["tti"] for t in unclaimed], default=1e9)
    reserve_ok = (active <= 0 and holding == 0) or min_tti < RESERVE_TTI
    while len(launches) < cap and len(launches) < stock:
        if _s["launched"] >= early_n and not reserve_ok:
            break
        tid = choose(ap, claimed, True)
        if tid is None:
            break
        if info[tid]["tti"] < 3.0:
            claimed.add(tid)
            continue
        launches.append(tid)
        claimed.add(tid)
        _s["launched"] += 1

    # gun
    gun = None
    if ammo > 0:
        inrange = [tid for tid in threats if info[tid]["r"] <= gun_range]
        if inrange:
            def covered(tid):
                for ic in icps:
                    tgt = retarget.get(ic["id"], ic["target"])
                    if tgt == tid and _d(ic["pos"], info[tid]["pos"]) < 12.0:
                        return True
                return False
            free = [tid for tid in inrange if not covered(tid)]
            pool = free if free else inrange
            gun = min(pool, key=lambda tid: (info[tid]["r"], str(tid)))

    return {"intercept": launches, "retarget": retarget, "gun": gun}
