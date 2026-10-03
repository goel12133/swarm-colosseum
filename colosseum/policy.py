"""Loading bots, and surviving them.

Two jobs:

* **A fresh module instance per match.** Bots are loaded from a file path under a unique
  module name every time, so a bot that stashes state in a global cannot carry it into the
  next match. `importlib` would otherwise hand back the cached module.
* **A bot must never crash a match.** Every call into a policy is wrapped: an exception, a
  non-dict return, or a malformed field becomes a no-op and increments a counter that ends
  up in the match result. The engine is responsible for the match completing; the bot is
  only responsible for its own actions being sensible.
"""
import importlib.util
import itertools
import math
from pathlib import Path

_COUNTER = itertools.count()

# Bots from these folders are untrusted (written by the house league or submitted from
# outside). They run only inside the sandbox container, never through load_policy on the
# host. Module-level so tests can point it at a scratch folder.
_ROOT = Path(__file__).resolve().parents[1]
UNTRUSTED_DIRS = [_ROOT / "bots" / "house", _ROOT / "bots" / "submitted"]


def is_untrusted(path) -> bool:
    p = Path(path).resolve()
    return any(p.is_relative_to(d.resolve()) for d in UNTRUSTED_DIRS)

ATTACKER = "attacker"
DEFENDER = "defender"


class PolicyError(Exception):
    pass


def load_policy(path, expected_role: str = None) -> "PolicyRunner":
    path = Path(path)
    if not path.exists():
        raise PolicyError(f"no such policy file: {path}")
    if is_untrusted(path):
        raise PolicyError(f"{path} is untrusted and runs only in the sandbox, "
                          "never in-process on the host")
    # A unique module name per load is what makes this a fresh instance rather than the
    # cached one; sys.modules is deliberately not touched.
    mod_name = f"_colosseum_bot_{path.stem}_{next(_COUNTER)}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ("NAME", "ROLE", "act"):
        if not hasattr(module, attr):
            raise PolicyError(f"{path.name} is missing {attr}")
    if expected_role and module.ROLE != expected_role:
        raise PolicyError(f"{path.name} has ROLE {module.ROLE!r}, expected {expected_role!r}")
    return PolicyRunner(module, path)


class PolicyRunner:
    def __init__(self, module, path):
        self.module = module
        self.path = Path(path)
        self.name = module.NAME
        self.role = module.ROLE
        self.policy_errors = 0
        self.invalid_actions = 0
        self.last_error = ""

    def reset(self, seed: int):
        fn = getattr(self.module, "reset", None)
        if fn is None:
            return
        try:
            fn(seed)
        except Exception as exc:
            self.policy_errors += 1
            self.last_error = f"reset: {type(exc).__name__}: {exc}"[:200]

    def act(self, obs: dict) -> dict:
        try:
            action = self.module.act(obs)
        except Exception as exc:
            self.policy_errors += 1
            self.last_error = f"act: {type(exc).__name__}: {exc}"[:200]
            return {}
        if not isinstance(action, dict):
            self.invalid_actions += 1
            return {}
        return action

    @property
    def stats(self) -> dict:
        return dict(policy_errors=self.policy_errors,
                    invalid_actions=self.invalid_actions,
                    last_error=self.last_error)


# --- action sanitising ------------------------------------------------------
# Each returns (clean_value, n_invalid). The engine adds n_invalid to the runner's count,
# so a bot that sends nonsense is measured rather than trusted or crashed on.
#
# Numbers must be finite: the sandbox decodes replies with json.loads, which accepts NaN,
# Infinity and integers of any length. Before the 3.9 fuzzer, `int(inf)` and `float(10**400)`
# raised OverflowError out of the match (and the tournament), and a NaN bearing or waypoint
# gave a drone NaN coordinates for the rest of the match.
_ID_ERRORS = (TypeError, ValueError, OverflowError)


def _finite(v):
    """v as a finite float, or None. bool is an int subclass and stays accepted as before."""
    if not isinstance(v, (int, float)):
        return None
    try:
        f = float(v)
    except OverflowError:
        return None
    return f if math.isfinite(f) else None


def clean_attacker_action(action: dict, rules):
    bad = 0
    launches = []
    raw = action.get("launch", []) if isinstance(action, dict) else []
    if not isinstance(raw, (list, tuple)):
        bad += 1
        raw = []
    for item in raw:
        if not isinstance(item, dict):
            bad += 1
            continue
        dtype = item.get("type")
        bearing = _finite(item.get("bearing"))
        if not isinstance(dtype, str) or dtype not in ("striker", "decoy") or bearing is None:
            bad += 1
            continue
        launches.append((dtype, bearing % 360.0))

    steer = {}
    raw_steer = action.get("steer", {}) if isinstance(action, dict) else {}
    if not isinstance(raw_steer, dict):
        bad += 1
        raw_steer = {}
    for k, v in raw_steer.items():
        try:
            did = int(k)
        except _ID_ERRORS:
            bad += 1
            continue
        if v is None:
            steer[did] = None
        elif (isinstance(v, (list, tuple)) and len(v) == 2
              and _finite(v[0]) is not None and _finite(v[1]) is not None):
            steer[did] = (_finite(v[0]), _finite(v[1]))
        else:
            bad += 1
    return launches, steer, bad


def clean_defender_action(action: dict):
    bad = 0
    intercept = []
    raw = action.get("intercept", []) if isinstance(action, dict) else []
    if not isinstance(raw, (list, tuple)):
        bad += 1
        raw = []
    for tid in raw:
        try:
            intercept.append(int(tid))
        except _ID_ERRORS:
            bad += 1

    retarget = {}
    raw_re = action.get("retarget", {}) if isinstance(action, dict) else {}
    if not isinstance(raw_re, dict):
        bad += 1
        raw_re = {}
    for k, v in raw_re.items():
        try:
            retarget[int(k)] = int(v)
        except _ID_ERRORS:
            bad += 1

    gun = action.get("gun") if isinstance(action, dict) else None
    if gun is not None:
        try:
            gun = int(gun)
        except _ID_ERRORS:
            bad += 1
            gun = None
    return intercept, retarget, gun, bad
