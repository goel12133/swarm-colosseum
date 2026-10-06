"""
Idea: Park the whole magazine at the origin by dithering retargets, wait for the synchronized ring to contract, then fire every interceptor outward at once so each blast lands where neighbouring strikers are less than one blast radius apart.

Target: 2026-09-29_attacker_synchronized_ring.

Which part of its logic this attacks
------------------------------------
1. The release gate. The attacker holds all 30 strikers at radius 190 and
   releases them on the same tick, each flying straight at the asset. That
   turns the raid into one ring that shrinks at a known rate (4 per tick).
   Its arrival time and geometry are fully predictable from the moment the
   ring starts moving.
2. Its spacing assumption. The docstring plans for strikers "about 20+ units
   apart where the interceptors meet them" so that one blast kills one
   striker. That only holds far out. Spacing on the ring is r * 2*pi / 30, or
   about 0.21 * r. Inside r of about 95, two strikers fit inside one 10 unit
   blast. Inside r of about 48, three fit. The attacker never steers after
   release, so it cannot spread back out.

What the replays show
---------------------
* Its two closest calls were both full defences (asset hp 30). In both, 20
  interceptors produced more than 20 kills: 28 kills for loiter_then_collapse
  (seed 9) and 22 for convergence_blast_scheduler (seed 3). The gun added
  only 2 to 8. So the raid breaks exactly when blasts are multi-kills, which
  means engaging late, on the contracted ring.
* The defenders that engage early, one interceptor per striker
  (discriminating_ledger, layered, nearest_first and others), all score about
  0.14. Spending the magazine 1:1 out at 150 to 190 is what the attacker was
  built to punish.

Plan
----
* Do nothing while the ring is parked.
* When tracks start coming inward, launch the full magazine at 2 per tick.
  Hold the interceptors near the origin by retargeting each one every tick to
  the track that lies most nearly opposite its current offset.
* Once tracks come within about 60, commit interceptors. Their head-on meeting
  point (closure speed 16 against 4) is about 0.75 r, so near r 45. Pick blast
  centres greedily so each one covers the most uncovered neighbouring tracks,
  then add second coverage when spare interceptors remain.
* The gun shoots the closest uncovered track inside its range.
"""
import math

NAME = "contracting_ring_blaster"
ROLE = "defender"

COMMIT_R = 62.0
COVER_D = 12.5
EMERG_R = 42.0

_S = {}


def reset(seed=None):
    global _S
    _S = {"ema": {}, "committed": {}, "triggered": False,
          "emerg": set(), "launched": 0}


reset()


