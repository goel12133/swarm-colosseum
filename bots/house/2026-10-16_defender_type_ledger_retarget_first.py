"""Idea: Hold interceptors until the radar reveals a drone's type, unless a running count of revealed types shows the attacker is mostly strikers, and re-aim every launched interceptor away from decoys as soon as they are identified.

Approach
--------
1. Type ledger. Every type the radar reveals is remembered per track id.
   - A running striker fraction f = (strikers seen + 1) / (types seen + 2.5)
     prices every "unknown" track.
   - Decoy-heavy attackers therefore cost the magazine almost nothing.
   - Striker-heavy attackers make unknowns worth firing at early, from far
     out in the outer ring.

2. Coverage ledger. A threat counts as covered only if an in-flight
   interceptor can reach it before impact and before the interceptor's
   lifetime expires.
   - The check uses the interceptor's estimated arrival time against the
     threat's time-to-impact.
   - Everything within the blast radius of a covered target also counts as
     covered.
   - When an interceptor vanishes and its target is still alive (a miss),
     that target becomes uncovered again and is re-engaged at once.

3. Retarget-first. Before spending stock, the bot re-aims any interceptor
   whose target is a decoy, is gone, or can no longer be reached. It moves
   to the best uncovered threat cluster.

4. Cluster value. Launch candidates are scored by the sum of threat values
   inside one blast radius, weighted by urgency (1 / time-to-impact).
   - Tight shells and depth stacks yield multi-kills.
   - Ring attacks are taken in deadline order.
   - Spent stock goes to the earliest leaks first.

5. Late double cover. Strikers close to the asset get a second interceptor,
   but only when stock clearly exceeds the number of uncovered strikers.

6. Gun. The gun only shoots threats (strikers, and unknowns when no type is
   known yet). It prefers uncovered tracks, then the soonest to hit.

Why this holds up against every attacker in the field
-----------------------------------------------------
- Synchronized and phase-locked rings: these have no blast overlap, so the
  fight is decided by stock spent per striker. Waiting for type reveal (or
  a high f) avoids decoy waste. Deadline ordering, plus the gun on leakers,
  maximises how many strikers are stopped.
- Interleaved, depth-shell and blast-proof-depth attackers: the coverage
  ledger re-fires after misses instead of assuming a kill. Retargeting
  recovers interceptors that were aimed at decoys. Cluster scoring finds
  any blast overlap that still exists.
- Magazine-drain, parked-ring and decoy screens: unknowns are priced by f.
  Decoy-revealed tracks never draw fire, so the stock survives until the
  real strikers arrive.
- Trickle and staggered attacks: the coverage ledger fires one interceptor
  per threat in deadline order and keeps a reserve. Spread-out raids
  therefore never strip the magazine early.
"""

import math

NAME = "type_ledger_retarget_first"
ROLE = "defender"

_S = {}


def reset(seed=None):
    global _S
    _S = {"cls": {}, "str": set(), "dec": set()}


reset()


