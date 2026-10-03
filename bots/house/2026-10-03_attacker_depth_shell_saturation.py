"""
Idea: Park all 30 strikers just outside gun range in three interleaved depth shells, then release them on one tick so that no two strikers ever share a blast radius and every interceptor kills at most one.

Which part of convergence_blast_scheduler's logic this attacks
--------------------------------------------------------------
The defender gets its strength from a plan built on blast groups. It predicts
radial positions at a deadline radius of about 40 and picks an aim track whose
0.9 * blast neighbourhood covers the most strikers. It waits until neighbouring
strikers converge inside one blast so that each interceptor kills two or three.
Against a single synchronized ring of 30, the neighbour spacing at r = 40 is
about 8.4. That is inside the 9-unit coverage radius, so its 20 interceptors
reach 30 strikers.

This bot removes that geometry and keeps the gun saturation:
* 30 slots, 12 degrees apart, are split into 3 shells, using slot index mod 3.
  The shells stage at radii 118, 130 and 142. Inside one shell, neighbours are
  36 degrees apart, which is 25 units at r = 40 and 15.7 at r = 25. Neighbours
  in adjacent shells are 12 degrees apart and also 12 units apart in depth.
  The blast-group planner therefore finds only singleton groups, and its 20
  interceptors can kill at most about 17 strikers.
* Staging uses the defender's own threat filter against it. Tracks that are
  not closing (vr <= 1) at r >= 100 are dropped from E entirely. Drones pace
  tangentially on their slot, with radial velocity near 0, outside gun range.
  The bot launches nothing at them and its gun cannot reach them.
* All shells release on the same tick. Arrivals fall about 3 ticks apart per
  shell, so roughly 13 surviving strikers reach a one-target gun within a few
  ticks of each other.

What in the replays shows it breaks there
-----------------------------------------
* Every loss to synchronized_ring ended the same way: stock_left 0, 20
  launched, and 21 to 24 interceptor kills. Those extra kills came only from
  converged-ring doubles. The surviving 3 or 4 strikers arrived within 2 ticks
  of each other and the gun managed only 2 to 5 kills.
* The rush replay (26 kills from 4 interceptors) shows the defender's margin
  comes entirely from clustering. Without clusters it is out of interceptors
  well before the last third of the swarm.
"""
import math

NAME = "depth_shell_saturation"
ROLE = "attacker"

N_SLOTS = 30
SHELL_R = [118.0, 130.0, 142.0]
PACE = 5.0

_S = {}


def reset(seed=None):
    global _S
    _S = {"slot_of": {}, "used": set(), "side": {}, "launched": 0,
          "released": False, "launch_idx": 0}


reset()


def _slot_angle(i):
    return 2.0 * math.pi * i / N_SLOTS


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    budget = float(obs.get("budget", 0.0) or 0.0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    cost = float(rules.get("striker_cost", 2.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    spd = float(rules.get("striker_speed", 4.0))

    launch = []
    while (len(launch) < cap and budget >= cost - 1e-9
           and S["launch_idx"] < N_SLOTS):
        i = S["launch_idx"]
        launch.append({"type": "striker", "bearing": _slot_angle(i)})
        budget -= cost
        S["launch_idx"] += 1
    done_launching = (S["launch_idx"] >= N_SLOTS) or (budget < cost - 1e-9)

    drones = obs.get("drones", []) or []
    steer = {}
    all_staged = True
    count = 0
    for d in drones:
        did = d.get("id")
        if did is None or d.get("type") == "decoy":
            continue
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        px, py = float(p[0]) - ax, float(p[1]) - ay
        count += 1
        if did not in S["slot_of"]:
            ang = math.atan2(py, px)
            free = [i for i in range(N_SLOTS) if i not in S["used"]]
            if not free:
                free = list(range(N_SLOTS))

            def adiff(i):
                a = abs(_slot_angle(i) - ang) % (2.0 * math.pi)
                return min(a, 2.0 * math.pi - a)
            best = min(free, key=lambda i: (adiff(i), i))
            S["slot_of"][did] = best
            S["used"].add(best)
            S["side"][did] = 1
        if S["released"]:
            steer[did] = [ax, ay]
            continue
        i = S["slot_of"][did]
        th = _slot_angle(i)
        Rs = SHELL_R[i % 3]
        sx, sy = Rs * math.cos(th), Rs * math.sin(th)
        dist = math.hypot(px - sx, py - sy)
        if dist > 2.0 * PACE:
            all_staged = False
            steer[did] = [sx + ax, sy + ay]
            continue
        tx, ty = -math.sin(th), math.cos(th)
        sd = S["side"].get(did, 1)
        qx, qy = sx + sd * PACE * tx, sy + sd * PACE * ty
        n = math.hypot(qx, qy)
        if n > 1e-6:
            qx, qy = qx * Rs / n, qy * Rs / n
        if math.hypot(px - qx, py - qy) < spd + 0.5:
            sd = -sd
            S["side"][did] = sd
            qx, qy = sx + sd * PACE * tx, sy + sd * PACE * ty
            n = math.hypot(qx, qy)
            if n > 1e-6:
                qx, qy = qx * Rs / n, qy * Rs / n
        steer[did] = [qx + ax, qy + ay]

    if not S["released"]:
        if (done_launching and not launch and count > 0 and all_staged) \
                or tick >= 260:
            S["released"] = True
            for did in list(steer.keys()):
                steer[did] = [ax, ay]

    return {"launch": launch, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
