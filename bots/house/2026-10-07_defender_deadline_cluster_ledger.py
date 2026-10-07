"""Idea: Earliest-deadline backscheduling on a worst-case "rush now" clock, filling each forced launch with the confirmed striker whose predicted blast point catches the most other uncovered strikers, and ignoring every unidentified track outside id range.

Name: deadline_cluster_ledger (defender)

How it works
------------
1. Track filter. Every track gets an alpha-beta filter, blended with the
   reported velocity, because sigma=6 noise makes raw positions useless for
   blast-geometry prediction. A classification, once seen, is remembered.
2. Threat set. Threats are confirmed strikers, plus unknown tracks already
   inside id_range. Decoys are never engaged. Unknowns parked outside 150 are
   never engaged either. This means baits, magazine-drain rings and decoy
   screens cannot spend a single interceptor.
3. Coverage ledger. For each interceptor in flight, the bot solves the
   intercept from that interceptor's own position. Its target, and every
   threat predicted to be inside about 0.8 blast radii of the detonation
   point, gets a survival factor of 0.15. Covered tracks drop out of the
   queue.
4. Worst-case deadline. Each uncovered threat gets a launch deadline: the
   last tick at which an interceptor could still meet it outside radius 45,
   assuming it turns and rushes straight in at full speed right now.
   Loitering therefore never hides a threat's real deadline.
5. Earliest-deadline-first capacity test. Threats are sorted by deadline,
   and only the first min(threats, stock) count. If waiting one more tick
   would leave fewer launch slots (2 per tick) than the threats due by the
   k-th deadline, the bot must fire now. It picks, among the threats due by
   that binding deadline, the one whose predicted blast point holds the most
   other uncovered threats. Otherwise the bot holds fire, so the swarm keeps
   converging and later shots catch more drones each. Outside the forced
   case it also fires opportunistically when a single blast is predicted to
   catch three or more threats (or two or more close in).
6. Retargeting. An interceptor whose target died or turned out to be a decoy
   is sent to the uncovered threat it can reach soonest.
7. Gun. Every tick the gun fires at the nearest uncovered threat in range.
   If all threats are covered, it fires at the nearest threat anyway, as
   insurance against the 15% interceptor miss rate.

Why it holds up against the whole field
---------------------------------------
- synchronized_ring and phase_locked_ring. Both park strikers just outside
  the id gate, then cross it together. The worst-case deadline already
  accounts for loiterers, and the capacity test counts all of them at once.
  Launches therefore start exactly when 2 per tick is barely enough. They
  are never late, which is what killed the ledger-style bots. And because
  waiting is legal until that moment, the late shots land where the ring
  has contracted, so many blasts take two drones.
- interleaved_shell_ring. Its spacing defeats blast pairing far out. But the
  queue is ordered by deadline, so the inner shell is served first, the next
  shell second, and so on, at the full launch rate. Bots that hold for
  clusters that never form get flooded; this one does not. Pairing kicks in
  automatically once the convergence geometry brings drones within a blast
  radius near the asset, and the gun handles leakers.
- depth_shell_saturation and trickle. Staggered depths simply become
  staggered deadlines. Each threat is engaged on time and individually, and
  there is no premature magazine dump on far shells.
- parked_ring_magazine_drain, decoy_screen, staggered_screen_trickle,
  flanker, multi_axis. Nothing is fired outside id range or at decoys, so
  draining fails. Flanks and multiple axes are bearing-agnostic to a
  deadline queue.
- rush. Many threats with short deadlines immediately trigger the capacity
  rule at the maximum rate, and blast packing helps on the dense front.
"""

import math

NAME = "deadline_cluster_ledger"
ROLE = "defender"

_state = {}


def reset(seed=None):
    global _state
    _state = {"filt": {}, "cls": {}, "last_tick": -1}


reset()


def _get(rules, k, d):
    try:
        v = rules.get(k, d)
        return d if v is None else v
    except Exception:
        return d


def _solve_intercept(px, py, vx, vy, ox, oy, s):
    rx, ry = px - ox, py - oy
    a = vx * vx + vy * vy - s * s
    b = 2.0 * (rx * vx + ry * vy)
    c = rx * rx + ry * ry
    if abs(a) < 1e-9:
        if abs(b) < 1e-9:
            return None
        t = -c / b
        return t if t > 0 else None
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    cands = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
    cands = [t for t in cands if t > 0]
    return min(cands) if cands else None


def _update_filter(tracks, tick, dspeed):
    filt = _state["filt"]
    last = _state["last_tick"]
    dt = tick - last if last >= 0 else 1
    if dt <= 0:
        dt = 1
    seen = set()
    for tr in tracks:
        tid = tr.get("id")
        pos = tr.get("pos") or [0.0, 0.0]
        vel = tr.get("vel") or [0.0, 0.0]
        zx, zy = float(pos[0]), float(pos[1])
        ovx, ovy = float(vel[0]), float(vel[1])
        seen.add(tid)
        f = filt.get(tid)
        if f is None:
            filt[tid] = [zx, zy, ovx, ovy]
            continue
        x, y, vx, vy = f
        px, py = x + vx * dt, y + vy * dt
        rx, ry = zx - px, zy - py
        a, b = 0.5, 0.25 / dt
        x, y = px + a * rx, py + a * ry
        vx, vy = vx + b * rx, vy + b * ry
        vx = 0.5 * vx + 0.5 * ovx
        vy = 0.5 * vy + 0.5 * ovy
        sp = math.hypot(vx, vy)
        cap = dspeed * 1.1
        if sp > cap and sp > 0:
            vx, vy = vx * cap / sp, vy * cap / sp
        filt[tid] = [x, y, vx, vy]
    for tid in list(filt.keys()):
        if tid not in seen:
            del filt[tid]
    _state["last_tick"] = tick


