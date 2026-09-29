"""Annealed assignment, eager variant: same model and solver, longer horizon, cheaper
interceptors in the energy and a higher floor on P(striker | unknown), so it commits
earlier and on less evidence.

Annealed assignment: each tick's launch and gun decisions as one small QUBO.

Idea: instead of a greedy rule ("nearest first", "strikers first"), write down what a tick's
decision is worth and let an optimiser pick the whole set at once.

Binary variables, rebuilt every tick:
  x_t = 1  launch an interceptor at track t   (tracks not already chased, top 12 by value)
  y_t = 1  fire the gun at track t            (tracks inside gun range, nearest 6)
  s_k      slack bits that turn "at most K launches" into an equality

Energy to minimise (lower is better):
  - sum_t x_t * pk * V_t                      value of an interceptor at t
      V_t = P(striker | label) * damage * urgency(time to impact)
            + 0.7 * the same for other tracks within the blast radius of t
      P(striker | unknown) is learned in-match from the labels seen so far
  + sum_t x_t * C                             interceptor cost, rising as stock runs short
  - sum_t y_t * pk_gun(range_t) * V_t         value of a gun round (cost 0.1)
  + A * (sum_t x_t + sum_k s_k - K)^2         launch cap and stock, K = min(cap, stock)
  + B * y_a * y_b                             at most one gun target
  + D * x_a * x_b   for a, b within blast     two interceptors into one cluster is waste
  + E * x_t * y_t                             gun and interceptor on the same target

Solved by simulated annealing (standard library, seeded from reset(seed) and the tick, so
deterministic), keeping the best state seen. Retargeting orphaned interceptors stays
greedy: it is not a choice between alternatives worth optimising jointly.

This is a hand-written experiment: does a joint optimiser beat layered's greedy heuristic
under a per-tick time limit? Results are reported whether it does or not.
"""
import math
import random

NAME = "annealed_assignment_eager"
ROLE = "defender"

# --- knobs (the family differs only here) ---------------------------------------
HORIZON = 60.0          # ticks: urgency is 1 at impact, 0 at this time-to-impact or later
COST_SCALE = 0.8        # multiplies the interceptor price in the energy
UNKNOWN_FLOOR = 0.40    # P(striker | unknown) never drops below this
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


# --- the policy -------------------------------------------------------------------

def _act(obs):
    names, lin, quad = build(obs)
    rng = random.Random(_state["seed"] * 1_000_003 + int(obs.get("tick", 0)))
    bits = anneal(lin, quad, rng)
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
