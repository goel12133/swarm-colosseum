"""The annealed-assignment defender family: solver quality, determinism, time, honesty."""
import importlib.util
import itertools
import random
import subprocess
from pathlib import Path

import pytest

from colosseum.sim import replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ["annealed_assignment", "annealed_assignment_eager", "greedy_value_model"]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bots" / "defenders" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def brute_force(lin, quad):
    n = len(lin)
    best = min(itertools.product((0, 1), repeat=n),
               key=lambda b: annealed.energy(list(b), lin, quad))
    return annealed.energy(list(best), lin, quad)


annealed = module("annealed_assignment")


@pytest.mark.parametrize("seed", range(20))
def test_the_annealer_finds_the_optimum_of_small_qubos(seed):
    rng = random.Random(seed)
    n = rng.randint(4, 10)
    lin = [rng.uniform(-5, 5) for _ in range(n)]
    quad = {(i, j): rng.uniform(-4, 6) for i in range(n) for j in range(i + 1, n)
            if rng.random() < 0.5}
    bits = annealed.anneal(lin, quad, random.Random(seed), sweeps=200)
    assert annealed.energy(bits, lin, quad) == pytest.approx(brute_force(lin, quad))


def test_the_launch_cap_holds_in_the_model():
    """Build a tick with many urgent strikers: never more launches than the cap."""
    rules = {"interceptor_launches_per_tick": 2, "striker_damage": 10, "blast_radius": 10,
             "interceptor_kill_prob": 0.85, "gun_range": 100, "interceptor_cost": 4,
             "gun_pk_scale": 0.4, "gun_pk_floor": 0.05, "gun_cost": 0.1}
    tracks = [dict(id=i, pos=[60 + 25 * i, 0.0], vel=[-4.0, 0.0], range=60 + 25 * i,
                   cls="striker") for i in range(8)]
    obs = dict(tick=5, rules=rules, tracks=tracks, interceptors=[], stock=20, ammo=120)
    annealed.reset(0)
    action = annealed.act(obs)
    assert 1 <= len(action["intercept"]) <= 2
    assert action["gun"] in {t["id"] for t in tracks if t["range"] <= 100}


@pytest.mark.parametrize("name", FAMILY)
def test_matches_are_deterministic(name):
    d = ROOT / "bots" / "defenders" / f"{name}.py"
    a = ROOT / "bots" / "attackers" / "flanker.py"
    assert replay_json(run_match(a, d, 3)) == replay_json(run_match(a, d, 3))


@pytest.mark.parametrize("name", FAMILY)
def test_it_beats_layered_on_a_quick_check(name):
    """Two seeds against each baseline attacker; the full 10-seed numbers are in PROGRESS."""
    mine = theirs = 0.0
    for a in sorted((ROOT / "bots" / "attackers").glob("*.py")):
        for seed in (0, 1):
            mine += run_match(a, ROOT / "bots" / "defenders" / f"{name}.py", seed,
                              record=False)["meta"]["score_defender"]
            theirs += run_match(a, ROOT / "bots" / "defenders" / "layered.py", seed,
                                record=False)["meta"]["score_defender"]
    assert mine > theirs


def test_no_forbidden_word_anywhere_in_the_repo():
    """The brief: call it what it is -- an optimiser, annealing, a QUBO."""
    word = "qu" + "antum"
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True,
                           text=True).stdout.split()
    hits = [f for f in files + [f"bots/defenders/{n}.py" for n in FAMILY]
            if (ROOT / f).is_file() and word in (ROOT / f).read_text(errors="ignore").lower()]
    assert hits == []


def test_the_greedy_variant_shares_the_value_model_exactly():
    """Same build(), energy() and knobs as annealed_assignment; only the picker differs."""
    import ast

    def parts(name):
        tree = ast.parse((ROOT / "bots" / "defenders" / f"{name}.py").read_text())
        funcs = {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        knobs = {t.id: ast.dump(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()
                 and t.id not in ("NAME", "ROLE")}
        return funcs, knobs
    af, ak = parts("annealed_assignment")
    gf, gk = parts("greedy_value_model")
    for fn in ("build", "energy", "_tti", "_p_striker", "_learn", "reset"):
        assert af[fn] == gf[fn], fn
    assert ak == gk
    assert "greedy" in gf and "anneal" not in gf["_act"]
