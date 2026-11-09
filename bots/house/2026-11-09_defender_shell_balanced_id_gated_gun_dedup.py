"""Idea: Spend the whole magazine only on ID-confirmed strikers, split it evenly between the two arrival shells by time-to-impact, and point the gun only at strikers that no inbound interceptor will reach in time.

Target: hidden_orbit_screen_then_interleaved_drop (attacker).

Which part of its logic this attacks:
- The decoy screen only works on defenders that fire at unknowns. The 16 decoys are
  released at tick 14. They reach the 150 ID ring near tick 97, which is about 13
  ticks before any striker does. So they are labelled "decoy" long before the
  defender has to commit anything. This bot never launches at, retargets onto, or
  shoots a track that is not a confirmed striker. The screen costs it nothing.
- The 26 strikers are packed into two synchronized shells. Shell A crosses r=150 near
  tick 110 and shell B near tick 114. Shell A impacts near tick 141 and shell B near
  tick 145. Its bet is that 20 rounds at pk 0.85 (about 17 kills) leave more survivors
  than the gun can clear. The gun window is roughly r=100 down to r=25, so about
  ticks 122-145.

What the replays show:
- Its two closest calls (vs hover_bank_double_lattice, seeds 3 and 5) were both
  defended. In both, all 16 impacts were decoys. 19 interceptors went only at
  strikers and made 17-19 kills. The gun then made the deciding 7-9 kills from 22
  shots. So the match is decided by coordinating interceptors and gun in the
  terminal window.
- A defender that empties its magazine into shell A first (earliest deadline) leaves
  most survivors in shell B. The gun then has only about 19 useful ticks.

What this bot does instead:
- Interceptors go to the least-covered time-to-impact band. That spreads them about
  10/10 across the shells, so the gun has a live target on every tick from about 122
  to 145 rather than about 19.
- The gun skips strikers that already have an interceptor due to arrive before impact,
  so no shot is spent twice on the same striker.
- Interceptors whose target dies (to the gun or to another blast) are retargeted at
  once onto the uncovered striker they can reach soonest.
"""
import math

NAME = "shell_balanced_id_gated_gun_dedup"
ROLE = "defender"

_s = {}


def reset(seed=None):
    _s.clear()


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    asset = obs.get("asset", {}) or {}
    ap = asset.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    ax, ay = float(ap[0]), float(ap[1])
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))
    s_speed = float(rules.get("striker_speed", 4.0))
    i_speed = float(rules.get("interceptor_speed", 12.0))
    i_life = float(rules.get("interceptor_lifetime", 90))
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))

    tracks = obs.get("tracks", []) or []
    inters = obs.get("interceptors", []) or []

    # Confirmed strikers only, with their time to impact.
    info = {}
    for t in tracks:
        if t.get("cls") != "striker":
            continue
        px, py = float(t["pos"][0]), float(t["pos"][1])
        r = math.hypot(px - ax, py - ay)
        v = t.get("vel") or [0.0, 0.0]
        sp = math.hypot(float(v[0]), float(v[1]))
        if sp < 0.5:
            sp = s_speed
        eta = max(0.0, r - arad) / sp
        info[t["id"]] = {"pos": (px, py), "r": r, "eta": eta, "sp": sp}

    # Count how many live interceptors are on each striker, and find orphans.
    engaged = {}
    cover_eta = {}
    orphans = []
    for it in inters:
        tid = it.get("target")
        ipos = it.get("pos") or [ax, ay]
        if tid in info:
            engaged[tid] = engaged.get(tid, 0) + 1
            d = math.hypot(ipos[0] - info[tid]["pos"][0], ipos[1] - info[tid]["pos"][1])
            arr = d / (i_speed + info[tid]["sp"])
            cover_eta[tid] = min(cover_eta.get(tid, 1e9), arr)
        else:
            orphans.append(it)

    retarget = {}
    # Retarget each orphan to the uncovered striker it can reach soonest.
    for it in orphans:
        ipos = it.get("pos") or [ax, ay]
        age = float(it.get("age", 0))
        best, bt = None, 1e9
        for tid, d in info.items():
            if engaged.get(tid, 0) > 0:
                continue
            dist = math.hypot(ipos[0] - d["pos"][0], ipos[1] - d["pos"][1])
            tt = dist / (i_speed + d["sp"])
            if age + tt > i_life - 1 or tt > d["eta"] + 0.5:
                continue
            if tt < bt:
                bt, best = tt, tid
        if best is not None:
            retarget[it["id"]] = best
            engaged[best] = engaged.get(best, 0) + 1
            cover_eta[best] = min(cover_eta.get(best, 1e9), bt)

    # Launches: give the next interceptor to the least-covered time-to-impact band.
    intercept = []
    n_launch = min(cap, stock)
    for _ in range(n_launch):
        cands = [tid for tid in info if engaged.get(tid, 0) == 0
                 and info[tid]["r"] / (i_speed + info[tid]["sp"]) < info[tid]["eta"] + 0.5]
        if not cands:
            break
        best, bkey = None, None
        for c in cands:
            ec = info[c]["eta"]
            nb = [tid for tid, d in info.items() if abs(d["eta"] - ec) <= 2.0]
            eng = sum(1 for tid in nb if engaged.get(tid, 0) > 0)
            frac = eng / float(len(nb)) if nb else 0.0
            key = (round(frac, 3), ec)
            if bkey is None or key < bkey:
                bkey, best = key, c
        intercept.append(best)
        engaged[best] = engaged.get(best, 0) + 1
        cover_eta[best] = info[best]["r"] / (i_speed + info[best]["sp"])

    # Gun: nearest striker that no interceptor will reach in time; otherwise nearest.
    gun = None
    if ammo > 0:
        inrange = [tid for tid, d in info.items() if d["r"] <= gun_range]
        if inrange:
            def covered(tid):
                return engaged.get(tid, 0) > 0 and cover_eta.get(tid, 1e9) < info[tid]["eta"] - 0.5
            unc = [tid for tid in inrange if not covered(tid)]
            pool = unc if unc else inrange
            gun = min(pool, key=lambda tid: info[tid]["r"])

    return {"intercept": intercept, "retarget": retarget, "gun": gun}
