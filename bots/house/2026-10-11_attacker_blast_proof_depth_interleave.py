"""
Idea: Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.

Which part of convergence_blast_scheduler's logic this attacks
--------------------------------------------------------------
The defender's whole edge is its plan() / blast-group step. It holds its stock
until a radial ring has shrunk to the deadline radius of about 40 (and about 31
for the second layer). At that radius the 12-degree neighbour spacing is about
8.4 units, which is inside its 0.9 * blast coverage radius, so one interceptor
covers two or three strikers. With 20 interceptors against 30 strikers, the
scheduler only wins if those multi-kills happen.

This bot keeps synchronized_ring's 12-degree slotting and simultaneous radial
dive, but alternate slots form a second shell that trails 12 units behind. At
r=40 the nearest neighbour is about sqrt(8.4^2 + 12^2) = 14.6 away. At r=31 it
is about 13.5 away. A same-shell neighbour is 24 degrees away, which is 16.7 at
r=40 and 13 at r=31. No predicted neighbourhood ever holds two strikers, so
every blast group is a single. The depth offset is only 3 ticks, so arrival
stays compressed, and that compression is what starves the one-target gun.
Strikers loiter at r=300 with near-zero closing speed. Those tracks are not
"closing" (vr <= 1 and r >= 100), so the defender spends nothing and builds no
filter history on the real dive until it starts.

What in the replays shows it breaks there
-----------------------------------------
* Both close calls (depth_shell_saturation seed 6, staggered_trishell seed 3)
  are breaches in which interceptors got only 13 and 18 kills from 20
  launches, meaning mostly singles. The gun managed only 5 to 8 kills from
  51 to 59 shots, and the three impacts landed within 1 to 2 ticks.
* synchronized_ring is still the scheduler's worst opponent (mean 0.40). The
  compressed arrival hurts it, and only the convergence multi-kills save it.
  Remove the multi-kills and keep the compression, and the arithmetic flips:
  about 17 single kills plus a starved gun leaves at least 3 strikers to impact.
"""
import math

NAME = "blast_proof_depth_interleave"
ROLE = "attacker"

N = 30
STAGE_R = 300.0
SHELL_DELAY = 3
_S = {}


def reset(seed=None):
    global _S
    _S = {"launched": 0, "slots": {}, "free": list(range(N)),
          "release": None}


reset()


def _ang(i):
    return 2.0 * math.pi * i / N


def _act(obs):
    S = _S
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    budget = float(obs.get("budget", 0.0) or 0.0)
    cost = float(rules.get("striker_cost", 2.0))
    cap = int(rules.get("attacker_launches_per_tick", 4))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    drones = obs.get("drones", []) or []

    # launches
    launch = []
    while S["launched"] < N and budget >= cost - 1e-9 and len(launch) < cap:
        launch.append({"type": "striker", "bearing": _ang(S["launched"])})
        S["launched"] += 1
        budget -= cost

    # slot assignment for new strikers
    alive = []
    for d in drones:
        if d.get("type", "striker") != "striker":
            continue
        did = d.get("id")
        p = d.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        px, py = float(p[0]) - ax, float(p[1]) - ay
        if did not in S["slots"] and S["free"]:
            a = math.atan2(py, px)

            def adiff(i):
                x = (a - _ang(i)) % (2 * math.pi)
                return min(x, 2 * math.pi - x)
            best = min(S["free"], key=lambda i: (adiff(i), i))
            S["free"].remove(best)
            S["slots"][did] = best
        if did in S["slots"]:
            alive.append((did, px, py, S["slots"][did]))

    # release decision
    done_launching = S["launched"] >= N or budget < cost
    if S["release"] is None and done_launching and alive:
        staged = True
        for did, px, py, s in alive:
            sx, sy = STAGE_R * math.cos(_ang(s)), STAGE_R * math.sin(_ang(s))
            if math.hypot(px - sx, py - sy) > 6.0:
                staged = False
                break
        if staged or tick >= 380:
            S["release"] = tick

    steer = {}
    rel = S["release"]
    sgn = 1.0 if tick % 2 == 0 else -1.0
    for did, px, py, s in alive:
        shell = s % 2
        if rel is not None and tick >= rel + shell * SHELL_DELAY:
            steer[did] = None
            continue
        a = _ang(s)
        cx, cy = math.cos(a), math.sin(a)
        sx, sy = STAGE_R * cx, STAGE_R * cy
        dist = math.hypot(px - sx, py - sy)
        if dist > 6.0:
            wx, wy = sx, sy
            if dist < 9.0:
                # aim past the staging point so we never "arrive" and dive
                k = 10.0 / max(dist, 1e-6)
                wx, wy = px + (sx - px) * k, py + (sy - py) * k
        else:
            tx, ty = -cy, cx
            wx, wy = sx + sgn * 10.0 * tx, sy + sgn * 10.0 * ty
        steer[did] = [wx + ax, wy + ay]

    return {"launch": launch, "steer": steer}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}
