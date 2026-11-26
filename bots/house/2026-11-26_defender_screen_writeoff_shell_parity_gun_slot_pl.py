"""Idea: Write off the first radar cohort as a screen, split the magazine evenly across the two striker shells so the survivors arrive 4 ticks apart, then plan the gun one shot per tick across that gap.

What I am attacking in hidden_orbit_screen_then_interleaved_drop:
- Its timing is fixed by its constants. All 16 decoys release on tick 14 from r~482.
  They cross the 450 radar ring together at about tick 22. Shell A releases on tick 27
  and crosses at about tick 35. Shell B releases on tick 31 and crosses at about tick 39.
  Because the orbit is hidden, each group shows up as one tight first-seen cohort.
  The screen is always cohort 0, and the two striker shells are the later cohorts.
  I write off cohort 0 unless the ID ring later shows a striker in it. The decoys
  then cost me nothing.
- What the replays show: in its closest calls (hover_bank_double_lattice, seeds 3 and 5)
  the 16 decoys impacted harmlessly on tick 128. 19 interceptors killed 17 strikers.
  The match was then decided entirely by the gun, which got 7 to 9 kills from 22 shots.
  Defenders that already skip the screen still score only about 0.4 against it.
  So the attacker's real edge is not the decoys. It is crowding the last 9 or so strikers
  into the gun's one-shot-per-tick window, and its blast-proof spacing stops interceptors
  from ever getting double kills.
- Its weak point is the fixed 4-tick, ~16-unit gap between shell A and shell B. I treat
  each first-seen cohort as a shell and always fire the next interceptor into the shell
  with the most unengaged strikers. The leftovers then split roughly 3+3 plus misses
  across both shells instead of piling into one. The gun gets two separate close-range
  windows.
- The gun runs a slot planner. Over the next 30 ticks it greedily gives each future gun
  tick to the striker with the largest marginal kill value (survival x pk at its range
  in that slot). Strikers inside the asset radius cannot be shot. Strikers chased by a
  live interceptor are discounted. A striker that is about to impact gets shots first;
  later arrivals get their close-in shots later.
"""
import math

NAME = "screen_writeoff_shell_parity_gun_slot_planner"
ROLE = "defender"

COHORT_GAP = 2
ENGAGE_R = 440.0
DEADLINE_R = 220.0
HORIZON = 30
NEIGH_R = 18.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["known"] = {}
    _s["assigned"] = {}
    _s["launch_tick"] = {}


