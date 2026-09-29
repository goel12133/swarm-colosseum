"""Greedy value model: annealed_assignment's value model with a greedy picker instead of the
annealer. It exists so the ladder shows what the optimiser is worth on its own.

Idea: same energy terms, no search. Launch at the best-valued tracks one by one (skipping
any track inside the blast radius of one already picked) up to the launch cap, whenever the
net value is positive; fire the gun at the best net-valued track in range. build(),
energy() and every knob are identical to annealed_assignment.py, and a test keeps them
identical.

The annealed_assignment docstring describes the model in full.
"""
import math
import random

NAME = "greedy_value_model"
ROLE = "defender"

# --- knobs (the family differs only here) ---------------------------------------
HORIZON = 40.0          # ticks: urgency is 1 at impact, 0 at this time-to-impact or later
COST_SCALE = 1.0        # multiplies the interceptor price in the energy
UNKNOWN_FLOOR = 0.25    # P(striker | unknown) never drops below this
SWEEPS = 60
MAX_LAUNCH_VARS = 12
MAX_GUN_VARS = 6
CLUSTER_SHARE = 0.7

_state = {"seed": 0, "strikers": 0, "decoys": 0, "seen": {}}


def reset(seed):
    _state.update(seed=int(seed or 0), strikers=0, decoys=0, seen={})


# --- the model --------------------------------------------------------------------

def _tti(t):
    p, v, r = t["pos"], t["vel"], max(t["range"], 1e-6)
    closing = -(p[0] * v[0] + p[1] * v[1]) / r
    return r / max(closing, 0.5)


def _p_striker(t, prior):
    c = t.get("cls", "unknown")
    if c == "striker":
        return 1.0
    if c == "decoy":
        return 0.02
    return prior


def _learn(tracks):
    for t in tracks:
        c = t.get("cls")
        if c in ("striker", "decoy") and t["id"] not in _state["seen"]:
            _state["seen"][t["id"]] = c
            _state["strikers" if c == "striker" else "decoys"] += 1
    s, d = _state["strikers"], _state["decoys"]
    return max(UNKNOWN_FLOOR, (s + 1.0) / (s + d + 2.0))


def build(obs):
    rules = obs["rules"]
    tracks = obs.get("tracks") or []
    prior = _learn(tracks)
    damage = float(rules.get("striker_damage", 10))
    blast = float(rules.get("blast_radius", 10.0))
    pk = float(rules.get("interceptor_kill_prob", 0.85))
    gun_range = float(rules.get("gun_range", 100.0))
    cap = int(rules.get("interceptor_launches_per_tick", 2))
    stock = int(obs.get("stock", 0))
    ammo = int(obs.get("ammo", 0))
    price = float(rules.get("interceptor_cost", 4.0))

    chased = {i.get("target") for i in (obs.get("interceptors") or [])}
    base = {}
    for t in tracks:
        urg = max(0.0, min(1.0, (HORIZON - _tti(t)) / HORIZON))
        base[t["id"]] = _p_striker(t, prior) * damage * urg
    pos = {t["id"]: t["pos"] for t in tracks}

    def near(a, b):
        return math.dist(pos[a], pos[b]) <= blast

    value = {}
    for t in tracks:
        extra = sum(base[u["id"]] for u in tracks
                    if u["id"] != t["id"] and near(t["id"], u["id"]))
        value[t["id"]] = base[t["id"]] + CLUSTER_SHARE * extra

    threats = sum(1 for t in tracks if base[t["id"]] > 0)
    scarcity = 1.0 + 0.5 * max(0, threats - stock) / max(1, stock)
    cost = COST_SCALE * price * scarcity

    launch = [t for t in tracks if t["id"] not in chased and base[t["id"]] > 0]
    launch.sort(key=lambda t: -value[t["id"]])
    launch = launch[:MAX_LAUNCH_VARS] if stock > 0 else []
    gun = [t for t in tracks if t["range"] <= gun_range and base[t["id"]] > 0]
    gun.sort(key=lambda t: t["range"])
    gun = gun[:MAX_GUN_VARS] if ammo > 0 else []

    names = [("x", t["id"]) for t in launch] + [("y", t["id"]) for t in gun]
    k = min(cap, stock)
    slack = [("s", j) for j in range(k)] if launch else []
    names += slack
    index = {n: i for i, n in enumerate(names)}
    lin = [0.0] * len(names)
    quad = {}

    def add(a, b, w):
        i, j = index[a], index[b]
        if i == j:
            lin[i] += w
        else:
            key = (min(i, j), max(i, j))
            quad[key] = quad.get(key, 0.0) + w

    big = 2.0 * (max(value.values(), default=1.0) * pk + cost) + 1.0
    for t in launch:
        n = ("x", t["id"])
        add(n, n, -pk * value[t["id"]] + cost)
    for t in gun:
        n = ("y", t["id"])
        pg = max(0.0, float(rules.get("gun_pk_scale", 0.4)) * (1 - t["range"] / gun_range)
                 + float(rules.get("gun_pk_floor", 0.05)))
        add(n, n, -pg * value[t["id"]] + float(rules.get("gun_cost", 0.1)))
    # launch cap as an equality with slack: A (sum x + sum s - k)^2
    if launch:
        group = [("x", t["id"]) for t in launch] + slack
        for a in group:
            add(a, a, big * (1 - 2 * k))
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                add(a, b, 2 * big)
    for i, a in enumerate(gun):
        for b in gun[i + 1:]:
            add(("y", a["id"]), ("y", b["id"]), big)
    for i, a in enumerate(launch):
        for b in launch[i + 1:]:
            if near(a["id"], b["id"]):
                add(("x", a["id"]), ("x", b["id"]), pk * min(value[a["id"]], value[b["id"]]))
        if ("y", a["id"]) in index:
            add(("x", a["id"]), ("y", a["id"]), 0.8 * pk * base[a["id"]])
    return names, lin, quad


