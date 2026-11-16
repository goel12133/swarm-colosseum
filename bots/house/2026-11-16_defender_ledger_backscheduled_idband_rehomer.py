"""Idea: Backscheduled ID-band launches that let interceptors fly before a target is identified and then re-home them, bounded by a budget-arithmetic ledger of the most strikers the attacker could still afford.

Approach
--------
1. Budget ledger. Every track id ever seen is recorded with the last class
   revealed for it. The attacker's budget is fixed and public: 60, with strikers
   at 2 and decoys at 0.5. From that, the bot computes an upper bound on how many
   still-unknown tracks can be strikers:
       x <= (B - 2*S_known - 0.5*D_known - 0.5*U) / 1.5
   That bound becomes the striker probability for live unknowns. It also gives a
   small stock reserve held back for strikers that have not been launched yet.
2. Launch timing tied to the ID band. A threat is engaged so that the meeting
   point falls at about radius 125, just inside the 150 id range. Most targets
   are therefore classified while the interceptor is still in flight. Any
   interceptor whose target is revealed as a decoy, or has vanished, is
   re-homed. It goes to the nearest uncovered striker or unknown it can still
   reach within its remaining lifetime.
3. Backscheduling under the launch cap. Candidates are sorted by how long each
   launch can wait. The i-th candidate must go once that wait is no more than
   about i/2 ticks, because only 2 launches are allowed per tick. Dense waves
   therefore start launching early enough to be fully engaged. Sparse trickles
   still wait for identification.
4. Blast-sharing coverage. A track within about 8 units of a track that already
   has an interceptor counts as covered. Converging rings and stacked columns
   then cost fewer interceptors.
5. The gun takes the best value times hit-chance target inside range. It favours
   strikers and unknowns that are not about to be hit by an interceptor. It
   fires on decoys only when ammo is plentiful.

Why it holds up across the field
--------------------------------
- Synchronized and phase-locked rings beat defenders that launch only after
  identification. Here the backscheduler launches early in proportion to how
  many threats are queued, and blast sharing exploits ring convergence.
- Staggered trickles beat static parking defenders. Here every launch is
  per-threat and timed to the ID band, so a lone striker gets exactly one
  interceptor plus the gun.
- Bait waves, decoy drains, clear-sky follow-ups and orbiting shadows try to
  empty the magazine on decoys. Three things limit that loss:
  * unknowns that are not closing are never engaged;
  * retargeting salvages interceptors aimed at revealed decoys;
  * the ledger reserve keeps stock for strikers the attacker can still afford.
- Veiled and blast-proof splits spread out so one blast cannot hit two drones.
  When blast sharing is impossible the bot degrades to one interceptor per
  threat. Misses are re-engaged from the origin, which is quick at short range,
  and the gun handles close leakers.
"""
import math

NAME = "ledger_backscheduled_idband_rehomer"
ROLE = "defender"

_S = {"cls": {}, "seen": set()}


def reset(seed=None):
    global _S
    _S = {"cls": {}, "seen": set()}


