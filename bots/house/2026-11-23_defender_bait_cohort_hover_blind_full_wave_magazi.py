"""Idea: Treat the first radar cohort and any track that hovers at a fixed range as unpaid bait, so the whole 20-round magazine and the gun are kept for the striker wave that only shows up after the decoy ring has been shown.

Target: 2026-11-15_attacker_attacker_radar_shadow_orbit_decoy_drain.

What it relies on
-----------------
The bot assumes the defender will spend interceptors on the decoy ring. It
launches its 16 decoys on ticks 0-3. They enter radar together as one cohort,
then hold a rotating ring at radius 190, outside id range (150). Its 26 strikers
orbit at radius 485, outside radar (450). They are released only when
obs.interceptors shows the magazine has been used and the sky is empty, or when
a timer runs out.

Where it breaks
---------------
Neither branch of the release logic does any damage if the magazine is never
spent on the ring. The "drained" check and the "idle" timer both send the same
26 strikers into a full stock of 20.

The replays show that decoys do no damage. In both closest calls
(doublecover, seeds 1 and 3), 7-8 decoy impacts at tick 174 left asset_hp at
30. The same doublecover still wasted 9 and 7 gun kills on decoys. In seed 3 it
also wasted 1 interceptor on a decoy. Every defender that scores near zero
against this bot spent its magazine on the ring and had none left for the
strikers.

What this bot does
------------------
* Never fires an interceptor or the gun at a track revealed as a decoy.
* Never fires at an unknown track from the first-seen cohort. Never fires at an
  unknown track whose range has stayed flat for 10 ticks (a hover ring). These
  tracks are re-checked when they enter id range. A revealed striker is engaged
  at once.
* Fires one interceptor per new committed track as soon as the striker wave
  crosses into radar. This uses the full 2-per-tick launch rate, so intercepts
  happen near range 330 with time to spare. Lost interceptors are retargeted to
  uncovered threats.
* The gun fires only at strikers. It picks uncovered strikers first, then the
  nearest one.
"""

import math

NAME = "bait_cohort_hover_blind_full_wave_magazine"
ROLE = "defender"

_S = {}


def reset(seed=0):
    _S.clear()
    _S.update({
        "t0": None,
        "first_seen": {},
        "bait": set(),
        "hover": set(),
        "hist": {},
    })


reset(0)

COHORT_WINDOW = 12
HOVER_TICKS = 10
HOVER_SPAN = 12.0


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    a_rad = float(rules.get("asset_radius", 25.0))
    tracks = obs.get("tracks", []) or []
    ics = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0) or 0)
    ammo = int(obs.get("ammo", 0) or 0)
    per_tick = int(rules.get("interceptor_launches_per_tick", 2))
    id_range = float(rules.get("id_range", 150.0))
    gun_range = float(rules.get("gun_range", 100.0))
    ic_speed = float(rules.get("interceptor_speed", 12.0))
    life = float(rules.get("interceptor_lifetime", 90))

    tr = {}
    rng = {}
    cls = {}
    for t in tracks:
        tid = t.get("id")
        if tid is None:
            continue
        px, py = (t.get("pos") or [0.0, 0.0])[:2]
        r = t.get("range")
        if r is None:
            r = math.hypot(px - ax, py - ay)
        r = float(r)
        tr[tid] = (px, py)
        rng[tid] = r
        cls[tid] = t.get("cls", "unknown") or "unknown"

        if _S["t0"] is None:
            _S["t0"] = tick
        if tid not in _S["first_seen"]:
            _S["first_seen"][tid] = tick
            if tick <= _S["t0"] + COHORT_WINDOW:
                _S["bait"].add(tid)
        h = _S["hist"].setdefault(tid, [])
        h.append(r)
        if len(h) > HOVER_TICKS + 2:
            del h[0]
        if len(h) >= HOVER_TICKS and r > id_range:
            w = h[-HOVER_TICKS:]
            if max(w) - min(w) < HOVER_SPAN:
                _S["hover"].add(tid)

    def is_threat(tid):
        c = cls.get(tid, "unknown")
        if c == "striker":
            return True
        if c == "decoy":
            return False
        if tid in _S["bait"] or tid in _S["hover"]:
            return False
        return True

    threats = [tid for tid in tr if is_threat(tid) and rng[tid] > a_rad * 0.5]

    # Existing interceptor coverage.
    covered = {}
    lost = []
    for ic in ics:
        iid = ic.get("id")
        tgt = ic.get("target")
        if tgt in tr and is_threat(tgt):
            covered[tgt] = covered.get(tgt, 0) + 1
        else:
            lost.append(ic)

    retarget = {}
    for ic in lost:
        iid = ic.get("id")
        ipos = (ic.get("pos") or [ax, ay])[:2]
        age = float(ic.get("age", 0) or 0)
        reach = max(0.0, (life - age)) * ic_speed
        best, bd = None, None
        for tid in threats:
            if covered.get(tid, 0) > 0:
                continue
            px, py = tr[tid]
            d = math.hypot(px - ipos[0], py - ipos[1])
            if d > reach * 0.9:
                continue
            if bd is None or d < bd:
                best, bd = tid, d
        if best is not None and iid is not None:
            retarget[iid] = best
            covered[best] = covered.get(best, 0) + 1

    # New launches: one per uncovered threat, most urgent first.
    intercept = []
    avail = min(per_tick, stock)
    if avail > 0:
        cand = [tid for tid in threats if covered.get(tid, 0) == 0]
        cand.sort(key=lambda t: rng[t])
        for tid in cand:
            if len(intercept) >= avail:
                break
            intercept.append(tid)
            covered[tid] = covered.get(tid, 0) + 1

    # Gun: strikers only, uncovered first, then nearest.
    gun = None
    if ammo > 0:
        best_key = None
        for tid in tr:
            if rng[tid] > gun_range:
                continue
            c = cls[tid]
            if c == "decoy":
                continue
            if c != "striker" and not is_threat(tid):
                continue
            key = (0 if covered.get(tid, 0) == 0 or tid in intercept else 1, rng[tid])
            if best_key is None or key < best_key:
                best_key, gun = key, tid

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
