"""Idea: Park a ring of cheap decoys permanently in the radar-only band so they are never identified, which keeps the defender in its "scarce" mode and pulls its commit radius inward, then dive a pre-staged, evenly spaced striker ring all at once.

Why this is not the obvious counter:
- The obvious answer to convergent_deadline_packer is to beat its blast packing. That
  means spreading strikers or depth-shelling them so no blast covers two, or arriving
  faster than its 2-per-tick launch cap. The ladder already does all of that.
- This bot goes after a different part of the defender: its launch-timing bookkeeping.
  The defender sets scarce = (uncovered strikers + 0.5 * unknown tracks) > stock. When
  scarce is true, it moves its commit radius from asset+42 down to asset+20.
- Decoys cost 0.5. Here they orbit forever at radius 330, inside radar range (450) but
  outside id range (150). They stay "unknown" for the whole match. The defender never
  shoots them, because interceptors only go at strikers and the gun only reaches 100.
- Because they are counted as unknowns, they keep the scarce flag on long after the
  striker count alone would have turned it off. So every interception is planned close
  to the asset. A 15% miss then leaves almost no time for a second interceptor before
  impact, and only the gun is left.
- The strikers spiral into fixed slots on a radius-260 ring. The slots are spaced so
  that no predicted blast catches two strikers, even near the asset. Once every striker
  is on station, they all dive together. They enter id range and hit deadline pressure
  at the same moment, while the magazine (20) is smaller than the striker count (22).
Deterministic, standard library only.
"""

import math

NAME = "unknown_ballast_scarcity_squeeze"
ROLE = "attacker"

_S = {}


def reset(seed=None):
    _S.clear()


def _st():
    if "init" not in _S:
        _S["init"] = True
        _S["ls"] = 0          # strikers launched
        _S["ld"] = 0          # decoys launched
        _S["slot"] = {}       # drone id -> slot index
        _S["used"] = {"striker": set(), "decoy": set()}
        _S["dive"] = False
    return _S


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    st = _st()
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0))
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    ax, ay = float(ax), float(ay)
    sc = float(rules.get("striker_cost", 2.0))
    dc = float(rules.get("decoy_cost", 0.5))
    total = float(rules.get("attacker_budget", 60.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    id_range = float(rules.get("id_range", 150.0))
    radar = float(rules.get("radar_range", 450.0))
    spd = float(rules.get("striker_speed", 4.0))

    NS = min(22, int(total // sc))
    ND = max(0, int((total - NS * sc + 1e-9) // dc))
    RS = max(id_range + 100.0, 260.0)
    RD = min(radar - 60.0, max(id_range + 150.0, 330.0))
    wS = 0.5 * spd / RS
    wD = 0.5 * spd / RD
    params = {"striker": (NS, RS, wS, 0.0), "decoy": (ND, RD, wD, math.pi / max(1, ND))}

    # Launches: strikers first, then the decoy ring.
    launch = []
    rem = budget
    while len(launch) < cap:
        if st["ls"] < NS and rem >= sc - 1e-9:
            k = st["ls"]
            launch.append({"type": "striker", "bearing": 2 * math.pi * k / max(1, NS)})
            st["ls"] += 1
            rem -= sc
        elif st["ld"] < ND and rem >= dc - 1e-9:
            k = st["ld"]
            launch.append({"type": "decoy",
                           "bearing": 2 * math.pi * k / max(1, ND) + math.pi / max(1, ND)})
            st["ld"] += 1
            rem -= dc
        else:
            break

    drones = obs.get("drones", []) or []
    steer = {}
    alive_ids = set()
    all_on_station = True
    n_strikers = 0

    plans = []
    for d in drones:
        did = d.get("id")
        typ = d.get("type", "striker")
        if typ not in params:
            typ = "striker"
        alive_ids.add(did)
        p = d.get("pos") or [ax, ay]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        N, R, w, off = params[typ]
        N = max(1, N)
        if did not in st["slot"]:
            ang_now = math.atan2(y, x)
            best, bd = None, None
            for k in range(N):
                if k in st["used"][typ]:
                    continue
                sa = 2 * math.pi * k / N + off + w * tick
                dd = abs(_wrap(sa - ang_now))
                if bd is None or dd < bd:
                    best, bd = k, dd
            if best is None:
                best = len(st["slot"]) % N
            st["slot"][did] = best
            st["used"][typ].add(best)
        k = st["slot"][did]
        sa = 2 * math.pi * k / N + off + w * tick
        sx, sy = R * math.cos(sa), R * math.sin(sa)
        dist = math.hypot(sx - x, sy - y)
        if typ == "striker":
            n_strikers += 1
            if dist > 20.0:
                all_on_station = False
        plans.append((did, typ, x, y, sa, R, sx, sy, dist))

    # Free slots of drones that died.
    for did in list(st["slot"].keys()):
        if did not in alive_ids:
            del st["slot"][did]
    used = {"striker": set(), "decoy": set()}
    for d in drones:
        did = d.get("id")
        typ = d.get("type", "striker")
        if typ not in used:
            typ = "striker"
        if did in st["slot"]:
            used[typ].add(st["slot"][did])
    st["used"] = used

    if not st["dive"]:
        if (st["ls"] >= NS and n_strikers > 0 and all_on_station) or tick >= 230:
            st["dive"] = True

    for (did, typ, x, y, sa, R, sx, sy, dist) in plans:
        if typ == "striker" and st["dive"]:
            steer[did] = [ax, ay]
            continue
        if dist > 20.0:
            wx, wy = sx, sy
        else:
            la = sa + 15.0 / R
            wx, wy = R * math.cos(la), R * math.sin(la)
        steer[did] = [wx + ax, wy + ay]

    return {"launch": launch, "steer": steer}
