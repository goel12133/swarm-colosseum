"""Idea: Treat a single-bearing stream as one target, and spend each interceptor on whichever track has the most uncovered threat inside its blast radius.

Weakness exploited: rush sends all 30 strikers down one corridor at 4 per tick.
That packs them into a dense column only a few units deep per launch tick, so a
single 10-unit blast can catch several strikers at once. The pairing rush vs
gun_only shows the weakness (mean score_defender 0.272). In seed 0, gun_only
fired no interceptors and kept all 20 in stock. Its gun killed only 4 strikers,
and the asset was breached at tick 118. Rush gets no protection from decoys
and no spread across bearings, so cluster-weighted blast targeting from long
range should thin the column well before it reaches gun range.

Method:
- Each tick, score every track by the class-weighted, urgency-weighted threat
  near it that is not already covered by an in-flight interceptor.
- Launch at the best-scoring tracks, up to the per-tick cap.
- Retarget interceptors whose target track has vanished.
- Keep a small reserve of stock for close-in leakers.
- Point the gun at the most urgent striker inside gun range.
"""

import math

NAME = "cluster_blast_column_breaker"
ROLE = "defender"

_COVER_R = 9.0      # a track this close to an interceptor's target counts as covered
_CLUSTER_R = 11.0   # neighbourhood used to score blast value (blast 10 + track noise)


def reset(seed):
    pass


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _w(cls):
    if cls == "striker":
        return 1.0
    if cls == "decoy":
        return 0.05
    return 0.75


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    gun_range = float(rules.get("gun_range", 100.0))
    lpt = int(rules.get("interceptor_launches_per_tick", 2))
    total_stock = int(rules.get("interceptor_stock", 20)) or 20

    action = {"intercept": [], "retarget": {}, "gun": None}
    if not tracks:
        return action

    tracks = sorted(tracks, key=lambda t: (float(t.get("range", 0.0)), str(t.get("id"))))
    by_id = {t["id"]: t for t in tracks}
    pos = {t["id"]: (float(t["pos"][0]), float(t["pos"][1])) for t in tracks}

    # Covered tracks: anything near the target of an interceptor already in flight.
    covered = set()
    orphans = []
    for it in inters:
        tgt = it.get("target")
        if tgt in by_id:
            tp = pos[tgt]
            for t in tracks:
                if _d(pos[t["id"]], tp) <= _COVER_R:
                    covered.add(t["id"])
        else:
            orphans.append(it)

    def urgency(t):
        r = float(t.get("range", 450.0))
        return 1.0 + max(0.0, (450.0 - r)) / 150.0

    def value(tid, cov):
        p = pos[tid]
        s = 0.0
        for t in tracks:
            oid = t["id"]
            if oid in cov:
                continue
            if _d(pos[oid], p) <= _CLUSTER_R:
                s += _w(t.get("cls", "unknown")) * urgency(t)
        return s

    def eligible(t, stock_now):
        cls = t.get("cls", "unknown")
        r = float(t.get("range", 450.0))
        if cls == "decoy":
            return False
        reserve = max(2, total_stock // 8)
        if stock_now <= reserve:
            # Hold the reserve for close leakers and confirmed strikers.
            return r < 220.0 or cls == "striker"
        return True

    def pick(cov, stock_now):
        best, bestv = None, 0.0
        for t in tracks:
            tid = t["id"]
            if tid in cov or not eligible(t, stock_now):
                continue
            v = value(tid, cov)
            if v > bestv + 1e-9:
                best, bestv = tid, v
        return best, bestv

    def cover(tid, cov):
        p = pos[tid]
        for t in tracks:
            if _d(pos[t["id"]], p) <= _COVER_R:
                cov.add(t["id"])

    # Retarget orphaned interceptors to the best uncovered cluster near them.
    for it in sorted(orphans, key=lambda x: str(x.get("id"))):
        ip = it.get("pos") or [0.0, 0.0]
        ip = (float(ip[0]), float(ip[1]))
        best, bestv = None, 0.0
        for t in tracks:
            tid = t["id"]
            if tid in covered or t.get("cls") == "decoy":
                continue
            v = value(tid, covered) / (1.0 + _d(ip, pos[tid]) / 200.0)
            if v > bestv:
                best, bestv = tid, v
        if best is not None:
            action["retarget"][it["id"]] = best
            cover(best, covered)

    # New launches.
    s = stock
    for _ in range(max(0, lpt)):
        if s <= 0:
            break
        tid, v = pick(covered, s)
        if tid is None:
            break
        t = by_id[tid]
        # Avoid wasting shots on lone, far, unidentified tracks once stock is thin.
        if (t.get("cls") == "unknown" and v < 1.5 and s < total_stock // 2
                and float(t.get("range", 450.0)) > 300.0):
            break
        action["intercept"].append(tid)
        cover(tid, covered)
        s -= 1

    # Gun: most urgent non-decoy track in range, strikers first.
    if ammo > 0:
        best, bestk = None, None
        for t in tracks:
            r = float(t.get("range", 1e9))
            if r > gun_range:
                continue
            cls = t.get("cls", "unknown")
            pri = 0 if cls == "striker" else (1 if cls == "unknown" else 2)
            k = (pri, r, str(t["id"]))
            if bestk is None or k < bestk:
                best, bestk = t["id"], k
        if best is not None and (bestk[0] < 2 or ammo > 40):
            action["gun"] = best

    return action
