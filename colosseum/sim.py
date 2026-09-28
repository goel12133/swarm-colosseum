"""The match engine.

Order of operations within a tick, fixed and relied on by the tests:

  1. build the attacker observation, call the attacker
  2. build the defender observation (this is where sensor noise is drawn), call the defender
  3. apply attacker launches, then steer orders
  4. apply defender interceptor launches, retargets, and the gun order
  5. move drones
  6. move interceptors, guiding on the noisy estimate drawn in step 2
  7. proximity fuses, blasts, kill rolls
  8. gun resolution
  9. impacts on the asset
 10. interceptor lifetime expiry
 11. record a frame (every other tick) and any events
 12. end-condition checks

Determinism: one `random.Random(seed)` per match, and every draw is made while iterating
ids in sorted order, so the result cannot depend on dict ordering. Sensor noise uses
`normalvariate` rather than `gauss` because `gauss` caches a spare value between calls,
which would make the draw sequence depend on call history.
"""
import json
import math
import random
from dataclasses import dataclass, field

from .policy import clean_attacker_action, clean_defender_action, load_policy
from .rules import SEASON0

FRAME_EVERY = 2
COORD_DP = 1


@dataclass
class Drone:
    id: int
    type: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    waypoint: tuple = None
    alive: bool = True
    reached_asset: bool = False


@dataclass
class Interceptor:
    id: int
    target: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    age: int = 0
    alive: bool = True


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _unit_towards(fx, fy, tx, ty):
    dx, dy = tx - fx, ty - fy
    d = math.hypot(dx, dy)
    if d == 0.0:
        return 0.0, 0.0
    return dx / d, dy / d


