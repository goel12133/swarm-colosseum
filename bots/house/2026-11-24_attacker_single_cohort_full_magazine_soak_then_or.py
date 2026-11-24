"""Idea: Feed the defender a single all-decoy birth cohort sized to its whole 20-round magazine, keep every striker in a parked orbit outside radar until the sky is clear, then drop one simultaneous striker wall.

Target: 2026-10-31_defender_decoy_carrier_retarget_shell_balancer.

Which part of its logic this attacks:
- Its threat filter is based on cohorts, not on what a track is. Before any
  second cohort exists, every unknown track counts as a threat ("thr = True
  if not later"). So a lone first cohort made only of decoys gets 16
  "carrier" interceptors right away. The carrier/retarget trick only pays
  off if strikers show up while those carriers are still in the air. If
  nothing new appears, the carriers just fly into the decoys and detonate
  near r~330, far outside the 150 id range, so the decoys are never
  identified.
- The 4-round reserve is released when min_tti < 60 for any unclaimed
  threat. I send 20 decoys, not 16. The 4 unclaimed decoys cross r~265 while
  still unidentified, and that triggers the reserve, which also goes into
  the screen. The magazine is empty before a single striker is on radar.
- The strikers loiter on an r~478 orbit, outside the 450 radar, with their
  waypoints steered every tick. They are released together only after no
  interceptor has been airborne for several ticks and no unidentified decoy
  remains. They then arrive as one wall, evenly spread in bearing so a blast
  cannot catch two at once. Without interceptors, the gun gets about 19
  low-pk shots against 25 strikers, and 3 hits breach.

What in the replays shows this is where it breaks:
- Seeds 3 and 4 vs radar_shadow_orbit_decoy_drain: decoy_by_interceptor =
  16, striker_by_interceptor 1-2, then 19 gun shots killed only 2 strikers
  while 4-8 impacted on the same tick (259). The screen soaked the early
  magazine, and only the reserve reached strikers. This bot also drains the
  reserve with 4 extra decoys and denies the retarget window completely.
"""
import math

NAME = "single_cohort_full_magazine_soak_then_orbit_wall"
ROLE = "attacker"

N_DECOY = 20
ORBIT_R = 478.0
LEAD = 0.05
CLEAR_TICKS = 4
MIN_RELEASE_TICK = 40
HARD_RELEASE_TICK = 230

_s = {}


def reset(seed=None):
    _s.clear()
    _s["decoys_sent"] = 0
    _s["strikers_sent"] = 0
    _s["released"] = False
    _s["clear"] = 0
    _s["saw_icp"] = False


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    if "decoys_sent" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    budget = float(obs.get("budget", 0.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    s_cost = float(rules.get("striker_cost", 2.0))
    d_cost = float(rules.get("decoy_cost", 0.5))
    id_range = float(rules.get("id_range", 150.0))
    radar = float(rules.get("radar_range", 450.0))
    orbit_r = max(ORBIT_R, radar + 20.0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])

    drones = obs.get("drones", []) or []
    icps = obs.get("interceptors", []) or []
    if icps:
        _s["saw_icp"] = True

    # ---- launches ----
    launch = []
    n_strike_target = int(max(0.0, (float(rules.get("attacker_budget", 60.0))
                                    - N_DECOY * d_cost)) // s_cost)
    n_strike_target = max(1, n_strike_target)
    while len(launch) < cap:
        if _s["decoys_sent"] < N_DECOY:
            if budget < d_cost - 1e-9:
                break
            i = _s["decoys_sent"]
            bearing = (360.0 * i / N_DECOY) % 360.0
            launch.append({"type": "decoy", "bearing": bearing})
            _s["decoys_sent"] += 1
            budget -= d_cost
        elif not _s["released"]:
            if budget < s_cost - 1e-9:
                break
            i = _s["strikers_sent"]
            bearing = (360.0 * i / n_strike_target + 7.0) % 360.0
            launch.append({"type": "striker", "bearing": bearing})
            _s["strikers_sent"] += 1
            budget -= s_cost
        else:
            break

    # ---- release decision ----
    if not _s["released"]:
        live_far_decoys = 0
        for d in drones:
            if d.get("type") == "decoy":
                p = d.get("pos", [0.0, 0.0])
                r = math.hypot(float(p[0]) - ax, float(p[1]) - ay)
                if r > id_range:
                    live_far_decoys += 1
        if not icps and live_far_decoys == 0:
            _s["clear"] += 1
        else:
            _s["clear"] = 0
        all_sent = (_s["decoys_sent"] >= N_DECOY and
                    (_s["strikers_sent"] >= n_strike_target or budget < s_cost))
        if all_sent and tick >= MIN_RELEASE_TICK and _s["clear"] >= CLEAR_TICKS:
            _s["released"] = True
        if tick >= HARD_RELEASE_TICK:
            _s["released"] = True

    # ---- steering ----
    steer = {}
    for d in drones:
        if d.get("type") != "striker":
            continue
        did = d.get("id")
        if did is None:
            continue
        if _s["released"]:
            if d.get("waypoint") is not None:
                steer[did] = None
            continue
        p = d.get("pos", [0.0, 0.0])
        px, py = float(p[0]) - ax, float(p[1]) - ay
        ang = math.atan2(py, px)
        na = ang + LEAD
        steer[did] = [ax + orbit_r * math.cos(na), ay + orbit_r * math.sin(na)]

    return {"launch": launch, "steer": steer}
