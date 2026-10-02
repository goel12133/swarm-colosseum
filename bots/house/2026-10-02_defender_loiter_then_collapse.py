"""
Idea: Launch interceptors after the ring is released, park them over the asset by retargeting them between two opposite tracks every tick, then fire every one at the same moment at the closing ring so each blast covers three strikers.

Which part of synchronized_ring this attacks
--------------------------------------------
The release logic. synchronized_ring holds all 30 strikers at radius 190.
They are evenly spaced 12 degrees apart. It then sets `steer[did] = asset`
for every drone on the same tick. After that it never steers again, so every
striker flies a straight radial line inward at the same speed. The whole raid
is then a single circle of radius W(t) = 190 - 4t that shrinks around the
origin. The arc spacing between neighbours is 2*pi*W/30, about 0.21*W. At
W of about 35 the spacing is about 7.3, which is less than the blast radius
of 10. One blast centred on a striker also catches both of its neighbours.
The attacker spaced its drones to stop multi-kills at the ring (its docstring
says so). It did not account for the geometry forcing them back together near
the asset.

What the replays show
---------------------
* In every winning match the stock ran out (stock_left 0, 20 launched) before
  the end. 16 to 18 interceptor kills came from 20 interceptors, which is
  about one kill per interceptor. Defenders that fire as strikers enter id or
  engagement range meet them where they are still 15 to 25 units apart.
* The only defender that held (convergence_blast_scheduler, defended with
  hp 30) got 22 to 25 interceptor kills from 20 interceptors. Kills above one
  per interceptor are the whole game here. But the launch cap is 2 per tick.
  Launching straight at the wave spreads meeting radii over a span of about
  30 units, so most of its blasts still go off where the spacing is too wide.
  It still loses about 60% of its matches.

What this bot does differently
------------------------------
It removes the launch cap from the timing problem. Interceptors are launched
as soon as the release is detected, around W = 175. Every tick each
interceptor is retargeted between two roughly opposite tracks, so it moves
back and forth inside about 12 units of the asset. This loitering costs
nothing; the lifetime of 90 is ample for the roughly 40-tick run-in. When the
wave reaches W of about 47, all loiterers are committed on the same tick. The
targets are the ring members sorted by angle, at indices round(j*N/k). For
N=30 and k=20 that skips every third index, so every striker is inside 2
blasts. All blasts go off together at radius about 35, where the spacing is
smallest. The gun clears leakers at point-blank range.
"""
import math

NAME = "loiter_then_collapse"
ROLE = "defender"

COMMIT_W = 47.0

_S = {}


def reset(seed=None):
    global _S
    _S = {
        "released": False,
        "committed": False,
        "assign": {},
    }


reset()


def _tr(t, ax, ay):
    p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    x, y = float(p[0]), float(p[1])
    r = t.get("range")
    if r is None:
        r = math.hypot(x - ax, y - ay)
    return x, y, float(r), math.atan2(y - ay, x - ax)


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    tick = int(obs.get("tick", 0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))

    intercept = []
    retarget = {}
    gun = None

    cands = []
    for t in tracks:
        if t.get("cls") == "decoy":
            continue
        x, y, r, a = _tr(t, ax, ay)
        cands.append((t.get("id"), x, y, r, a))
    live = set(c[0] for c in cands)

    # Gun: nearest non-decoy in range
    if ammo > 0:
        best = None
        for c in cands:
            if c[3] <= gun_range and (best is None or c[3] < best[3]):
                best = c
        if best is not None:
            gun = best[0]

    if not cands:
        return {"intercept": [], "retarget": {}, "gun": gun}

    # Release detection
    if not S["released"]:
        inner = [c for c in cands if c[3] < 260.0]
        n_in = sum(1 for c in inner if c[3] < 175.0)
        if (len(inner) >= 3 and n_in * 2 >= len(inner)) or \
                any(c[3] < 120.0 for c in cands):
            S["released"] = True

    if not S["released"]:
        return {"intercept": [], "retarget": {}, "gun": gun}

    wave = [c for c in cands if c[3] < 200.0] or cands
    rs = sorted(c[3] for c in wave)
    W = rs[len(rs) // 2]
    rmin = rs[0]

    if not S["committed"]:
        trigger = W <= COMMIT_W or rmin <= 38.0
        for it in ints:
            if int(it.get("age", 0) or 0) >= life - 6:
                trigger = True
        if trigger:
            S["committed"] = True
            srt = sorted(wave, key=lambda c: c[4])
            N = len(srt)
            ilist = list(ints)
            k = len(ilist)
            targets = []
            if k > 0:
                if k >= N:
                    targets = [srt[j % N] for j in range(k)]
                else:
                    seen = set()
                    for j in range(k):
                        idx = int(math.floor(j * N / float(k) + 0.5)) % N
                        while idx in seen and len(seen) < N:
                            idx = (idx + 1) % N
                        seen.add(idx)
                        targets.append(srt[idx])
            free = list(range(k))
            for tg in targets:
                bi, bd = None, 1e18
                for i in free:
                    p = ilist[i].get("pos", [0.0, 0.0]) or [0.0, 0.0]
                    d = math.hypot(float(p[0]) - tg[1], float(p[1]) - tg[2])
                    if d < bd:
                        bd, bi = d, i
                if bi is None:
                    break
                free.remove(bi)
                iid = ilist[bi].get("id")
                S["assign"][iid] = tg[0]
                retarget[iid] = tg[0]
        else:
            # Loiter: bounce all interceptors between two opposite tracks
            A = max(cands, key=lambda c: math.cos(c[4]))
            B = min(cands, key=lambda c: math.cos(c[4]))
            lt = A[0] if tick % 2 == 0 else B[0]
            for it in ints:
                retarget[it.get("id")] = lt
            n = min(cap, stock)
            intercept = [lt] * n
            return {"intercept": intercept, "retarget": retarget, "gun": gun}

    # Committed phase: keep interceptors on live targets, spend leftover stock
    assigned = set()
    for it in ints:
        iid = it.get("id")
        tg = S["assign"].get(iid, it.get("target"))
        if tg in live:
            assigned.add(tg)
            if iid not in S["assign"]:
                S["assign"][iid] = tg
                retarget[iid] = tg
            continue
        p = it.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        px, py = float(p[0]), float(p[1])
        best, bd = None, 1e18
        for c in cands:
            d = math.hypot(c[1] - px, c[2] - py) + (30.0 if c[0] in assigned else 0.0)
            if d < bd:
                bd, best = d, c
        if best is not None:
            S["assign"][iid] = best[0]
            retarget[iid] = best[0]
            assigned.add(best[0])

    n = min(cap, stock)
    if n > 0:
        order = sorted(cands, key=lambda c: (c[0] in assigned, c[3]))
        for c in order[:n]:
            intercept.append(c[0])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