def _cohorts(first_seen):
    ticks = sorted(set(first_seen.values()))
    tmap = {}
    idx = -1
    prev = None
    for t in ticks:
        if prev is None or t - prev > COHORT_GAP:
            idx += 1
        tmap[t] = idx
        prev = t
    return {tid: tmap[ft] for tid, ft in first_seen.items()}, idx


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
    a_rad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    tracks = obs.get("tracks", []) or []
    icpts = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    pk_int = float(rules.get("interceptor_kill_prob", 0.85))
    g_rng = float(rules.get("gun_range", 100.0))
    g_scale = float(rules.get("gun_pk_scale", 0.4))
    g_floor = float(rules.get("gun_pk_floor", 0.05))
    spd = float(rules.get("striker_speed", 4.0))

    fs = _s["first_seen"]
    known = _s["known"]
    tr = {}
    for t in tracks:
        tid = t["id"]
        fs.setdefault(tid, tick)
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            known[tid] = c
        px, py = float(t["pos"][0]), float(t["pos"][1])
        r = t.get("range")
        if r is None:
            r = math.hypot(px - ax, py - ay)
        tr[tid] = (px, py, float(r))

    cmap, maxc = _cohorts(fs)
    later_exists = maxc >= 1
    c0_str = sum(1 for tid, c in known.items() if c == "striker" and cmap.get(tid) == 0)
    c0_dec = sum(1 for tid, c in known.items() if c == "decoy" and cmap.get(tid) == 0)
    screen0 = later_exists and c0_str <= 0.25 * c0_dec

    def eligible(tid):
        c = known.get(tid, "unknown")
        if c == "decoy":
            return False
        if c == "striker":
            return True
        co = cmap.get(tid, 0)
        r = tr[tid][2]
        if co == 0:
            if screen0:
                return False
            if later_exists:
                return r <= ENGAGE_R
            return r < DEADLINE_R
        return r <= ENGAGE_R

    elig = [tid for tid in tr if eligible(tid)]
    elig_set = set(elig)

    # engagement ledger
    engaged = set()
    for ic in icpts:
        tg = ic.get("target")
        if tg is not None:
            engaged.add(tg)
    for tid, lt in _s["launch_tick"].items():
        if tick - lt <= 2:
            engaged.add(tid)

    # neighbour bonus (opportunistic multi-kill)
    neigh = {}
    for i in elig:
        xi, yi, _ = tr[i]
        n = 0
        for j in elig:
            if j != i:
                xj, yj, _ = tr[j]
                if (xi - xj) ** 2 + (yi - yj) ** 2 < NEIGH_R * NEIGH_R:
                    n += 1
        neigh[i] = n

    assigned = _s["assigned"]

    def pick(exclude, near=None):
        cands = [t for t in elig if t not in exclude]
        if not cands:
            return None
        minas = min(assigned.get(t, 0) for t in cands)
        cands = [t for t in cands if assigned.get(t, 0) == minas]
        rem = {}
        for t in cands:
            co = cmap.get(t, 0)
            rem[co] = rem.get(co, 0) + 1
        best_co = max(rem, key=lambda c: (rem[c], -c))
        pool = [t for t in cands if cmap.get(t, 0) == best_co]
        if near is not None:
            nx, ny = near
            return min(pool, key=lambda t: (-neigh.get(t, 0),
                                            (tr[t][0] - nx) ** 2 + (tr[t][1] - ny) ** 2, str(t)))
        return min(pool, key=lambda t: (-neigh.get(t, 0), tr[t][2], str(t)))

    # retarget interceptors whose target is gone or no longer eligible
    retarget = {}
    for ic in icpts:
        tg = ic.get("target")
        if tg in elig_set:
            continue
        pos = ic.get("pos") or [ax, ay]
        nt = pick(engaged, (float(pos[0]), float(pos[1])))
        if nt is not None:
            retarget[ic["id"]] = nt
            engaged.add(nt)

    # launches
    launch = []
    n = min(cap, stock)
    for _ in range(max(0, n)):
        t = pick(engaged)
        if t is None:
            break
        launch.append(t)
        engaged.add(t)
        assigned[t] = assigned.get(t, 0) + 1
        _s["launch_tick"][t] = tick

    # gun slot planner
    gun = None
    if ammo > 0:
        def gpk(d):
            frac = max(0.0, 1.0 - d / g_rng)
            return max(g_floor, min(0.95, g_scale * frac + g_floor))

        cand = []
        for tid in elig:
            d = tr[tid][2]
            if d - spd * HORIZON > g_rng:
                continue
            surv = (1.0 - pk_int) if tid in engaged else 1.0
            cand.append([tid, d, surv])
        if cand:
            used = set()
            first = None
            for _ in range(HORIZON):
                best = None
                bv = 0.0
                for k in range(HORIZON):
                    if k in used:
                        continue
                    for c in cand:
                        dk = c[1] - spd * k
                        if dk <= a_rad or dk > g_rng:
                            continue
                        if k == 0 and tr[c[0]][2] > g_rng:
                            continue
                        p = gpk(dk)
                        v = c[2] * p
                        if v > bv + 1e-12:
                            bv = v
                            best = (k, c, p)
                if best is None:
                    break
                k, c, p = best
                used.add(k)
                c[2] *= (1.0 - p)
                if k == 0:
                    first = c[0]
            if first is None:
                inr = [c for c in cand if tr[c[0]][2] <= g_rng and c[1] > a_rad * 0.5]
                if inr:
                    first = min(inr, key=lambda c: (c[1], str(c[0])))[0]
            gun = first

    return {"intercept": launch, "retarget": retarget, "gun": gun}
