"""Idea: Fire nothing at any track until the radar's 150-range ID confirms it is a striker, so the whole 20-round magazine and the gun are saved for the single synchronized striker wave.

Target: 2026-11-15_attacker_attacker_radar_shadow_orbit_decoy_drain.

What we attack
--------------
The attacker's plan depends on the defender spending stock on its 16-decoy ring
at radius 190. That ring sits outside ID range, so the decoys show as "unknown".
The strikers wait in an orbit at radius 485, outside the radar. They are
released only when the attacker sees max_ic > 0 and then zero interceptors for
4 or more ticks. If it never sees an interceptor, the "idle" branch fires
instead: the strikers are released at decoy_release_tick + 80. By then every
decoy has already hit the asset, and decoy impacts do no damage. The strike then
arrives into a full magazine. It is a single ring of 26 tracks, all inbound at
the same speed from about 450.

Replay evidence
---------------
In its closest calls (parked_hover_ring_doublecover, seeds 1 and 3), every decoy
impact is at tick 174 and asset_hp stays at 30, so decoys are harmless. That
defender still used 9 and 8 gun kills on decoys, and 49 and 60 shots overall.
It then needed 20 and 22 interceptor kills on strikers to survive. The
defenders it crushes (loiter_then_collapse 0.04, contracting_ring 0.04) are the
ones that emptied their magazines on the decoy ring.

How this bot works
------------------
* It never engages an "unknown" track that is beyond ID range. The decoys at 190
  are never shot. When they are released, they reveal as decoys at 150 and are
  ignored, including by the gun.
* Strikers are engaged once identified, nearest first, at 2 launches per tick.
  The 20 interceptors are spread across about 12 ticks. Intercepts happen around
  radius 110 to 80, which overlaps the gun window.
* An interceptor whose target died, or turned out to be a decoy, is retargeted
  to the nearest uncovered striker.
* The gun fires only at non-decoy tracks. Uncovered strikers come first, then
  the closest.
* Fallback for other attackers: an unknown inbound track that comes within the
  urgent radius is treated as a threat.
"""

import math

NAME = "defender_id_gate_magazine_vault"
ROLE = "defender"

_S = {}


def reset(seed=0):
    _S.clear()
    _S["seen"] = {}


reset(0)


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    tracks = obs.get("tracks", []) or []
    ics = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    id_range = float(rules.get("id_range", 150.0))
    a_rad = float(rules.get("asset_radius", 25.0))
    urgent_r = max(a_rad + 40.0, id_range - 40.0)

    info = {}
    for t in tracks:
        tid = t.get("id")
        px, py = (t.get("pos") or [0.0, 0.0])[:2]
        vx, vy = (t.get("vel") or [0.0, 0.0])[:2]
        dx, dy = px - ax, py - ay
        r = t.get("range")
        r = float(r) if r is not None else math.hypot(dx, dy)
        rn = max(1e-6, math.hypot(dx, dy))
        rv = (dx * vx + dy * vy) / rn
        cls = t.get("cls", "unknown")
        if tid not in _S["seen"]:
            _S["seen"][tid] = tick
        info[tid] = (px, py, r, rv, cls)

    def is_threat(tid):
        px, py, r, rv, cls = info[tid]
        if cls == "striker":
            return True
        if cls == "decoy":
            return False
        # unknown: only if dangerously close and inbound (fallback)
        return r <= urgent_r and rv < -0.5

    threats = [tid for tid in info if is_threat(tid)]
    threats.sort(key=lambda k: info[k][2])

    covered = {}
    for ic in ics:
        tg = ic.get("target")
        if tg in info and is_threat(tg):
            covered[tg] = covered.get(tg, 0) + 1

    # retarget interceptors that lost their target or hold a decoy
    retarget = {}
    for ic in ics:
        tg = ic.get("target")
        if tg in info and is_threat(tg):
            continue
        ipos = (ic.get("pos") or [ax, ay])[:2]
        best, bd = None, 1e18
        for tid in threats:
            if covered.get(tid, 0) > 0:
                continue
            px, py = info[tid][0], info[tid][1]
            d = math.hypot(px - ipos[0], py - ipos[1])
            if d < bd:
                bd, best = d, tid
        if best is None and threats:
            best = threats[0]
        if best is not None and best != tg:
            retarget[ic.get("id")] = best
            covered[best] = covered.get(best, 0) + 1

    # launches: one per uncovered threat, nearest first
    intercept = []
    slots = min(per_tick, stock)
    for tid in threats:
        if slots <= 0:
            break
        if covered.get(tid, 0) == 0:
            intercept.append(tid)
            covered[tid] = 1
            slots -= 1
    # leaker double-cover inside gun range if stock is left
    if slots > 0:
        for tid in threats:
            if slots <= 0:
                break
            if info[tid][2] < gun_range * 0.8 and covered.get(tid, 0) == 1 \
                    and tid not in intercept:
                intercept.append(tid)
                covered[tid] = 2
                slots -= 1

    # gun: non-decoy tracks in range, uncovered first, then closest
    gun = None
    if ammo > 0:
        cands = []
        for tid, (px, py, r, rv, cls) in info.items():
            if cls == "decoy" or r > gun_range:
                continue
            cands.append((1 if covered.get(tid, 0) > 0 and tid not in intercept
                          else 0, r, tid))
        if cands:
            cands.sort(key=lambda c: (c[0], c[1]))
            gun = cands[0][2]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
