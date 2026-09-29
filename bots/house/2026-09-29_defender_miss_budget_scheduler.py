"""
NAME: miss_budget_scheduler

Core idea: plan for misses before they happen, and order launches by deadline.

An interceptor hits with p = 0.85, so about one shot in seven misses. For every
confirmed striker this bot works out how many more one-at-a-time intercept
attempts still fit before the striker reaches a safety radius. It counts the
engagement time, the time to notice a miss, and the relaunch from the origin
(the "miss budget").

  * If at least two sequential tries still fit, it launches one interceptor.
  * If only one try fits, it launches a simultaneous pair. Surviving both
    shots is 0.15^2, about 2%.
  * If zero tries fit, it still launches one and leans on the gun.

Launches are ordered by earliest deadline (time until impact), because only
two can go per tick. The magazine is rationed: pairs are dropped whenever
stock is not comfortably above the number of strikers still alive.

The gun fires only at strikers. It prefers the one whose in-flight coverage
will not resolve before the safety radius, and breaks ties by the closest,
most urgent striker.

How it differs from each existing defender:
  * discriminating_ledger: that bot uses exactly one interceptor per striker
    and relaunches only after the first one is gone. This bot predicts, from
    the striker's range and speed, whether a relaunch would even be in time.
    When it would not, it fires a pair up front. It also orders launches by
    deadline instead of reacting.
  * identify_then_engage: that bot shares the "confirmed strikers only"
    filter, but it has no model of whether a miss can be recovered. It
    commits one shot and hopes.
  * layered: that bot holds a magazine reserve and engages unknowns early by
    time to impact. This bot never fires at unknowns outside id range. It
    varies shots per target (1 or 2) based on the sequential tries left, not
    on a reserve fraction.
  * nearest_first: that bot is range-greedy and ignores class. This bot is
    class-strict and deadline-ordered.
  * gun_only: this bot uses interceptors, and uses the gun only as the last
    layer against strikers.
"""

import math

NAME = "miss_budget_scheduler"
ROLE = "defender"


def reset(seed=None):
    pass


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def _closing(tr):
    try:
        px, py = tr["pos"]
        vx, vy = tr.get("vel") or (0.0, 0.0)
        r = math.hypot(px, py)
        if r < 1e-6:
            return 4.0
        c = -(px * vx + py * vy) / r
        return c if c > 0.5 else 0.5
    except Exception:
        return 4.0


def _opportunities(r, vi, vs, r_safe, lag):
    n = 0
    for _ in range(6):
        t = r / (vi + vs)
        r = r - vs * t - vs * lag
        if r <= r_safe:
            break
        n += 1
    return n


def act(obs):
    action = {"intercept": [], "retarget": {}, "gun": None}
    try:
        rules = obs.get("rules", {}) or {}
        vi = _f(rules.get("interceptor_speed", 12.0), 12.0)
        asset_r = _f(rules.get("asset_radius", 25.0), 25.0)
        id_range = _f(rules.get("id_range", 150.0), 150.0)
        gun_range = _f(rules.get("gun_range", 100.0), 100.0)
        launch_cap = int(_f(rules.get("interceptor_launches_per_tick", 2), 2))
        r_safe = asset_r + 35.0
        lag = 2.0

        tracks = obs.get("tracks", []) or []
        inters = obs.get("interceptors", []) or []
        stock = int(_f(obs.get("stock", 0), 0))
        ammo = int(_f(obs.get("ammo", 0), 0))

        by_id = {}
        threats = {}
        for tr in tracks:
            tid = tr.get("id")
            by_id[tid] = tr
            cls = tr.get("cls", "unknown")
            rng = _f(tr.get("range"), 1e9)
            if cls == "striker" or (cls == "unknown" and rng <= id_range):
                threats[tid] = tr

        # Current coverage of each threat, plus interceptors needing a new target.
        cover = {tid: [] for tid in threats}
        orphans = []
        for it in inters:
            tgt = it.get("target")
            if tgt in threats:
                cover[tgt].append(it)
            else:
                orphans.append(it)

        n_threats = len(threats)

        def need(tid):
            tr = threats[tid]
            r = _f(tr.get("range"), 1e9)
            vs = _closing(tr)
            inflight = cover[tid]
            if inflight:
                if len(inflight) >= 2:
                    return 0
                # Estimate the range at which the in-flight shot resolves.
                try:
                    ip = inflight[0].get("pos") or (0.0, 0.0)
                    tp = tr["pos"]
                    d = math.hypot(tp[0] - ip[0], tp[1] - ip[1])
                except Exception:
                    d = r
                t = d / (vi + vs)
                r_res = r - vs * t - vs * lag
                if r_res > r_safe and _opportunities(r_res, vi, vs, r_safe, lag) >= 1:
                    return 0
                if r_res > r_safe:
                    return 0
                return 1 if stock > n_threats else 0
            n = _opportunities(r, vi, vs, r_safe, lag)
            if n >= 2:
                return 1
            if n == 1:
                return 2 if stock >= n_threats + 2 else 1
            return 1 if r > asset_r + 5 else 0

        def deadline(tid):
            tr = threats[tid]
            return (_f(tr.get("range"), 1e9) - asset_r) / _closing(tr)

        order = sorted(threats.keys(), key=deadline)
        deficit = {tid: need(tid) for tid in order}

        # Send orphaned interceptors to the most urgent threats with a deficit.
        for it in orphans:
            iid = it.get("id")
            ip = it.get("pos") or (0.0, 0.0)
            best, best_score = None, None
            for tid in order:
                if deficit[tid] <= 0:
                    continue
                tp = threats[tid]["pos"]
                d = math.hypot(tp[0] - ip[0], tp[1] - ip[1])
                score = deadline(tid) + d / (vi + 4.0) * 0.5
                if best_score is None or score < best_score:
                    best, best_score = tid, score
            if best is not None:
                action["retarget"][iid] = best
                deficit[best] -= 1
                cover[best].append(it)

        # Fresh launches, earliest deadline first, within the per-tick cap and stock.
        launches = []
        avail = min(launch_cap, stock)
        for tid in order:
            while deficit[tid] > 0 and len(launches) < avail:
                launches.append(tid)
                deficit[tid] -= 1
            if len(launches) >= avail:
                break
        action["intercept"] = launches

        # Gun: strikers only, prefer the ones coverage will not reach in time.
        if ammo > 0:
            best, best_key = None, None
            for tid, tr in threats.items():
                r = _f(tr.get("range"), 1e9)
                if r > gun_range:
                    continue
                vs = _closing(tr)
                covered_in_time = False
                for it in cover.get(tid, []):
                    try:
                        ip = it.get("pos") or (0.0, 0.0)
                        tp = tr["pos"]
                        d = math.hypot(tp[0] - ip[0], tp[1] - ip[1])
                        if r - vs * d / (vi + vs) > asset_r + 20:
                            covered_in_time = True
                            break
                    except Exception:
                        pass
                fresh = tid in launches
                key = (1 if (covered_in_time or fresh) else 0, r / vs)
                if best_key is None or key < best_key:
                    best, best_key = tid, key
            action["gun"] = best
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
    return action
