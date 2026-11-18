"""Idea: Use the radar arrival cohort to label the bait screen, then fire the whole magazine only at the later cohort, one interceptor per striker, retarget, and finish with a nearest-first gun.

What I attack in hidden_orbit_screen_then_interleaved_drop:
- Its release schedule is fixed. All 16 decoys are released at tick 14. The strikers
  are released at ticks 27 and 31. Everything stages at r~482, so the radar sees nothing
  until the decoys cross r=450 together, all within a tick or two. Then nothing new
  appears for about 13 ticks until the 26 strikers arrive. The orbit that hides its
  build-up also announces which group is bait: the first cohort is the decoys.
- Its 26-striker count only exceeds the magazine plus gun if some interceptors go to
  the screen or are wasted. In its closest calls against hover_bank_double_lattice
  (score 0.76), the defender launched 19 interceptors for 17 striker kills, and the gun
  took 7 to 9 more. Every one of the 16 impacts was a decoy, so no striker leaked.
  Its easiest wins are against defenders that engage unknowns early: nearest_first
  scores 0.08, layered 0.10 and annealed_eager 0.09, because they spend rounds on the
  screen. This bot never spends a round on the first cohort unless that track is
  later identified as a striker.
- Interleaved shells defeat blast packing, so this bot does not try to pack. It puts one
  interceptor on each distinct striker as soon as the striker is seen. The early
  shell gets interceptors first, which staggers the survivors the gun has to handle. In-flight
  interceptors are retargeted if their track dies or is identified as a decoy. The gun
  always fires at the closest uncovered threat.
"""
import math

NAME = "cohort_screen_blind_one_per_striker"
ROLE = "defender"

COHORT_WIN = 6

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}
    _s["t0"] = None
    _s["pending"] = {}


def _rule(obs, k, d):
    try:
        return (obs.get("rules") or {}).get(k, d)
    except Exception:
        return d


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    tick = obs.get("tick", 0)
    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(_rule(obs, "interceptor_launches_per_tick", 2))
    gun_range = float(_rule(obs, "gun_range", 100.0))
    id_range = float(_rule(obs, "id_range", 150.0))
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])

    fs = _s["first_seen"]
    tmap = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        tmap[tid] = t
        if tid not in fs:
            fs[tid] = tick
            if _s["t0"] is None:
                _s["t0"] = tick

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t.get("pos", [0, 0])
            r = math.hypot(p[0] - ax, p[1] - ay)
        return float(r)

    def hostile(t):
        cls = t.get("cls", "unknown")
        if cls == "striker":
            return True
        if cls == "decoy":
            return False
        t0 = _s["t0"]
        suspect = t0 is not None and fs.get(t["id"], tick) <= t0 + COHORT_WIN
        if not suspect:
            return True
        # fallback: an unidentified suspect deep inside the ID ring is a threat
        return rng(t) < id_range * 0.9

    hostiles = {tid: t for tid, t in tmap.items() if hostile(t)}

    # covered targets
    covered = {}
    live_targets = set()
    for it in inters:
        tg = it.get("target")
        if tg is not None:
            live_targets.add(tg)
    pend = _s["pending"]
    for tg in list(pend.keys()):
        if tg in live_targets or tick - pend[tg] > 2:
            del pend[tg]
    for it in inters:
        tg = it.get("target")
        if tg is not None and tg in hostiles:
            covered[tg] = covered.get(tg, 0) + 1
    for tg in pend:
        if tg in hostiles:
            covered[tg] = covered.get(tg, 0) + 1

    # retarget interceptors whose target is gone or not hostile
    retarget = {}
    for it in inters:
        tg = it.get("target")
        if tg is not None and tg in hostiles:
            continue
        free = [h for h in hostiles.values() if h["id"] not in covered]
        if not free:
            continue
        ip = it.get("pos", [ax, ay])
        if isinstance(ip, dict):
            ip = ip.get("pos", [ax, ay])
        best = min(free, key=lambda h: math.hypot(h["pos"][0] - ip[0],
                                                  h["pos"][1] - ip[1]))
        retarget[it.get("id")] = best["id"]
        covered[best["id"]] = 1

    # launches: one per uncovered hostile, earliest-seen / closest first
    intercept = []
    if stock > 0:
        free = [h for h in hostiles.values() if h["id"] not in covered]
        free.sort(key=lambda h: (rng(h), fs.get(h["id"], tick)))
        for h in free:
            if len(intercept) >= min(cap, stock):
                break
            intercept.append(h["id"])
            covered[h["id"]] = 1
            pend[h["id"]] = tick

    # gun: closest hostile in range, prefer uncovered
    gun = None
    if ammo > 0:
        inr = [h for h in hostiles.values() if rng(h) <= gun_range]
        if inr:
            inr.sort(key=lambda h: (h["id"] in covered and h["id"] not in intercept, rng(h)))
            unc = [h for h in inr if h["id"] not in covered]
            pick = min(unc, key=rng) if unc else min(inr, key=rng)
            gun = pick["id"]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
