"""Engine fuzzer and invariants (backlog 3.9).

Seeded and standard-library only (no `hypothesis`; see DECISIONS.local.md). Each trajectory
is one full match between two random policies defined here, in this file. They are trusted
code, not bots: nothing is loaded from bots/, so this runs on the host without the sandbox.

A trajectory is fixed by one integer. From it come the rules variant, the match seed, and
the two policies' own random streams, so a failure is reproduced with
`python3 -m colosseum.fuzz --start <n> --n 1`.

Checked on every tick (through the engine's own end-of-tick `_frame` hook):
  * budget, stock and ammo stay within [0, start] and never rise
  * spend matches launches: budget used = cost of drones launched, stock used =
    interceptors launched, ammo used = shots fired
  * per-tick launch caps hold for drones and interceptors
  * HP stays within [0, max] and never rises
  * every drone and interceptor position and velocity is finite
  * per drone type, launched = killed + impacted + alive
Checked per match:
  * the match ends by rules.max_ticks
  * the result is strict JSON (no NaN or Infinity)
  * a second run of the same trajectory gives a byte-identical replay

About one action in eight is deliberately malformed (wrong types, NaN, infinities, huge
integers, unknown ids). The contract in policy.py is that a bot can never crash a match,
so those must be counted as invalid, not raised.
"""
import argparse
import json
import math
import random
import sys
import time

from .rules import SEASON0
from .sim import Match, replay_json

# Rules variants within sane ranges, so the caps are exercised at their edges as well as at
# the season's values. Built with Rules.tuned; rules.py itself is never touched.
VARIANTS = (
    SEASON0,
    SEASON0.tuned(interceptor_kill_prob=1.0, gun_pk_scale=0.95),
    SEASON0.tuned(attacker_budget=200.0, interceptor_stock=60, gun_ammo=400),
    SEASON0.tuned(attacker_budget=3.0, interceptor_stock=1, gun_ammo=1),
    SEASON0.tuned(attacker_launches_per_tick=1, interceptor_launches_per_tick=1,
                  blast_radius=40.0, track_noise_sigma=0.0),
    SEASON0.tuned(max_ticks=50, interceptor_lifetime=5),
)

# Values a bot can actually produce: the sandbox decodes replies with json.loads, which
# accepts NaN, Infinity and integers of any length.
HOSTILE = (float("nan"), float("inf"), float("-inf"), 10 ** 400, -10 ** 400, 1e308,
           True, None, "1", [1], {"a": 1}, -1, 0, 2 ** 63)


class FuzzError(AssertionError):
    pass


class _Fuzzer:
    """PolicyRunner-compatible surface; actions drawn from its own Random."""
    role = None

    def __init__(self, seed):
        self.name = f"fuzz_{self.role}"
        self.seed = seed
        self.rng = random.Random(seed)
        self.policy_errors = 0
        self.invalid_actions = 0
        self.last_error = ""

    def reset(self, seed):
        self.rng = random.Random(self.seed * 1_000_003 + seed)

    def hostile(self):
        return self.rng.choice(HOSTILE)

    @property
    def stats(self):
        return dict(policy_errors=self.policy_errors, invalid_actions=self.invalid_actions,
                    last_error=self.last_error)


class FuzzAttacker(_Fuzzer):
    role = "attacker"

    def act(self, obs):
        r = self.rng
        bad = r.random() < 0.125
        launch = []
        for _ in range(r.choice((0, 0, 0, 1, 2, 4, 7))):
            item = dict(type=r.choice(("striker", "striker", "decoy")),
                        bearing=r.uniform(-720.0, 720.0))
            if bad and r.random() < 0.5:
                item[r.choice(("type", "bearing"))] = self.hostile()
            launch.append(item)
        ids = [d["id"] for d in obs["drones"]]
        steer = {}
        for did in r.sample(ids, min(len(ids), r.choice((0, 0, 1, 3)))):
            steer[str(did)] = (None if r.random() < 0.2
                               else [r.uniform(-600.0, 600.0), r.uniform(-600.0, 600.0)])
        if bad:
            steer[r.choice((str(r.randint(-5, 500)), "x", "1e999", "NaN",
                            float("nan"), float("inf"), 10 ** 400))] = \
                r.choice(([self.hostile(), 0.0], [0.0, self.hostile()], self.hostile()))
        action = dict(launch=launch, steer=steer)
        if bad and r.random() < 0.2:
            action[r.choice(("launch", "steer"))] = self.hostile()
        return action


class FuzzDefender(_Fuzzer):
    role = "defender"

    def act(self, obs):
        r = self.rng
        bad = r.random() < 0.125
        ids = [t["id"] for t in obs["tracks"]]
        action = {}
        if ids and r.random() < 0.3:
            action["intercept"] = [r.choice(ids) for _ in range(r.choice((1, 2, 3)))]
        mine = [i["id"] for i in obs["interceptors"]]
        if mine and ids and r.random() < 0.1:
            action["retarget"] = {str(r.choice(mine)): r.choice(ids + [999_999])}
        if ids and r.random() < 0.5:
            action["gun"] = r.choice(ids)
        if bad:
            key = r.choice(("intercept", "retarget", "gun"))
            if key == "intercept":
                action[key] = r.choice(([self.hostile()], self.hostile()))
            elif key == "retarget":
                action[key] = r.choice(({"1": self.hostile()}, {float("inf"): 1},
                                        self.hostile()))
            else:
                action[key] = self.hostile()
        return action