def _act(obs):
    rules = obs.get("rules") or {}
    tick = int(obs.get("tick", 0))
    asset = obs.get("asset") or {}
    apos = asset.get("pos") or [0.0, 0.0]
    ax, ay = float(apos[0]), float(apos[1])
    arad = float(asset.get("radius", _get(rules, "asset_radius", 25.0)))
    tracks = obs.get("tracks") or []
    inters = obs.get("interceptors") or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))

    dspeed = float(_get(rules, "striker_speed", 4.0))
    ispeed = float(_get(rules, "interceptor_speed", 12.0))
    ilife = float(_get(rules, "interceptor_lifetime", 90))
    rate = int(_get(rules, "interceptor_launches_per_tick", 2))
    blast = float(_get(rules, "blast_radius", 10.0))
    idr = float(_get(rules, "id_range", 150.0))
    grange = float(_get(rules, "gun_range", 100.0))

    _update_filter(tracks, tick, dspeed)
    filt = _state["filt"]
    clsmem = _state["cls"]

    threats = {}
    for tr in tracks:
        tid = tr.get("id")
        c = tr.get("cls", "unknown")
        if c in ("striker", "decoy"):
            clsmem[tid] = c
        c = clsmem.get(tid, c)
        f = filt.get(tid)
        if f is None:
            continue
        rng = math.hypot(f[0] - ax, f[1] - ay)
        if c == "decoy":
            continue
        if c == "striker" or rng < idr:
            threats[tid] = (f[0], f[1], f[2], f[3], rng)

    nb = blast * 0.8
    r_min = arad + 20.0
    ratio = ispeed / (ispeed + dspeed)
    r_launch = r_min / ratio

    def pred(tid, t):
        x, y, vx, vy, _ = threats[tid]
        return x + vx * t, y + vy * t

    def neighbors(tid, t, pool):
        px, py = pred(tid, t)
        out = []
        for w in pool:
            if w == tid:
                continue
            qx, qy = pred(w, t)
            if (qx - px) ** 2 + (qy - py) ** 2 <= nb * nb:
                out.append(w)
        return out

    surv = {tid: 1.0 for tid in threats}
    retarget = {}
    orphans = []
    for it in inters:
        iid = it.get("id")
        tgt = it.get("target")
        ipos = it.get("pos") or [ax, ay]
        age = float(it.get("age", 0))
        if tgt in threats:
            x, y, vx, vy, _ = threats[tgt]
            t = _solve_intercept(x, y, vx, vy, float(ipos[0]), float(ipos[1]), ispeed)
            if t is None or t > ilife - age:
                t = None
            if t is not None:
                surv[tgt] *= 0.15
                for w in neighbors(tgt, t, list(threats.keys())):
                    surv[w] *= 0.3
            else:
                orphans.append((iid, ipos, age))
        else:
            orphans.append((iid, ipos, age))

    def uncovered():
        return [t for t in threats if surv.get(t, 1.0) > 0.3]

    for iid, ipos, age in orphans:
        U = uncovered()
        if not U:
            break
        best, bt = None, None
        for u in U:
            x, y, vx, vy, _ = threats[u]
            t = _solve_intercept(x, y, vx, vy, float(ipos[0]), float(ipos[1]), ispeed)
            if t is None or t > ilife - age:
                continue
            if bt is None or t < bt:
                best, bt = u, t
        if best is not None:
            retarget[iid] = best
            surv[best] *= 0.15

    launches = []
    slots = min(rate, stock)
    margin = 1
    while len(launches) < slots:
        U = uncovered()
        if not U:
            break
        info = {}
        for u in U:
            x, y, vx, vy, r = threats[u]
            d = (r - r_launch) / dspeed - 1.0
            t = _solve_intercept(x + vx, y + vy, vx, vy, ax, ay, ispeed)
            if t is None:
                t = r / (ispeed + dspeed)
            t += 1.0
            info[u] = (d, t)
        U.sort(key=lambda u: info[u][0])
        left = stock - len(launches)
        n = min(len(U), left)
        bind = None
        for k in range(n):
            d = info[U[k]][0]
            avail = rate * max(0, int(math.floor(d)) - margin)
            if k + 1 > avail:
                bind = k
                break
        choice = None
        if bind is not None:
            best_v, best_d = -1, None
            for u in U[:bind + 1]:
                v = 1 + len(neighbors(u, info[u][1], U))
                if v > best_v or (v == best_v and info[u][0] < best_d):
                    best_v, best_d, choice = v, info[u][0], u
        else:
            best_v = 0
            for u in U:
                t = info[u][1]
                px, py = pred(u, t)
                rr = math.hypot(px - ax, py - ay)
                if rr > idr or rr < arad + 5:
                    continue
                v = 1 + len(neighbors(u, t, U))
                if v >= 3 or (v >= 2 and rr <= 80):
                    if v > best_v:
                        best_v, choice = v, u
        if choice is None:
            break
        launches.append(choice)
        surv[choice] *= 0.15
        for w in neighbors(choice, info[choice][1], U):
            surv[w] *= 0.3

    gun = None
    if ammo > 0:
        inr = [(threats[t][4], t) for t in threats if threats[t][4] <= grange]
        if inr:
            unc = [p for p in inr if surv.get(p[1], 1.0) > 0.3 and p[1] not in launches]
            pool = unc if unc else inr
            pool.sort()
            gun = pool[0][1]

    return {"intercept": launches, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