def _empty():
    return {"intercept": [], "retarget": {}, "gun": None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return _empty()


def _f(rules, key, default):
    try:
        return float(rules.get(key, default))
    except Exception:
        return default


def _act(obs):
    rules = obs.get("rules", {}) or {}
    asset_r = _f(rules, "asset_radius", 25.0)
    i_speed = _f(rules, "interceptor_speed", 12.0)
    i_life = _f(rules, "interceptor_lifetime", 90)
    blast = _f(rules, "blast_radius", 10.0)
    gun_range = _f(rules, "gun_range", 100.0)
    launch_cap = int(_f(rules, "interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)

    mem = _S["cls"]
    tracks = {}

    # Pass 1: read tracks and update the type ledger.
    for t in obs.get("tracks", []) or []:
        try:
            tid = t["id"]
            x, y = float(t["pos"][0]), float(t["pos"][1])
            vx, vy = float(t["vel"][0]), float(t["vel"][1])
        except Exception:
            continue
        r = math.hypot(x, y)
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            mem[tid] = c
            (_S["str"] if c == "striker" else _S["dec"]).add(tid)
        tracks[tid] = {
            "x": x, "y": y, "vx": vx, "vy": vy,
            "r": r, "cls": mem.get(tid, c),
        }

    # Price unknown tracks by the observed striker fraction.
    ns, nd = len(_S["str"]), len(_S["dec"])
    f = (ns + 1.0) / (ns + nd + 2.5)

    # Pass 2: threat value and time-to-impact per track.
    for t in tracks.values():
        r = max(t["r"], 1e-6)
        closing = -(t["x"] * t["vx"] + t["y"] * t["vy"]) / r
        t["closing"] = closing
        t["tti"] = max(0.0, r - asset_r) / max(closing, 0.3)
        if t["cls"] == "striker":
            t["p"] = 1.0
        elif t["cls"] == "decoy":
            t["p"] = 0.0
        else:
            t["p"] = f
        t["cov"] = 0

    def neighbors(tid):
        a = tracks[tid]
        out = []
        for uid, u in tracks.items():
            if u["p"] <= 0:
                continue
            if math.hypot(u["x"] - a["x"], u["y"] - a["y"]) <= blast * 0.9:
                out.append(uid)
        return out

    def cover(tid):
        for uid in neighbors(tid):
            tracks[uid]["cov"] += 1

    def cluster_value(tid):
        return sum(tracks[u]["p"] for u in neighbors(tid) if tracks[u]["cov"] == 0)

    # Coverage ledger: which interceptors can still reach a real threat in time.
    free = []
    for it in obs.get("interceptors", []) or []:
        try:
            iid = it["id"]
            tgt = it.get("target")
            ix, iy = float(it["pos"][0]), float(it["pos"][1])
            age = float(it.get("age", 0))
        except Exception:
            continue
        life = i_life - age
        ok = False
        if tgt in tracks and tracks[tgt]["p"] > 0:
            tt = tracks[tgt]
            d = math.hypot(tt["x"] - ix, tt["y"] - iy)
            eta = d / (i_speed + 2.0)
            if eta < life and eta <= tt["tti"] + 1.0:
                ok = True
        if ok:
            cover(tgt)
        elif life > 3:
            free.append((iid, ix, iy, life))

    n_uncov_str = sum(
        1 for t in tracks.values() if t["cls"] == "striker" and t["cov"] == 0
    )

    # Retarget-first: re-aim free interceptors before spending stock.
    retarget = {}
    for iid, ix, iy, life in free:
        best, best_score = None, 0.0
        for tid, t in tracks.items():
            if t["p"] <= 0 or t["cov"] > 0:
                continue
            d = math.hypot(t["x"] - ix, t["y"] - iy)
            eta = d / (i_speed + 2.0)
            if eta >= life or eta > t["tti"] + 1.0:
                continue
            score = cluster_value(tid) / (1.0 + d / 200.0)
            if score > best_score:
                best, best_score = tid, score
        if best is not None:
            retarget[iid] = best
            cover(best)

    # Launch planning.
    n_uncov_str = sum(
        1 for t in tracks.values() if t["cls"] == "striker" and t["cov"] == 0
    )
    unk_range = 400.0 if f >= 0.7 else (260.0 if f >= 0.5 else 190.0)
    reserve_unknown = 2 if f >= 0.6 else 5

    cands = []
    for tid, t in tracks.items():
        if t["p"] <= 0:
            continue
        meet_t = t["r"] / (i_speed + max(t["closing"], 0.0))
        if meet_t > t["tti"] + 0.5 or meet_t >= i_life:
            continue
        cv = cluster_value(tid)
        if t["cov"] == 0:
            if t["cls"] == "unknown":
                if t["r"] > unk_range:
                    continue
                if cv < 0.55 and f < 0.5:
                    continue
            cands.append((tid, cv * (1.0 + 30.0 / (t["tti"] + 5.0)), False))
        elif t["cls"] == "striker" and t["cov"] == 1 and t["tti"] < 14:
            cands.append((tid, 0.4 * (1.0 + 30.0 / (t["tti"] + 5.0)), True))
    cands.sort(key=lambda c: -c[1])

    launches = []
    left = stock
    for tid, score, is_double in cands:
        if len(launches) >= launch_cap or left <= 0:
            break
        t = tracks[tid]
        if t["cov"] > (1 if is_double else 0):
            continue
        if is_double and left <= n_uncov_str + 3:
            continue
        if t["cls"] == "unknown" and left <= n_uncov_str + reserve_unknown:
            continue
        launches.append(tid)
        left -= 1
        if t["cls"] == "striker" and t["cov"] == 0:
            n_uncov_str -= 1
        cover(tid)

    # Gun: shoot threats in range, uncovered first, then soonest to hit.
    gun = None
    if ammo > 0:
        best = None
        for tid, t in tracks.items():
            if t["p"] <= 0 or t["r"] > gun_range:
                continue
            key = (1 if t["cov"] > 0 else 0, -t["p"], t["tti"])
            if best is None or key < best[0]:
                best = (key, tid)
        if best is not None:
            gun = best[1]

    return {"intercept": launches, "retarget": retarget, "gun": gun}