def _act(obs):
    S = _S
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    gun_range = float(rules.get("gun_range", 100.0))
    life = int(rules.get("interceptor_lifetime", 90))
    lcap = int(rules.get("interceptor_launches_per_tick", 2))

    tr = {}
    for t in obs.get("tracks", []) or []:
        tid = t.get("id")
        if tid is None or t.get("cls") == "decoy":
            continue
        p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(x, y)
        tr[tid] = (x, y, r)
        e = S["ema"].get(tid)
        if e is None:
            S["ema"][tid] = [r, 0.0]
        else:
            nr = 0.6 * e[0] + 0.4 * r
            e[1] = 0.6 * e[1] + 0.4 * (nr - e[0])
            e[0] = nr

    if not S["triggered"]:
        for tid, (x, y, r) in tr.items():
            e = S["ema"][tid]
            if (e[0] < 172.0 and e[1] < -1.5) or r < 130.0:
                S["triggered"] = True
                break

    ints = {}
    for it in obs.get("interceptors", []) or []:
        iid = it.get("id")
        if iid is None:
            continue
        p = it.get("pos", [0.0, 0.0]) or [0.0, 0.0]
        ints[iid] = (float(p[0]) - ax, float(p[1]) - ay,
                     int(it.get("age", 0) or 0), it.get("target"))

    com = S["committed"]
    for iid in list(com.keys()):
        if iid not in ints or com[iid] not in tr:
            del com[iid]
    # Interceptors launched as emergency shots count as committed.
    for iid, (x, y, age, tgt) in ints.items():
        if iid not in com and tgt in S["emerg"] and tgt in tr and age <= 2:
            com[iid] = tgt
    free = [i for i in ints if i not in com]

    def covered_count(tid):
        x, y, _ = tr[tid]
        c = 0
        for ct in com.values():
            cx, cy, _ = tr[ct]
            if math.hypot(cx - x, cy - y) <= COVER_D:
                c += 1
        return c

    retarget = {}

    # Commit interceptors to the contracting ring.
    if free and tr:
        cand = [t for t, v in tr.items() if v[2] <= COMMIT_R]
        while free and cand:
            unc = [t for t in tr if covered_count(t) == 0]
            best, bscore = None, None
            for c in cand:
                cx, cy, cr = tr[c]
                n = 0
                for u in unc:
                    ux, uy, _ = tr[u]
                    if math.hypot(ux - cx, uy - cy) <= COVER_D:
                        n += 1
                if n == 0:
                    continue
                sc = (n, -cr)
                if bscore is None or sc > bscore:
                    bscore, best = sc, c
            if best is None:
                break
            bx, by, _ = tr[best]
            fi = min(free, key=lambda i: math.hypot(ints[i][0] - bx,
                                                    ints[i][1] - by))
            com[fi] = best
            free.remove(fi)
        # Second coverage when there are spare interceptors.
        if free:
            future = sum(1 for t, v in tr.items()
                         if v[2] > COMMIT_R and covered_count(t) == 0)
            spare = len(free) + stock - int(math.ceil(future / 1.6))
            inner = sorted([t for t, v in tr.items() if v[2] <= COMMIT_R - 8],
                           key=lambda t: tr[t][2])
            for t in inner:
                if spare <= 0 or not free:
                    break
                if covered_count(t) < 2:
                    tx, ty, _ = tr[t]
                    fi = min(free, key=lambda i: math.hypot(ints[i][0] - tx,
                                                            ints[i][1] - ty))
                    com[fi] = t
                    free.remove(fi)
                    spare -= 1
        # Free interceptors near the end of their life go to the closest track.
        for fi in list(free):
            if ints[fi][2] >= life - 6:
                t = min(tr, key=lambda k: tr[k][2])
                com[fi] = t
                free.remove(fi)

    for iid, t in com.items():
        retarget[iid] = t

    # Dither the free interceptors near the origin.
    if tr:
        for fi in free:
            x, y, _, _ = ints[fi]
            d = math.hypot(x, y)
            best, bv = None, None
            for t, (tx, ty, r) in tr.items():
                if r < 1e-6:
                    continue
                if d < 1.0:
                    v = -r
                else:
                    v = (x * tx + y * ty) / (d * r)
                if bv is None or v < bv:
                    bv, best = v, t
            if best is not None:
                retarget[fi] = best

    # Launches.
    intercept = []
    if stock > 0 and tr:
        n = min(lcap, stock)
        urgent = sorted([t for t, v in tr.items()
                         if v[2] <= EMERG_R and covered_count(t) == 0],
                        key=lambda t: tr[t][2])
        for t in urgent:
            if len(intercept) >= n:
                break
            intercept.append(t)
            S["emerg"].add(t)
        if S["triggered"]:
            order = sorted(tr, key=lambda t: tr[t][2])
            while len(intercept) < n and order:
                intercept.append(order[0])
        S["launched"] += len(intercept)

    # Gun.
    gun = None
    if ammo > 0:
        inr = [t for t, v in tr.items() if v[2] <= gun_range]
        if inr:
            unc = [t for t in inr if covered_count(t) == 0]
            pool = unc if unc else inr
            gun = min(pool, key=lambda t: tr[t][2])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
