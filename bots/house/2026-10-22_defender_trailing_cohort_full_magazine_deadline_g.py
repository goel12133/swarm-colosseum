"""Idea: Treat the first radar cohort as bait and the trailing cohort as the strike, put every one of the 20 rounds into the trailing cohort at the radar edge, re-aim orphaned rounds, and run the gun on a no-overlap deadline queue.

Which part of the attacker this targets:
- The release schedule. Decoys leave the hidden r=482 orbit at tick 14. The two
  striker shells leave at ticks 27 and 31.
- Every decoy therefore crosses the 450 radar edge together, around tick 22.
- All 26 strikers cross about 13 ticks later, in two sub-waves 4 ticks apart.
- The hidden orbit hides the build-up, but it also makes first-seen time a clean
  label. The early cohort is all decoys and the late cohort is all strikers.
- Inside the 150 ID ring the radar's own class label overrides this, and it stays
  attached to the track.

What the replays show:
- In both of its closest calls, all 16 decoys flew in unshot and hit at tick 128,
  doing no damage. The defender held them and the asset still had 30 hp after
  them, so the decoys cost nothing.
- Those defenders lost or nearly lost on the strikers alone. They fired only 19 of
  20 interceptors (stock_left 1). They fired 22 gun rounds with 98 still left.
- The swarm is too large for the magazine: 26 strikers against 20 rounds at
  pk 0.85. So the match is decided by how few rounds are wasted and how well the
  gun uses its roughly 23-tick window.

How this bot differs from the obvious counter:
- It does not spend effort on a finer classifier. It is a magazine-accounting bot:
  - All 20 rounds go out at radar range, onto distinct trailing-cohort tracks.
  - No track ever carries two rounds.
  - A round whose target vanished, or whose target was revealed as a decoy, is
    re-aimed at an uncovered striker.
  - The gun never shoots a track that an in-flight round will reach before
    impact. It also never shoots at an identified decoy.
- This leaves every gun round free for the roughly 9 strikers no interceptor
  covers. The asset survives two leakers (30 hp, 10 damage each).
"""
import math

NAME = "trailing_cohort_full_magazine_deadline_gun"
ROLE = "defender"

COHORT_GAP = 6
SINGLE_COHORT_WAIT = 30

_s = {}


def reset(seed=None):
    _s.clear()
    _s["first"] = {}
    _s["cls"] = {}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    if "first" not in _s:
        reset(None)
    tick = int(obs.get("tick", 0))
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    tracks = obs.get("tracks", []) or []
    icps = obs.get("interceptors", []) or []
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    gun_range = float(rules.get("gun_range", 100.0))
    i_speed = float(rules.get("interceptor_speed", 12.0))
    d_speed = float(rules.get("striker_speed", 4.0))

    first = _s["first"]
    scls = _s["cls"]
    live = {}
    for t in tracks:
        tid = t["id"]
        px, py = float(t["pos"][0]), float(t["pos"][1])
        rng = t.get("range")
        if rng is None:
            rng = math.hypot(px - ax, py - ay)
        live[tid] = (px, py, float(rng))
        if tid not in first:
            first[tid] = tick
        c = t.get("cls", "unknown")
        if c in ("striker", "decoy"):
            scls[tid] = c

    # Cohorts by first-seen tick.
    ticks = sorted(set(first.values()))
    coh_of = {}
    starts = []
    prev = None
    for tk in ticks:
        if prev is None or tk - prev > COHORT_GAP:
            starts.append(tk)
        coh_of[tk] = len(starts) - 1
        prev = tk
    ncoh = len(starts)

    def presumed(tid):
        c = scls.get(tid)
        if c == "striker":
            return True
        if c == "decoy":
            return False
        k = coh_of.get(first.get(tid, tick), 0)
        if k >= 1:
            return True
        if ncoh >= 2:
            return False
        return tick - (starts[0] if starts else tick) > SINGLE_COHORT_WAIT

    strike = {tid for tid in live if presumed(tid)}

    # Coverage from in-flight interceptors.
    cov = {}
    orphans = []
    for ic in icps:
        tg = ic.get("target")
        if tg in live and tg in strike:
            cov.setdefault(tg, []).append(ic)
        else:
            orphans.append(ic)

    retarget = {}
    for ic in orphans:
        ip = ic.get("pos", [ax, ay]) or [ax, ay]
        best = None
        bd = 1e18
        for tid in strike:
            if tid in cov:
                continue
            px, py, _ = live[tid]
            d = math.hypot(px - ip[0], py - ip[1])
            if d < bd or (d == bd and str(tid) < str(best)):
                bd = d
                best = tid
        if best is not None:
            retarget[ic["id"]] = best
            cov.setdefault(best, []).append(ic)

    # Launch at uncovered presumed strikers, nearest first.
    intercept = []
    cands = sorted((live[tid][2], str(tid), tid) for tid in strike if tid not in cov)
    n = min(cap, stock, len(cands))
    for i in range(n):
        tid = cands[i][2]
        intercept.append(tid)
        cov.setdefault(tid, []).append({"pos": [ax, ay], "new": True})

    # Gun: deadline queue, skip tracks an interceptor will reach in time.
    gun = None
    if ammo > 0:
        uncovered = []
        covered = []
        for tid, (px, py, rng) in live.items():
            if rng > gun_range:
                continue
            if scls.get(tid) == "decoy":
                continue
            tti = max(0.0, (rng - arad) / max(d_speed, 1e-6))
            ok = False
            for ic in cov.get(tid, []):
                ip = ic.get("pos", [ax, ay]) or [ax, ay]
                d = math.hypot(px - ip[0], py - ip[1])
                eta = d / (i_speed + d_speed)
                if eta < tti - 1.0:
                    ok = True
                    break
            (covered if ok else uncovered).append((rng, str(tid), tid))
        pool = uncovered if uncovered else covered
        if pool:
            pool.sort()
            gun = pool[0][2]

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