def energy(bits, lin, quad):
    e = sum(w for w, b in zip(lin, bits) if b)
    return e + sum(w for (i, j), w in quad.items() if bits[i] and bits[j])


def anneal(lin, quad, rng, sweeps=SWEEPS):
    n = len(lin)
    if n == 0:
        return []
    nbr = [[] for _ in range(n)]
    for (i, j), w in quad.items():
        nbr[i].append((j, w))
        nbr[j].append((i, w))
    bits = [0] * n
    e = 0.0
    best, best_e = bits[:], e
    scale = max([abs(w) for w in lin] + [abs(w) for w in quad.values()] + [1.0])
    t_hi, t_lo = scale, scale * 1e-3
    for s in range(sweeps):
        temp = t_hi * (t_lo / t_hi) ** (s / max(1, sweeps - 1))
        for i in range(n):
            field = lin[i] + sum(w for j, w in nbr[i] if bits[j])
            delta = -field if bits[i] else field
            if delta <= 0 or rng.random() < math.exp(-delta / temp):
                bits[i] ^= 1
                e += delta
                if e < best_e:
                    best, best_e = bits[:], e
    return best


def greedy(names, lin, quad, obs):
    """The whole difference from annealed_assignment: pick, don't search."""
    k = min(int(obs["rules"].get("interceptor_launches_per_tick", 2)), int(obs.get("stock", 0)))
    bits = [0] * len(names)
    xs = sorted((i for i, n in enumerate(names) if n[0] == "x" and lin[i] < 0),
                key=lambda i: lin[i])
    chosen = []
    for i in xs:
        if len(chosen) >= k:
            break
        if any(quad.get((min(i, j), max(i, j)), 0) > 0 for j in chosen):
            continue
        chosen.append(i)
    for i in chosen:
        bits[i] = 1
    ys = sorted((i for i, n in enumerate(names) if n[0] == "y" and lin[i] < 0),
                key=lambda i: lin[i])
    if ys:
        bits[ys[0]] = 1
    return bits


# --- the policy -------------------------------------------------------------------

def _act(obs):
    names, lin, quad = build(obs)
    bits = greedy(names, lin, quad, obs)
    cap = int(obs["rules"].get("interceptor_launches_per_tick", 2))
    launches = [n[1] for n, b in zip(names, bits) if b and n[0] == "x"][:cap]
    guns = [n[1] for n, b in zip(names, bits) if b and n[0] == "y"]

    tracks = {t["id"]: t for t in (obs.get("tracks") or [])}
    retarget = {}
    wanted = [t for t in sorted(tracks.values(), key=_tti)
              if t.get("cls") != "decoy" and t["id"] not in launches]
    busy = {i.get("target") for i in (obs.get("interceptors") or [])
            if i.get("target") in tracks}
    free = [t["id"] for t in wanted if t["id"] not in busy]
    for i in obs.get("interceptors") or []:
        if i.get("target") not in tracks and free:
            retarget[i["id"]] = free.pop(0)
    return {"intercept": launches, "retarget": retarget, "gun": guns[0] if guns else None}


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return {"intercept": [], "retarget": {}, "gun": None}
