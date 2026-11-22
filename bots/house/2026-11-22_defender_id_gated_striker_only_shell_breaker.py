"""Idea: Hold every interceptor until a track is identified as a striker inside id range, then fire two per tick strictly at strikers in order of time-to-impact, retarget orphaned interceptors to uncovered strikers, and keep the gun on the closest uncovered striker only.

Weakness exploited (2026-11-21_attacker_orbit_hold_picket_drain_ring):
The bot's plan assumes the defender spends interceptors early. Its 16-decoy
picket only drains launches and lifetimes from defenders that fire on unknown
or parked tracks. Against an ID-gated defender the picket is free noise. The
bot pays for it with roughly 14 budget it could have spent on strikers, so it
can field only about 23 strikers.

The pairing vs gun_only shows the structure (mean score_defender 0.264). In
seed 0 the picket decoys hit at ticks 117-119 and cause no harm. Everything
else arrives together at tick 203. The gun alone saturates, because it fires
one shot per tick into about 40 tracks. Here the full shell crosses id range
(150) at once. That gives about 30 ticks of flight, which is enough for 2
launches per tick to put all 20 interceptors onto strikers only. At closing
speed 16 the intercepts land around range 110-60, well before impact. Leftover
strikers are then the gun's job, at short range where its pk is highest.
Decoys draw neither interceptors nor gun ammo.
"""

import math

NAME = "id_gated_striker_only_shell_breaker"
ROLE = "defender"

_DEFAULTS = {
    "id_range": 150.0,
    "gun_range": 100.0,
    "interceptor_speed": 12.0,
    "striker_speed": 4.0,
    "asset_radius": 25.0,
    "interceptor_launches_per_tick": 2,
    "blast_radius": 10.0,
}


def reset(seed=None):
    return None


def _rule(rules, key):
    try:
        v = rules.get(key)
        if v is None:
            return _DEFAULTS[key]
        return v
    except Exception:
        return _DEFAULTS[key]


def _dist(a, b):
    try:
        return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
    except Exception:
        return 1e9


def _range_of(t):
    try:
        r = t.get("range")
        if r is not None:
            return float(r)
        p = t.get("pos") or [0.0, 0.0]
        return math.hypot(float(p[0]), float(p[1]))
    except Exception:
        return 1e9


def act(obs):
    action = {"intercept": [], "retarget": {}, "gun": None}
    try:
        rules = obs.get("rules") or {}
        gun_range = float(_rule(rules, "gun_range"))
        asset_r = float(_rule(rules, "asset_radius"))
        i_speed = float(_rule(rules, "interceptor_speed"))
        s_speed = float(_rule(rules, "striker_speed"))
        per_tick = int(_rule(rules, "interceptor_launches_per_tick"))
        stock = int(obs.get("stock") or 0)
        ammo = int(obs.get("ammo") or 0)
        tracks = obs.get("tracks") or []
        inters = obs.get("interceptors") or []

        by_id = {}
        strikers = []
        for t in tracks:
            try:
                tid = t.get("id")
                if tid is None:
                    continue
                by_id[tid] = t
                if t.get("cls") == "striker":
                    strikers.append(t)
            except Exception:
                continue
        strikers.sort(key=_range_of)

        # Count how many live interceptors cover each striker.
        cover = {}
        orphans = []
        for it in inters:
            try:
                tgt = it.get("target")
                t = by_id.get(tgt)
                if t is not None and t.get("cls") == "striker":
                    cover[tgt] = cover.get(tgt, 0) + 1
                else:
                    orphans.append(it)
            except Exception:
                continue

        # Minimum range at which a launch from the origin still intercepts
        # before impact: (r - asset_r)/s_speed >= r/(i_speed + s_speed).
        closing = i_speed + s_speed
        if closing > s_speed:
            min_r = asset_r * closing / i_speed + 5.0
        else:
            min_r = 40.0

        # Retarget orphans to the nearest uncovered striker.
        retarget = {}
        for it in orphans:
            try:
                ipos = it.get("pos") or [0.0, 0.0]
                best = None
                bestd = 1e18
                for s in strikers:
                    sid = s.get("id")
                    if cover.get(sid, 0) > 0:
                        continue
                    d = _dist(ipos, s.get("pos") or [0.0, 0.0])
                    if d < bestd:
                        bestd = d
                        best = sid
                if best is None:
                    # Fall back to the closest striker overall.
                    for s in strikers:
                        d = _dist(ipos, s.get("pos") or [0.0, 0.0])
                        if d < bestd:
                            bestd = d
                            best = s.get("id")
                if best is not None:
                    retarget[it.get("id")] = best
                    cover[best] = cover.get(best, 0) + 1
            except Exception:
                continue
        action["retarget"] = retarget

        # Launch: strikers only, one per striker by time-to-impact.
        launches = []
        budget = min(per_tick, stock)
        if budget > 0:
            for s in strikers:
                if len(launches) >= budget:
                    break
                sid = s.get("id")
                r = _range_of(s)
                if r < min_r:
                    continue
                if cover.get(sid, 0) == 0:
                    launches.append(sid)
                    cover[sid] = 1
            # Spare launches: double-cover close strikers when stock exceeds
            # the visible striker count (no shell left to save stock for).
            if len(launches) < budget:
                uncovered = sum(1 for s in strikers if cover.get(s.get("id"), 0) == 0)
                spare = stock - len(launches) - uncovered
                if spare > 2:
                    for s in strikers:
                        if len(launches) >= budget:
                            break
                        sid = s.get("id")
                        r = _range_of(s)
                        if r < min_r or r > 90.0:
                            continue
                        if cover.get(sid, 0) == 1:
                            launches.append(sid)
                            cover[sid] = 2
        action["intercept"] = launches

        # Gun: the closest uncovered striker in range, else the closest striker.
        if ammo > 0:
            gun_t = None
            for s in strikers:
                if _range_of(s) <= gun_range and cover.get(s.get("id"), 0) == 0:
                    gun_t = s.get("id")
                    break
            if gun_t is None:
                for s in strikers:
                    if _range_of(s) <= gun_range:
                        gun_t = s.get("id")
                        break
            if gun_t is None:
                # Unknown track inside gun range (should be rare): engage it.
                best = None
                bestr = 1e18
                for t in tracks:
                    try:
                        if t.get("cls") == "unknown":
                            r = _range_of(t)
                            if r <= gun_range and r < bestr:
                                bestr = r
                                best = t.get("id")
                    except Exception:
                        continue
                gun_t = best
            action["gun"] = gun_t
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
    return action