class Match:
    def __init__(self, attacker, defender, seed, rules=SEASON0, record=True):
        self.attacker = attacker
        self.defender = defender
        self.seed = int(seed)
        self.rules = rules
        self.record = record
        self.rng = random.Random(self.seed)

        self.tick = 0
        self.hp = rules.asset_hp
        self.budget = rules.attacker_budget
        self.stock = rules.interceptor_stock
        self.ammo = rules.gun_ammo

        self.drones = {}
        self.interceptors = {}
        self._next_drone = 1
        self._next_interceptor = 1

        self.noisy = {}              # drone id -> ((x, y), (vx, vy)) as the defender sees it
        self.frames = []
        self.events = []

        self.interceptors_launched = 0
        self.shots_fired = 0
        self.value_destroyed = 0.0
        self.drones_launched = {"striker": 0, "decoy": 0}
        self.drones_killed = {"striker": 0, "decoy": 0}
        self.drones_impacted = {"striker": 0, "decoy": 0}
        self.end_reason = "tick_limit"

    # --- observations -----------------------------------------------------
    def _attacker_obs(self):
        r = self.rules
        return dict(
            tick=self.tick,
            budget=round(self.budget, 6),
            asset=dict(pos=[0.0, 0.0], hp=self.hp, radius=r.asset_radius),
            drones=[dict(id=d.id, type=d.type, pos=[d.x, d.y], vel=[d.vx, d.vy],
                         waypoint=list(d.waypoint) if d.waypoint else None)
                    for d in self._alive_drones()],
            interceptors=[[i.x, i.y] for i in self._alive_interceptors()],
            rules=r.as_dict(),
        )

    def _defender_obs(self):
        r = self.rules
        self.noisy = {}
        tracks = []
        for d in self._alive_drones():                       # sorted by id
            rng_to_asset = _dist(d.x, d.y, 0.0, 0.0)
            if rng_to_asset > r.radar_range:
                continue
            nx = d.x + self.rng.normalvariate(0.0, r.track_noise_sigma)
            ny = d.y + self.rng.normalvariate(0.0, r.track_noise_sigma)
            nvx = d.vx + self.rng.normalvariate(0.0, r.track_noise_sigma / 10.0)
            nvy = d.vy + self.rng.normalvariate(0.0, r.track_noise_sigma / 10.0)
            self.noisy[d.id] = ((nx, ny), (nvx, nvy))
            cls = d.type if rng_to_asset <= r.id_range else "unknown"
            tracks.append(dict(id=d.id, pos=[nx, ny], vel=[nvx, nvy],
                               range=_dist(nx, ny, 0.0, 0.0), cls=cls))
        return dict(
            tick=self.tick,
            asset=dict(pos=[0.0, 0.0], hp=self.hp, radius=r.asset_radius),
            tracks=tracks,
            interceptors=[dict(id=i.id, target=i.target, pos=[i.x, i.y], age=i.age)
                          for i in self._alive_interceptors()],
            stock=self.stock,
            ammo=self.ammo,
            rules=r.as_dict(),
        )

    def _alive_drones(self):
        return [self.drones[k] for k in sorted(self.drones) if self.drones[k].alive]

    def _alive_interceptors(self):
        return [self.interceptors[k] for k in sorted(self.interceptors)
                if self.interceptors[k].alive]

    # --- actions ----------------------------------------------------------
    def _apply_attacker(self, action):
        r = self.rules
        launches, steer, bad = clean_attacker_action(action, r)
        self.attacker.invalid_actions += bad
        for dtype, bearing in launches[:r.attacker_launches_per_tick]:
            cost = r.cost_of(dtype)
            if cost > self.budget + 1e-9:
                continue
            self.budget -= cost
            theta = math.radians(bearing)
            x = r.spawn_radius * math.cos(theta)
            y = r.spawn_radius * math.sin(theta)
            d = Drone(id=self._next_drone, type=dtype, x=x, y=y)
            self._next_drone += 1
            self.drones[d.id] = d
            self.drones_launched[dtype] += 1
        if len(launches) > r.attacker_launches_per_tick:
            self.attacker.invalid_actions += len(launches) - r.attacker_launches_per_tick
        for did, wp in steer.items():
            d = self.drones.get(did)
            if d is not None and d.alive:
                d.waypoint = wp

    def _apply_defender(self, action):
        r = self.rules
        intercept, retarget, gun, bad = clean_defender_action(action)
        self.defender.invalid_actions += bad
        for tid in intercept[:r.interceptor_launches_per_tick]:
            if self.stock <= 0:
                break
            target = self.drones.get(tid)
            if target is None or not target.alive:
                self.defender.invalid_actions += 1
                continue
            self.stock -= 1
            self.interceptors_launched += 1
            i = Interceptor(id=self._next_interceptor, target=tid, x=0.0, y=0.0)
            self._next_interceptor += 1
            self.interceptors[i.id] = i
        if len(intercept) > r.interceptor_launches_per_tick:
            self.defender.invalid_actions += len(intercept) - r.interceptor_launches_per_tick
        for iid in sorted(retarget):
            i = self.interceptors.get(iid)
            if i is not None and i.alive:
                i.target = retarget[iid]
        self._gun_order = gun

    # --- physics ----------------------------------------------------------
    def _move_drones(self):
        r = self.rules
        for d in self._alive_drones():
            speed = r.speed_of(d.type)
            if d.waypoint is not None:
                tx, ty = d.waypoint
                if _dist(d.x, d.y, tx, ty) <= speed:
                    d.waypoint = None
                    tx, ty = 0.0, 0.0
            else:
                tx, ty = 0.0, 0.0
            ux, uy = _unit_towards(d.x, d.y, tx, ty)
            d.vx, d.vy = ux * speed, uy * speed
            d.x += d.vx
            d.y += d.vy

    def _move_interceptors(self):
        r = self.rules
        for i in self._alive_interceptors():
            est = self.noisy.get(i.target)
            target = self.drones.get(i.target)
            if est is None or target is None or not target.alive:
                # coasting: keep the current heading, wait for a retarget or for lifetime
                i.x += i.vx
                i.y += i.vy
                continue
            (ex, ey), (evx, evy) = est
            d = _dist(i.x, i.y, ex, ey)
            lead_t = d / r.interceptor_speed if r.interceptor_speed else 0.0
            aim_x, aim_y = ex + evx * lead_t, ey + evy * lead_t
            ux, uy = _unit_towards(i.x, i.y, aim_x, aim_y)
            i.vx, i.vy = ux * r.interceptor_speed, uy * r.interceptor_speed
            i.x += i.vx
            i.y += i.vy

    def _fuses(self):
        r = self.rules
        for i in self._alive_interceptors():
            target = self.drones.get(i.target)
            if target is None or not target.alive:
                continue
            if _dist(i.x, i.y, target.x, target.y) > r.blast_radius:
                continue
            i.alive = False
            self._event("blast", x=i.x, y=i.y, interceptor=i.id)
            for d in self._alive_drones():
                if _dist(i.x, i.y, d.x, d.y) <= r.blast_radius:
                    if self.rng.random() < r.interceptor_kill_prob:
                        self._kill(d, "interceptor")

    def _gun(self):
        r = self.rules
        tid = getattr(self, "_gun_order", None)
        if tid is None or self.ammo <= 0:
            return
        d = self.drones.get(tid)
        if d is None or not d.alive:
            if tid is not None:
                self.defender.invalid_actions += 1
            return
        dist = _dist(0.0, 0.0, d.x, d.y)
        if dist > r.gun_range:
            self.defender.invalid_actions += 1
            return
        self.ammo -= 1
        self.shots_fired += 1
        self._event("shot", x=d.x, y=d.y, target=d.id)
        if self.rng.random() < r.gun_kill_prob(dist):
            self._kill(d, "gun")

    def _impacts(self):
        r = self.rules
        for d in self._alive_drones():
            if _dist(d.x, d.y, 0.0, 0.0) <= r.asset_radius:
                d.alive = False
                d.reached_asset = True
                self.drones_impacted[d.type] += 1
                dmg = r.striker_damage if d.type == "striker" else 0
                self.hp = max(0, self.hp - dmg)
                self._event("impact", x=d.x, y=d.y, drone=d.id, dtype=d.type, damage=dmg)

    def _expire(self):
        for i in self._alive_interceptors():
            i.age += 1
            if i.age >= self.rules.interceptor_lifetime:
                i.alive = False

    def _kill(self, drone, by):
        drone.alive = False
        self.drones_killed[drone.type] += 1
        self.value_destroyed += self.rules.cost_of(drone.type)
        self._event("kill", x=drone.x, y=drone.y, drone=drone.id, dtype=drone.type, by=by)

    def _event(self, kind, **kw):
        if self.record:
            self.events.append(dict(t=self.tick, kind=kind,
                                    **{k: (round(v, COORD_DP) if isinstance(v, float) else v)
                                       for k, v in kw.items()}))

    def _frame(self):
        if not self.record or self.tick % FRAME_EVERY:
            return
        self.frames.append(dict(
            t=self.tick,
            hp=self.hp,
            d=[[d.id, 1 if d.type == "striker" else 0,
                round(d.x, COORD_DP), round(d.y, COORD_DP)] for d in self._alive_drones()],
            i=[[i.id, round(i.x, COORD_DP), round(i.y, COORD_DP)]
               for i in self._alive_interceptors()],
        ))

    # --- scoring ----------------------------------------------------------
    def _score(self):
        r = self.rules
        spent = self.interceptors_launched * r.interceptor_cost + self.shots_fired * r.gun_cost
        destroyed = self.value_destroyed
        cer = (destroyed / spent) if spent > 0 else 0.0
        if destroyed == 0 and spent == 0:
            economy = 0.5
        else:
            economy = destroyed / (destroyed + spent)
        score_def = 0.6 * (self.hp / r.asset_hp) + 0.4 * economy
        return dict(
            defender_spent=round(spent, 6),
            value_destroyed=round(destroyed, 6),
            cost_exchange_ratio=round(cer, 6),
            score_defender=round(score_def, 6),
            score_attacker=round(1.0 - score_def, 6),
            outcome="defended" if self.hp > 0 else "breached",
        )

    # --- loop -------------------------------------------------------------
    def run(self):
        r = self.rules
        self.attacker.reset(self.seed)
        self.defender.reset(self.seed)
        self._frame()
        while self.tick < r.max_ticks:
            self.tick += 1
            self._apply_attacker(self.attacker.act(self._attacker_obs()))
            self._apply_defender(self.defender.act(self._defender_obs()))
            self._move_drones()
            self._move_interceptors()
            self._fuses()
            self._gun()
            self._impacts()
            self._expire()
            self._frame()
            if self.hp <= 0:
                self.end_reason = "asset_destroyed"
                break
            if self.budget < r.cheapest_drone() - 1e-9 and not self._alive_drones():
                self.end_reason = "attacker_exhausted"
                break
        return self.result()

    def result(self):
        score = self._score()
        meta = dict(
            season=0,
            attacker=self.attacker.name,
            defender=self.defender.name,
            seed=self.seed,
            ticks=self.tick,
            end_reason=self.end_reason,
            asset_hp=self.hp,
            asset_hp_max=self.rules.asset_hp,
            budget_left=round(self.budget, 6),
            stock_left=self.stock,
            ammo_left=self.ammo,
            interceptors_launched=self.interceptors_launched,
            shots_fired=self.shots_fired,
            drones_launched=dict(self.drones_launched),
            drones_killed=dict(self.drones_killed),
            drones_impacted=dict(self.drones_impacted),
            attacker_errors=self.attacker.stats,
            defender_errors=self.defender.stats,
            **score,
        )
        out = dict(meta=meta)
        if self.record:
            out["frames"] = self.frames
            out["events"] = self.events
        return out


def run_match(attacker_path, defender_path, seed, rules=SEASON0, record=True,
              sandbox=False, limits=None):
    """Load both bots fresh, run one match, return the replay dict.

    With sandbox=True each bot runs in its own container instead of in-process. The engine
    is unchanged either way: SandboxedPolicy presents the same surface as PolicyRunner, so
    a bot that behaves differently between the two modes is a bug in the sandbox, which is
    what the determinism test checks.
    """
    if sandbox:
        from .sandbox import SandboxedPolicy, SandboxLimits
        lim = limits or SandboxLimits()
        attacker = SandboxedPolicy(attacker_path, "attacker", lim)
        try:
            defender = SandboxedPolicy(defender_path, "defender", lim)
        except Exception:
            attacker.close()
            raise
        try:
            return Match(attacker, defender, seed, rules=rules, record=record).run()
        finally:
            attacker.close()
            defender.close()
    attacker = load_policy(attacker_path, "attacker")
    defender = load_policy(defender_path, "defender")
    return Match(attacker, defender, seed, rules=rules, record=record).run()


def replay_json(result) -> str:
    return json.dumps(result, sort_keys=True, separators=(",", ":"))
