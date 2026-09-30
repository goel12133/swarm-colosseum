"""Idea: Pre-launch interceptors at unidentified tracks just before they cross id range, timed so the intercept lands inside id range, then retarget every shot whose track is revealed as a decoy onto an uncovered striker.

NAME: reveal_timed_prelaunch

Core idea: the real bottleneck against a synchronized ring is the launch cap,
not the magazine. When a whole ring crosses the 150 u identification range at
once, a defender that waits for identification can put only 2 interceptors in
the air per tick. The last strikers get engaged too late. This bot moves
launches earlier in time without spending them on decoys:

  * An interceptor (speed 12) launched at a closing track (speed 4) at range R
    meets it at about 0.75 R. If it launches while the track is at about 185 u
    or less, the meeting point is inside 150 u. So the track is always
    identified several ticks before the interceptor arrives.
  * When the reveal says "decoy", that interceptor is immediately retargeted to
    the most urgent striker that has no coverage. The launch slot already used
    is not lost; only the decoy is ignored.
  * Retargeting is a greedy match of free interceptors to uncovered strikers,
    ordered by urgency, respecting remaining interceptor lifetime.
  * Speculative launches are capped so that the remaining stock always covers
    the strikers that are already confirmed and uncovered.

How it differs from each existing defender:
  * miss_budget_scheduler: that bot never fires outside id range and spends
    its thinking on pairing shots against misses. This bot's lever is
    throughput. It fires *before* identification, on a timing rule that
    guarantees the reveal arrives before impact, and it recycles decoy-bound
    shots.
  * discriminating_ledger: that bot fires only at confirmed strikers and only
    retargets when a target disappears. This bot fires at unknowns on purpose
    and retargets on *reveal*, not on death.
  * layered: that bot engages unknowns only when waiting would cost the
    intercept, then commits to them. This bot engages unknowns whenever the
    geometry guarantees a reveal before contact, then un-commits on decoys.
  * identify_then_engage: that bot waits for identification and accepts the
    lost stand-off and launch-cap congestion. This bot spreads launches into
    the ticks before identification.
  * nearest_first: that bot commits on range alone and eats decoys. This bot
    uses range only to time a launch that it can still redirect.
  * gun_only: this bot relies on interceptors. The gun is a last layer against
    strikers, and prefers strikers with no interceptor coverage.
"""

import math

NAME = "reveal_timed_prelaunch"
ROLE = "defender"

PRELAUNCH_RANGE = 185.0
MIN_PRELAUNCH_RANGE = 150.0


def reset(seed=None):
    pass


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def act(obs):
    action = {"intercept": [], "retarget": {}, "gun": None}
    try:
        rules = obs.get("rules", {}) or {}
        tracks = obs.get("tracks", []) or []
        ints = obs.get("interceptors", []) or []
        stock = int(obs.get("stock", 0) or 0)
        ammo = int(obs.get("ammo", 0) or 0)
        launch_cap = int(rules.get("interceptor_launches_per_tick", 2))
        lifetime = float(rules.get("interceptor_lifetime", 90))
        i_speed = float(rules.get("interceptor_speed", 12.0))
        gun_range = float(rules.get("gun_range", 100.0))
        id_range = float(rules.get("id_range", 150.0))

        by_id = {}
        for t in tracks:
            by_id[t["id"]] = t

        def approaching(t):
            p = t.get("pos", [0, 0])
            v = t.get("vel", [0, 0])
            return (p[0] * v[0] + p[1] * v[1]) < 0 or t.get("range", 1e9) < 60

        # Coverage from interceptors whose target is a live, non-decoy track.
        coverage = {}
        free = []
        for it in ints:
            tgt = it.get("target")
            t = by_id.get(tgt)
            if t is None or t.get("cls") == "decoy":
                free.append(it)
            else:
                coverage[tgt] = coverage.get(tgt, 0) + 1

        strikers = [t for t in tracks if t.get("cls") == "striker"]
        strikers.sort(key=lambda t: t.get("range", 1e9))
        uncovered = [t for t in strikers if coverage.get(t["id"], 0) == 0]

        # Greedy retarget of free (decoy-bound / orphaned) interceptors.
        still_uncovered = []
        for s in uncovered:
            best = None
            best_d = 1e18
            for it in free:
                d = _dist(it.get("pos", [0, 0]), s.get("pos", [0, 0]))
                remain = lifetime - float(it.get("age", 0))
                if d / max(i_speed - 4.0, 1.0) > remain:
                    continue
                if d < best_d:
                    best_d = d
                    best = it
            if best is not None:
                action["retarget"][best["id"]] = s["id"]
                free.remove(best)
                coverage[s["id"]] = 1
            else:
                still_uncovered.append(s)

        # Leftover free interceptors: send toward nearest unknown in window.
        unknowns = [t for t in tracks if t.get("cls") == "unknown" and approaching(t)]
        unknowns.sort(key=lambda t: t.get("range", 1e9))
        for it in free:
            best = None
            best_d = 1e18
            for u in unknowns:
                if coverage.get(u["id"], 0) > 0:
                    continue
                d = _dist(it.get("pos", [0, 0]), u.get("pos", [0, 0]))
                if d < best_d:
                    best_d = d
                    best = u
            if best is not None:
                action["retarget"][it["id"]] = best["id"]
                coverage[best["id"]] = 1

        # Launches: confirmed uncovered strikers first, then timed prelaunches.
        launches = []
        avail = min(launch_cap, stock)
        for s in still_uncovered:
            if len(launches) >= avail:
                break
            launches.append(s["id"])
            coverage[s["id"]] = 1

        remaining_stock = stock - len(launches)
        need_reserve = max(0, len(still_uncovered) - len(launches))
        for u in unknowns:
            if len(launches) >= avail:
                break
            r = u.get("range", 1e9)
            if r > PRELAUNCH_RANGE or r < MIN_PRELAUNCH_RANGE - 20:
                continue
            if coverage.get(u["id"], 0) > 0:
                continue
            if remaining_stock - 1 < need_reserve:
                break
            launches.append(u["id"])
            coverage[u["id"]] = 1
            remaining_stock -= 1

        # Spare capacity: second shot on close strikers when stock is healthy.
        if len(launches) < avail:
            n_unknown_near = sum(1 for u in unknowns if u.get("range", 1e9) < 300)
            for s in strikers:
                if len(launches) >= avail:
                    break
                if s.get("range", 1e9) > 110:
                    continue
                if coverage.get(s["id"], 0) >= 2:
                    continue
                if remaining_stock - 1 < len(strikers) + n_unknown_near // 2:
                    break
                launches.append(s["id"])
                coverage[s["id"]] = coverage.get(s["id"], 0) + 1
                remaining_stock -= 1

        action["intercept"] = launches

        # Gun: strikers only; prefer thinly covered, then closest.
        if ammo > 0:
            in_range = [t for t in tracks
                        if t.get("range", 1e9) <= gun_range
                        and t.get("cls") != "decoy"]
            if in_range:
                def gkey(t):
                    cls_pen = 0 if t.get("cls") == "striker" else 1
                    return (cls_pen, min(coverage.get(t["id"], 0), 1),
                            t.get("range", 1e9))
                in_range.sort(key=gkey)
                tgt = in_range[0]
                if tgt.get("cls") == "striker" or tgt.get("range", 1e9) < id_range:
                    action["gun"] = tgt["id"]
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
    return action
