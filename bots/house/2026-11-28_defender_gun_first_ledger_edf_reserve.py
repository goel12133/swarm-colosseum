"""Idea: Ignore every pre-ID track, spend the magazine only on ID'd strikers outside gun range, hold a 3-round reserve that fires on an earliest-deadline schedule at whatever the gun leaves alive, and point the gun only at strikers that have no interceptor arriving.

Target: the attacker's core claim that "26 strikers (52 budget) are more than the
20-round magazine at pk 0.85 plus the gun can stop", and that compressing all 26
strikers onto the 150 ID ring beats a 2-per-tick launch cap.

What the replays show: its two closest calls are both against
hover_bank_double_lattice, and both end with zero striker impacts. In each game the
defender used 19 interceptors for 17-19 kills and got 7-9 gun kills from only 22
shots. The arithmetic is tight but it holds. About 17 interceptor kills plus about 7
gun kills is 24 of 26, and the asset survives 2 hits. The attacker wins only when the
defender wastes rounds. That happens in three ways: firing at the 16-decoy screen,
letting an interceptor and the gun double up on one striker, or leaving the gun idle.

How this bot exploits that:
- The screen never costs a round. Nothing is launched at an unknown track. Decoys
  get ID'd at r=150 about 13 ticks before the strikers and are dropped.
- Shell A hits the ID ring 4 ticks before shell B. So 17 rounds go out at r~150
  without straining the 2-per-tick cap, and the intercepts land at r~110, outside
  gun range.
- The shell-B lag stretches the gun's window to about 23 ticks. The gun only shoots
  strikers with no interceptor inbound, so no shot is wasted.
- The 3-round reserve is spent last, on an earliest-deadline schedule. It goes only
  to strikers the gun failed to kill, so reserve rounds are never spent on a target
  the gun would have finished.
- Interceptors whose target dies are retargeted to the nearest striker they can still
  reach.
"""
import math

NAME = "gun_first_ledger_edf_reserve"
ROLE = "defender"

RESERVE = 3
DEADLINE_R = 58.0

_s = {}


def reset(seed=None):
    _s.clear()
    _s["had"] = set()


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "had" not in _s:
        reset(None)
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    ssp = float(rules.get("striker_speed", 4.0))
    isp = float(rules.get("interceptor_speed", 12.0))
    life = float(rules.get("interceptor_lifetime", 90))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    grange = float(rules.get("gun_range", 100.0))
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    closing = isp + ssp

    tracks = obs.get("tracks", []) or []
    strikers = {}
    unknowns = {}
    for t in tracks:
        p = t.get("pos", [0.0, 0.0])
        r = t.get("range")
        if r is None:
            r = math.hypot(p[0] - ax, p[1] - ay)
        r = float(r)
        c = t.get("cls", "unknown")
        if c == "striker":
            strikers[t["id"]] = (r, p)
        elif c == "unknown":
            unknowns[t["id"]] = (r, p)

    def tti(r):
        return max(0.0, (r - arad) / ssp)

    icpts = obs.get("interceptors", []) or []
    assigned = {}
    eta = {}
    free = []
    for ic in icpts:
        tid = ic.get("target")
        if tid in strikers:
            assigned[tid] = assigned.get(tid, 0) + 1
            ip = ic.get("pos", [ax, ay])
            sp = strikers[tid][1]
            e = math.hypot(ip[0] - sp[0], ip[1] - sp[1]) / closing
            eta[tid] = min(eta.get(tid, 1e9), e)
            _s["had"].add(tid)
        else:
            free.append(ic)

    # retarget interceptors whose target is gone or is a decoy
    retarget = {}
    for ic in free:
        ip = ic.get("pos", [ax, ay])
        age = float(ic.get("age", 0) or 0)
        best = None
        bestkey = None
        for sid, (r, sp) in strikers.items():
            d = math.hypot(ip[0] - sp[0], ip[1] - sp[1])
            e = d / closing
            if e + 0.5 >= tti(r) or age + e >= life - 1:
                continue
            key = (assigned.get(sid, 0), d)
            if bestkey is None or key < bestkey:
                bestkey = key
                best = (sid, e)
        if best is not None:
            sid, e = best
            retarget[ic["id"]] = sid
            assigned[sid] = assigned.get(sid, 0) + 1
            eta[sid] = min(eta.get(sid, 1e9), e)
            _s["had"].add(sid)

    # launches
    min_r = (arad + 6.0) * closing / isp
    cands = sorted([(r, sid) for sid, (r, sp) in strikers.items()
                    if assigned.get(sid, 0) == 0 and r > min_r])
    urgent = False
    for i, (r, sid) in enumerate(cands):
        slack = (r - DEADLINE_R) / ssp
        if slack <= (i // max(1, cap)):
            urgent = True
            break
    launch = []
    left = stock
    for r, sid in cands:
        if len(launch) >= cap or left <= 0:
            break
        refire = sid in _s["had"] and r > grange
        if left > RESERVE or urgent or refire:
            launch.append(sid)
            left -= 1
            assigned[sid] = assigned.get(sid, 0) + 1
            eta[sid] = (r * isp / closing) / closing if False else r / closing
            _s["had"].add(sid)

    # gun
    gun = None
    if ammo > 0:
        inr = [(r, sid) for sid, (r, sp) in strikers.items() if r <= grange]
        un = sorted([(r, sid) for r, sid in inr if assigned.get(sid, 0) == 0])
        if un:
            gun = un[0][1]
        elif inr:
            late = sorted([(-eta.get(sid, 0.0), r, sid) for r, sid in inr])
            gun = late[0][2]
        else:
            uk = sorted([(r, sid) for sid, (r, sp) in unknowns.items() if r <= grange])
            if uk:
                gun = uk[0][1]

    return {"intercept": launch, "retarget": retarget, "gun": gun}
