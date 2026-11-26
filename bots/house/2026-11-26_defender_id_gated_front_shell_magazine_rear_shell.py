"""Idea: Fire interceptors only at ID-confirmed strikers, nearest first, so the unengaged strikers all fall into the rear shell, and point the gun only at strikers that no interceptor is chasing.

Target: hidden_orbit_screen_then_interleaved_drop, and two of its timing claims.

1. The decoy screen is mistimed.
   - Decoys are released at tick 14 and strikers at ticks 27 and 31.
   - So the 16 decoys cross the 150 ID ring around tick 97. That is about 13 ticks
     before shell A crosses it (tick ~110) and 17 before shell B (tick ~114).
   - The decoys show up as "decoy" well before any striker is near. A defender that
     fires only on confirmed strikers gives them nothing.
   - Replay evidence: in its two closest calls, all 16 decoys hit the asset at tick 128
     for zero damage. The asset kept all 30 hp. 19 interceptors produced 17 striker
     kills, with no interceptor spent on a decoy.

2. "The ID-then-engage window is compressed against the 2-per-tick cap" is false.
   - Shell A is ID'd at tick ~110. At 2 launches per tick, all 20 rounds are out by
     tick ~119.
   - Each round meets its striker around r 100-112, well before impact at tick 141.
   - So the match comes down to 20 rounds at pk 0.85 plus about 22 gun shots against
     26 strikers.
   - Replay evidence: the closest calls were won only on gun kills (7 and 9 of 26).
     The gun is the swing factor.

How this bot uses that:
- Nearest-first interceptor launches cover shell A almost completely. The roughly 6
  unengaged strikers fall into shell B.
- Shell B trails shell A by 16 units, so it keeps flying for about 4 ticks (141-145)
  after shell A has hit or died. In those ticks the gun has no competing targets and
  shoots at its closest, best range.
- The gun ranks uncovered strikers ahead of ones with an interceptor inbound. It does
  not spend shots on targets already 85% dead.
- If an interceptor's target dies or is revealed as a decoy, the interceptor is
  retargeted to the nearest uncovered striker. If a round misses, its striker counts as
  uncovered again, and the gun and any spare stock pick it up.
"""
import math

NAME = "id_gated_front_shell_magazine_rear_shell_gun"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first_seen"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first_seen" not in _s:
        reset(None)
    rules = obs.get("rules", {}) or {}
    tick = obs.get("tick", 0)
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    a_rad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    tracks = obs.get("tracks", []) or []
    itcs = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    id_range = float(rules.get("id_range", 150.0))

    def rng(t):
        r = t.get("range")
        if r is None:
            p = t["pos"]
            r = math.hypot(p[0] - ax, p[1] - ay)
        return float(r)

    live = {}
    threats = {}
    for t in tracks:
        tid = t["id"]
        live[tid] = t
        if tid not in _s["first_seen"]:
            _s["first_seen"][tid] = tick
        cls = t.get("cls", "unknown")
        r = rng(t)
        if cls == "striker":
            threats[tid] = r
        elif cls == "unknown" and r <= id_range * 0.95:
            # should already be identified; treat as a threat to be safe
            threats[tid] = r

    # coverage by live interceptors
    cover = {tid: 0 for tid in threats}
    need = []
    for it in itcs:
        tgt = it.get("target")
        if tgt in threats:
            cover[tgt] += 1
        else:
            need.append(it)

    retarget = {}
    for it in need:
        ipos = it.get("pos", [ax, ay]) or [ax, ay]
        best = None
        bkey = None
        for tid, r in threats.items():
            if r < a_rad + 8.0:
                continue
            p = live[tid]["pos"]
            dist = math.hypot(p[0] - ipos[0], p[1] - ipos[1])
            key = (cover[tid], dist)
            if bkey is None or key < bkey:
                bkey = key
                best = tid
        if best is not None:
            retarget[it["id"]] = best
            cover[best] += 1

    # launches: uncovered confirmed strikers, nearest first
    intercept = []
    n = min(cap, stock)
    if n > 0:
        cands = [tid for tid, r in threats.items()
                 if cover[tid] == 0 and r > a_rad + 12.0]
        cands.sort(key=lambda tid: threats[tid])
        for tid in cands[:n]:
            intercept.append(tid)
            cover[tid] += 1

    # gun: uncovered first, then nearest
    gun = None
    if ammo > 0:
        best = None
        bkey = None
        for tid, r in threats.items():
            if r > gun_range:
                continue
            key = (1 if cover.get(tid, 0) > 0 else 0, r)
            if bkey is None or key < bkey:
                bkey = key
                best = tid
        gun = best

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