def _f(d, k, default):
    try:
        v = d.get(k, default)
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    budget = _f(rules, "attacker_budget", 60.0)
    s_cost = _f(rules, "striker_cost", 2.0)
    d_cost = _f(rules, "decoy_cost", 0.5)
    i_speed = _f(rules, "interceptor_speed", 12.0)
    i_life = _f(rules, "interceptor_lifetime", 90)
    blast = _f(rules, "blast_radius", 10.0)
    id_range = _f(rules, "id_range", 150.0)
    gun_range = _f(rules, "gun_range", 100.0)
    pk_scale = _f(rules, "gun_pk_scale", 0.4)
    pk_floor = _f(rules, "gun_pk_floor", 0.05)
    launch_cap = int(_f(rules, "interceptor_launches_per_tick", 2))
    d_speed = _f(rules, "striker_speed", 4.0)
    asset = obs.get("asset", {}) or {}
    a_r = _f(asset, "radius", 25.0)
    apos = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(apos[0]), float(apos[1])
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    ledger = _S["cls"]
    seen = _S["seen"]

    # ---- parse tracks
    T = {}
    for t in obs.get("tracks", []) or []:
        try:
            tid = t["id"]
            px, py = float(t["pos"][0]) - ax, float(t["pos"][1]) - ay
            v = t.get("vel") or [0.0, 0.0]
            vx, vy = float(v[0]), float(v[1])
        except Exception:
            continue
        r = math.hypot(px, py)
        c = t.get("cls", "unknown") or "unknown"
        seen.add(tid)
        if c in ("striker", "decoy"):
            ledger[tid] = c
        cls = ledger.get(tid, "unknown")
        closing = -(px * vx + py * vy) / r if r > 1e-6 else d_speed
        T[tid] = {"x": px, "y": py, "vx": vx, "vy": vy, "r": r,
                  "cls": cls, "c": closing}

    # ---- ledger bound on striker count among unknowns
    sk = sum(1 for k in seen if ledger.get(k) == "striker")
    dk = sum(1 for k in seen if ledger.get(k) == "decoy")
    uk = len(seen) - sk - dk
    extra = max(0.0, s_cost - d_cost)
    rem = budget - s_cost * sk - d_cost * dk - d_cost * uk
    x_max = int(math.floor(rem / extra + 1e-9)) if extra > 0 else uk
    x_max = max(0, x_max)
    alive_unknown = sum(1 for t in T.values() if t["cls"] == "unknown")
    p_u = min(1.0, x_max / alive_unknown) if alive_unknown else 1.0
    # strikers not yet seen that the attacker could still afford
    future_str = max(0.0, rem) / s_cost if s_cost > 0 else 0.0
    reserve = int(min(3, math.floor(future_str)))

    def value(t):
        if t["cls"] == "striker":
            return 1.0
        if t["cls"] == "decoy":
            return 0.0
        return max(0.05, p_u)

    for t in T.values():
        t["v"] = value(t)

    # ---- interceptor coverage
    cov = {}
    free = []
    ints = obs.get("interceptors", []) or []
    for it in ints:
        try:
            iid = it["id"]
            tgt = it.get("target")
            ip = it.get("pos") or [0.0, 0.0]
            ix, iy = float(ip[0]) - ax, float(ip[1]) - ay
            age = float(it.get("age", 0) or 0)
        except Exception:
            continue
        info = {"id": iid, "x": ix, "y": iy, "age": age, "tgt": tgt}
        if tgt in T and T[tgt]["v"] > 0.0:
            cov[tgt] = cov.get(tgt, 0) + 1
        else:
            free.append(info)
        it_list = info
    # interceptor positions per target for gun discounting
    near_hit = set()
    for it in ints:
        try:
            tgt = it.get("target")
            if tgt in T:
                ip = it.get("pos") or [0.0, 0.0]
                dx = float(ip[0]) - ax - T[tgt]["x"]
                dy = float(ip[1]) - ay - T[tgt]["y"]
                if math.hypot(dx, dy) < 2.5 * i_speed:
                    near_hit.add(tgt)
        except Exception:
            pass

    share_r = min(8.0, blast * 0.8)

    def covered(tid):
        if cov.get(tid, 0) > 0:
            return True
        t = T[tid]
        for oid, n in cov.items():
            if n <= 0 or oid == tid or oid not in T:
                continue
            o = T[oid]
            if math.hypot(o["x"] - t["x"], o["y"] - t["y"]) < share_r:
                return True
        return False

    # ---- retarget free interceptors
    retarget = {}
    for fi in free:
        life_left = max(0.0, i_life - fi["age"]) * i_speed
        best, bscore = None, None
        for tid, t in T.items():
            if t["v"] <= 0.0:
                continue
            d = math.hypot(t["x"] - fi["x"], t["y"] - fi["y"])
            if d > life_left * 0.9:
                continue
            unc = 0.0 if covered(tid) else 1.0
            sc = unc * 3.0 + t["v"] * 2.0 - d / 200.0 - t["r"] / 400.0
            if bscore is None or sc > bscore:
                best, bscore = tid, sc
        if best is not None and best != fi["tgt"]:
            retarget[fi["id"]] = best
            cov[best] = cov.get(best, 0) + 1

    # ---- backscheduled launches
    meet_r = min(id_range - 25.0, 125.0)
    cands = []
    for tid, t in T.items():
        if t["v"] <= 0.0 or covered(tid):
            continue
        c = t["c"]
        if c < 0.5 and t["r"] > 120.0:
            continue  # not closing: orbiter / lure, wait
        ce = max(c, 2.0)
        r_launch = meet_r * (i_speed + max(c, d_speed)) / i_speed
        delay = (t["r"] - r_launch) / ce
        if t["r"] < 120.0:
            delay = min(delay, 0.0)
        # slight priority to confirmed strikers
        cands.append((delay - 0.5 * (t["cls"] == "striker"), tid, t))
    cands.sort(key=lambda z: z[0])

    launches = []
    avail = stock
    for i, (delay, tid, t) in enumerate(cands):
        if len(launches) >= launch_cap or avail <= 0:
            break
        if delay > i // max(1, launch_cap) + 1.0:
            continue
        if t["cls"] == "unknown" and t["r"] > 110.0 and avail <= reserve:
            continue
        if t["cls"] == "unknown" and p_u < 0.15 and t["r"] > 110.0:
            continue
        launches.append(tid)
        avail -= 1
        cov[tid] = cov.get(tid, 0) + 1

    # ---- gun
    gun = None
    if ammo > 0:
        best, bscore = None, None
        for tid, t in T.items():
            if t["r"] > gun_range:
                continue
            pk = max(pk_floor, pk_scale * (1.0 - t["r"] / gun_range))
            v = t["v"]
            if v <= 0.0:
                if ammo < 40:
                    continue
                v = 0.02
            disc = 0.35 if tid in near_hit else 1.0
            sc = v * pk * disc + 0.001 * (gun_range - t["r"])
            if bscore is None or sc > bscore:
                best, bscore = tid, sc
        gun = best

    return {"intercept": launches, "retarget": retarget, "gun": gun}
