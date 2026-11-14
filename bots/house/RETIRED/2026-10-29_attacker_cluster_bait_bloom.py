"""Idea: Fly strikers in tight same-bearing bundles that masquerade as blast-clusters to bait one interceptor each, then bloom the bundle apart just before detonation so a single blast kills at most one while the defender's collateral ledger marks the rest "covered" and stalls their re-service.

Why this is not the obvious counter: the packer's documented strength is punishing converging/synchronized rings with multi-kill blasts, and the obvious counter is to SPREAD OUT (depth-shell saturation), which it explicitly falls back against. This bot does the opposite -- it deliberately clusters to trip the opportunistic blast rule, then exploits the collateral-coverage bookkeeping: once a bundle is flagged covered by one blast, the survivors are not re-served until that interceptor resolves, by which time they are inside gun range with a backlog larger than the 2-per-tick launcher can ever clear. No ladder attacker intentionally feeds the blast rule, so this evades the whole design.
"""

import math

NAME = "cluster_bait_bloom"
ROLE = "attacker"

_S = {}


def reset(seed=None):
    _S.clear()
    _S["launched"] = 0
    _S["plan"] = None
    _S["order"] = []
    _S["assign"] = {}


def _plan(rules):
    budget = float(rules.get("attacker_budget", 60.0))
    scost = float(rules.get("striker_cost", 2.0))
    cap = max(1, int(rules.get("attacker_launches_per_tick", 4)))
    n = int(budget // scost)  # all strikers, no decoys (defender ignores decoys)
    n_ticks = int(math.ceil(n / float(cap)))  # one tight bundle per launch tick
    offsets = [-18.0, -6.0, 6.0, 18.0]
    seq = []
    for j in range(n):
        t = j // cap            # bundle index == launch tick
        k = j % cap             # member within bundle
        bearing = 2.0 * math.pi * t / max(1, n_ticks)
        off = offsets[k % len(offsets)]
        jit = (k - (cap - 1) / 2.0) * 0.002  # near-identical path, stays clustered
        seq.append((bearing + jit, off))
    return seq, cap


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"launch": [], "steer": {}}


def _act(obs):
    rules = obs.get("rules", {}) or {}
    if not _S:
        reset()
    if _S.get("plan") is None:
        _S["plan"] = _plan(rules)
    seq, cap = _S["plan"]

    asset = obs.get("asset", {}) or {}
    ax, ay = (asset.get("pos") or [0.0, 0.0])[:2]
    arad = float(asset.get("radius", rules.get("asset_radius", 25.0)))

    # Launch up to cap this tick, one bundle per tick.
    launched = _S["launched"]
    launch = []
    i = launched
    while i < len(seq) and len(launch) < cap:
        bearing, _off = seq[i]
        launch.append({"type": "striker", "bearing": bearing})
        i += 1
    _S["launched"] = i

    # Map drones to plan entries by stable first-seen order (launch order == spawn order).
    drones = obs.get("drones", []) or []
    order = _S["order"]
    assign = _S["assign"]
    for d in drones:
        did = d.get("id")
        if did not in assign:
            idx = len(order)
            order.append(did)
            assign[did] = seq[idx] if idx < len(seq) else (0.0, 0.0)

    R_BLOOM = 130.0  # just inside id_range: cluster already baited, now split
    steer = {}
    for d in drones:
        did = d.get("id")
        if d.get("type") != "striker":
            continue
        p = d.get("pos") or [0.0, 0.0]
        x, y = float(p[0]) - ax, float(p[1]) - ay
        r = math.hypot(x, y)
        if R_BLOOM >= r > 30.0:
            _bearing, off = assign.get(did, (0.0, 0.0))
            if r > 1e-6:
                px, py = -y / r, x / r   # perpendicular to the radial approach
            else:
                px, py = 1.0, 0.0
            # Aim at a distinct point still inside the asset: each bundle-mate
            # peels to its own lane (>=12 apart) so one blast cannot catch them,
            # yet every striker still strikes the asset.
            steer[did] = [ax + px * off, ay + py * off]
        else:
            steer[did] = None

    return {"launch": launch, "steer": steer}
