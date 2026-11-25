"""Idea: Ignore the first radar cohort, spend the whole magazine far out on the second cohort split evenly between its two depth shells, so the strikers left for the gun arrive spread across both shell deadlines and the gun gets its widest shot window.

What this attacks in hidden_orbit_screen_then_interleaved_drop:
- Its fixed release schedule. DECOY_RELEASE=14 and SHELL_A/B_RELEASE=27/31 all start
  from the same r~482 orbit. So the whole decoy screen crosses the 450 radar ring at
  about tick 22, and every striker crosses about 13 ticks later. Labelling tracks by
  first-seen tick gaps separates decoys from strikers perfectly long before the
  150-unit ID ring. Nothing is spent waiting for ID, and nothing goes on the screen.
- Its shell offset. The two shells reach r=100 about 4 ticks apart (shell A ~121,
  shell B ~125) and hit at ~141 and ~145. Strikers that survive the magazine are the
  gun's problem. If they all come from one shell, the gun gets only ~20 ticks. If they
  are split evenly, the gun gets ~25 ticks (121..145). The bot sorts strikers into
  shells using smoothed predicted impact ticks. Each launch or retarget goes to the
  shell with more unengaged strikers, so the residue is balanced.
- Its blast-proof spacing works against it here. Neighbours are about 25 apart, so the
  intercepts are clean single kills far out (r~330). Every intercept resolves before
  the gun window opens, and the gun never shares a target with a late interceptor.

What the replays show: the only full defences were by hover_bank_double_lattice. It
killed all 26 strikers with 17 interceptor kills plus 7-9 gun kills, using 22 shots.
All 16 decoys hit harmlessly at tick 128, and one interceptor was left over. The
margin is decided by how many useful gun shots fit before the last striker lands.
This bot spends every interceptor on strikers and none on the screen. It then gives
the gun a full shell-spanning window, using earliest-deadline order and skipping
strikers that already have an interceptor inbound.
"""
import math

NAME = "cohort_gap_shell_split_gun_window_stretch"
ROLE = "defender"

GAP = 6
_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cohort"] = {}
    _s["ncoh"] = 0
    _s["last_new"] = None
    _s["est"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)) or 25.0)
    sspd = float(rules.get("striker_speed", 4.0)) or 4.0
    ispd = float(rules.get("interceptor_speed", 12.0)) or 12.0
    ilife = int(rules.get("interceptor_lifetime", 90))
    gun_range = float(rules.get("gun_range", 100.0))
    lcap = int(rules.get("interceptor_launches_per_tick", 2))

    tmap = {}
    rng = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        tmap[tid] = t
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0, 0])
            r = math.hypot(p[0] - ax, p[1] - ay)
        rng[tid] = float(r)
        if tid not in _s["first"]:
            ln = _s["last_new"]
            if ln is None or tick - ln > GAP:
                _s["ncoh"] += 1
            _s["cohort"][tid] = _s["ncoh"] - 1
            _s["first"][tid] = tick
            _s["last_new"] = tick
        e = tick + max(0.0, rng[tid] - arad) / sspd
        old = _s["est"].get(tid)
        _s["est"][tid] = e if old is None else 0.8 * old + 0.2 * e

    ncoh = _s["ncoh"]

    def suspect(tid):
        t = tmap[tid]
        cls = t.get("cls", "unknown")
        if cls == "striker":
            return False
        if cls == "decoy":
            return True
        if _s["cohort"].get(tid, 0) == 0:
            # first cohort: screen unless nothing follows and it is getting close
            if ncoh >= 2:
                return True
            return rng[tid] > 260.0
        return False

    cands = [tid for tid in tmap if not suspect(tid) and rng[tid] > arad + 8.0]
    cset = set(cands)

    # shell split by smoothed predicted impact
    group = {}
    if cands:
        es = [_s["est"][c] for c in cands]
        lo, hi = min(es), max(es)
        if hi - lo > 2.5:
            thr = 0.5 * (lo + hi)
            for c in cands:
                group[c] = 0 if _s["est"][c] < thr else 1
        else:
            for c in cands:
                group[c] = 0

    engaged = {}
    for it in ints:
        tg = it.get("target")
        if tg in cset:
            engaged[tg] = engaged.get(tg, 0) + 1

    def pick(ipos=None, age=0):
        un = [c for c in cands if engaged.get(c, 0) == 0]
        if ipos is not None:
            ok = []
            for c in un:
                p = tmap[c].get("pos", [0, 0])
                d = math.hypot(p[0] - ipos[0], p[1] - ipos[1])
                if d / ispd + 2 <= ilife - age:
                    ok.append(c)
            un = ok
        if not un:
            return None
        cnt = [0, 0]
        for c in un:
            cnt[group.get(c, 0)] += 1
        g = 0 if cnt[0] >= cnt[1] else 1
        pool = [c for c in un if group.get(c, 0) == g] or un
        pool.sort(key=lambda c: (_s["est"][c], rng[c]))
        return pool[0]

    retarget = {}
    for it in ints:
        iid = it.get("id")
        tg = it.get("target")
        if iid is None:
            continue
        if tg in cset:
            continue
        ipos = it.get("pos", [ax, ay])
        nt = pick(ipos, int(it.get("age", 0) or 0))
        if nt is not None:
            retarget[iid] = nt
            engaged[nt] = engaged.get(nt, 0) + 1

    launches = []
    while stock > 0 and len(launches) < lcap:
        nt = pick()
        if nt is None:
            break
        launches.append(nt)
        engaged[nt] = engaged.get(nt, 0) + 1
        stock -= 1

    # gun: earliest deadline, skip strikers with an inbound interceptor
    inbound = {}
    for it in ints:
        tg = it.get("target")
        if it.get("id") in retarget:
            tg = retarget[it.get("id")]
        if tg in tmap:
            p = tmap[tg].get("pos", [0, 0])
            ip = it.get("pos", [ax, ay])
            d = math.hypot(p[0] - ip[0], p[1] - ip[1])
            eta = d / (ispd + sspd)
            if tg not in inbound or eta < inbound[tg]:
                inbound[tg] = eta
    gun = None
    if ammo > 0:
        best = None
        fallback = None
        for tid, t in tmap.items():
            if rng[tid] > gun_range - 2.0:
                continue
            cls = t.get("cls", "unknown")
            if cls == "decoy" or (cls == "unknown" and suspect(tid)):
                continue
            tti = max(0.0, rng[tid] - arad) / sspd
            if tid in inbound and inbound[tid] + 0.5 < tti and tti > 2.0:
                if fallback is None or rng[tid] < rng[fallback]:
                    fallback = tid
                continue
            if best is None or rng[tid] < rng[best]:
                best = tid
        gun = best if best is not None else fallback

    return {"intercept": launches, "retarget": retarget, "gun": gun}