class CheckedMatch(Match):
    """A Match that checks the invariants at the end of every tick.

    The check rides on `_frame`, which `run` calls once before the first tick and once at
    the end of every tick, so the engine's own loop is what gets tested, unmodified.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        r = self.rules
        self._prev = None
        self._spent_by_drones = 0.0
        self._seen_drones = 0
        self._seen_interceptors = 0
        self._start = (r.attacker_budget, r.interceptor_stock, r.gun_ammo, r.asset_hp)

    def fail(self, msg):
        raise FuzzError(f"tick {self.tick}: {msg}")

    def _frame(self):
        self.check()
        super()._frame()

    def check(self):
        r = self.rules
        budget0, stock0, ammo0, hp0 = self._start
        if self.tick > r.max_ticks:
            self.fail(f"tick beyond max_ticks {r.max_ticks}")
        if not (-1e-9 <= self.budget <= budget0 + 1e-9):
            self.fail(f"budget {self.budget} outside [0, {budget0}]")
        if not 0 <= self.stock <= stock0:
            self.fail(f"stock {self.stock} outside [0, {stock0}]")
        if not 0 <= self.ammo <= ammo0:
            self.fail(f"ammo {self.ammo} outside [0, {ammo0}]")
        if not 0 <= self.hp <= hp0:
            self.fail(f"hp {self.hp} outside [0, {hp0}]")
        if self._prev is not None:
            budget, stock, ammo, hp = self._prev
            if self.budget > budget + 1e-9:
                self.fail("budget rose")
            if self.stock > stock or self.ammo > ammo:
                self.fail("stock or ammo rose")
            if self.hp > hp:
                self.fail(f"hp rose {hp} -> {self.hp}")
        self._prev = (self.budget, self.stock, self.ammo, self.hp)

        new_drones = [d for k, d in sorted(self.drones.items()) if k > self._seen_drones]
        if len(new_drones) > r.attacker_launches_per_tick:
            self.fail(f"{len(new_drones)} drones launched in one tick")
        self._spent_by_drones += sum(r.cost_of(d.type) for d in new_drones)
        self._seen_drones = max(self.drones, default=0)
        new_int = [k for k in self.interceptors if k > self._seen_interceptors]
        if len(new_int) > r.interceptor_launches_per_tick:
            self.fail(f"{len(new_int)} interceptors launched in one tick")
        self._seen_interceptors = max(self.interceptors, default=0)

        if abs((budget0 - self.budget) - self._spent_by_drones) > 1e-6:
            self.fail(f"budget used {budget0 - self.budget} != drones bought "
                      f"{self._spent_by_drones}")
        if stock0 - self.stock != self.interceptors_launched or \
                self.interceptors_launched != len(self.interceptors):
            self.fail("stock used != interceptors launched")
        if ammo0 - self.ammo != self.shots_fired:
            self.fail("ammo used != shots fired")

        for kind, objs in (("drone", self.drones), ("interceptor", self.interceptors)):
            for o in objs.values():
                if not all(math.isfinite(v) for v in (o.x, o.y, o.vx, o.vy)):
                    self.fail(f"{kind} {o.id} has a non-finite position or velocity")
        for t in ("striker", "decoy"):
            alive = sum(1 for d in self.drones.values() if d.alive and d.type == t)
            if self.drones_launched[t] != self.drones_killed[t] + self.drones_impacted[t] + alive:
                self.fail(f"{t}s launched != killed + impacted + alive")


def trajectory(n: int):
    """Everything a trajectory depends on, derived from one integer."""
    r = random.Random(n)
    return VARIANTS[r.randrange(len(VARIANTS))], r.randrange(1 << 31), r.randrange(1 << 31)


def run_one(n: int) -> dict:
    """Run trajectory n twice, checking invariants and replay identity. Raises on failure."""
    rules, seed, pseed = trajectory(n)
    replays = []
    for _ in range(2):
        m = CheckedMatch(FuzzAttacker(pseed), FuzzDefender(pseed + 1), seed, rules=rules)
        res = m.run()
        m.check()
        if m.tick > rules.max_ticks:
            raise FuzzError(f"match ran to tick {m.tick}")
        try:
            json.dumps(res, allow_nan=False)
        except ValueError as exc:
            raise FuzzError(f"result is not strict JSON: {exc}") from None
        replays.append(replay_json(res))
    if replays[0] != replays[1]:
        raise FuzzError("re-simulation gave a different replay")
    return json.loads(replays[0])["meta"]


def run(start: int, n: int) -> dict:
    t0 = time.monotonic()
    failures, ticks, reasons = [], 0, {}
    for k in range(start, start + n):
        try:
            meta = run_one(k)
        except Exception as exc:                      # noqa: BLE001 - report every kind
            failures.append(dict(trajectory=k, error=f"{type(exc).__name__}: {exc}"[:300]))
            continue
        ticks += meta["ticks"]
        reasons[meta["end_reason"]] = reasons.get(meta["end_reason"], 0) + 1
    return dict(start=start, trajectories=n, failed=len(failures), failures=failures[:20],
                ticks=ticks, end_reasons=dict(sorted(reasons.items())),
                seconds=round(time.monotonic() - t0, 1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=500, help="trajectories (default 500)")
    ap.add_argument("--start", type=int, default=None,
                    help="first trajectory (default: today's date as YYYYMMDD * 10000, "
                         "so each night covers new ones)")
    args = ap.parse_args(argv)
    start = args.start if args.start is not None else int(time.strftime("%Y%m%d")) * 10000
    report = run(start, args.n)
    print(json.dumps(report, sort_keys=True))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
