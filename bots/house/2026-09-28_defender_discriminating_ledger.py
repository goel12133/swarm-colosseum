"""
NAME: discriminating_ledger

Target: the trickle and decoy-heavy attackers, and the matches they win against
identify_then_engage (trickle: 0.155) and nearest_first (decoy_screen: 0.107).

The weakness: both of those defenders spend their resources on decoys.
  * nearest_first shoots whatever is closest. In the sample match it killed all
    16 decoys and let 3 strikers through.
  * identify_then_engage fired all 120 gun rounds against a trickle that was half
    decoys, and ran dry before the strikers arrived.

This bot keeps a strict ledger of what each threat is:
  * Interceptors are only ever sent at confirmed strikers, or at unknown tracks
    that are already inside id range (these should not normally exist).
  * Each striker gets exactly one interceptor. Anything else is only launched
    when that striker's interceptor is gone and the striker is still alive.
  * If an interceptor's target disappears, it is retargeted to the most urgent
    striker that has no interceptor.
  * The gun only fires at strikers. It prefers strikers with no interceptor on
    the way, then the closest one. Decoys are never engaged, so ammo lasts
    against a long trickle.
"""
import math

NAME = "discriminating_ledger"
ROLE = "defender"


def reset(seed=None):
    pass


def _tti(t):
    """Rough time until the track reaches the asset (lower = more urgent)."""
    r = float(t.get("range", 1e9))
    v = t.get("vel", [0.0, 0.0]) or [0.0, 0.0]
    p = t.get("pos", [0.0, 0.0]) or [0.0, 0.0]
    closing = 0.0
    if r > 1e-6:
        closing = -(p[0] * v[0] + p[1] * v[1]) / r
    if closing <= 0.1:
        closing = 0.1
    return r / closing


def _act(obs):
    rules = obs.get("rules", {}) or {}
    id_range = float(rules.get("id_range", 150.0))
    gun_range = float(rules.get("gun_range", 100.0))
    launch_cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))

    tracks = obs.get("tracks", []) or []
    ints = obs.get("interceptors", []) or []
    by_id = {t.get("id"): t for t in tracks}

    def is_threat(t):
        c = t.get("cls", "unknown")
        if c == "striker":
            return True
        if c == "unknown" and float(t.get("range", 1e9)) < id_range * 0.9:
            return True
        return False

    threats = [t for t in tracks if is_threat(t)]
    threats.sort(key=_tti)

    covered = {}
    orphans = []
    for it in ints:
        tgt = it.get("target")
        if tgt in by_id and is_threat(by_id[tgt]):
            covered[tgt] = covered.get(tgt, 0) + 1
        else:
            orphans.append(it)

    retarget = {}
    uncovered = [t for t in threats if covered.get(t.get("id"), 0) == 0]
    for it in orphans:
        if not uncovered:
            break
        t = uncovered.pop(0)
        retarget[it.get("id")] = t.get("id")
        covered[t.get("id")] = 1

    intercept = []
    for t in uncovered:
        if len(intercept) >= launch_cap or stock - len(intercept) <= 0:
            break
        intercept.append(t.get("id"))
        covered[t.get("id")] = 1

    gun = None
    if ammo > 0:
        in_range = [t for t in threats if float(t.get("range", 1e9)) <= gun_range]
        if in_range:
            # Prefer strikers with no interceptor en route, then the closest.
            in_range.sort(key=lambda t: (
                1 if covered.get(t.get("id"), 0) > 0 and float(t.get("range", 0)) > 45.0 else 0,
                float(t.get("range", 1e9)),
            ))
            gun = in_range[0].get("id")

    return {"intercept": intercept, "retarget": retarget, "gun": gun}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
