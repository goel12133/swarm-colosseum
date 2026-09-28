"""Sandbox tests: the container has to contain, and the boundary must not change results.

These run real containers, so they are slower than the rest of the suite and skip cleanly
where Docker is unavailable.
"""
import json
import subprocess
import time
from pathlib import Path

import pytest

from colosseum.sandbox import SandboxedPolicy, SandboxLimits, docker_available
from colosseum.sim import replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "bots" / "attackers"
D = ROOT / "bots" / "defenders"
F = ROOT / "tests" / "fixtures"

pytestmark = pytest.mark.skipif(not docker_available(), reason="docker not available")

FAST = SandboxLimits(tick_timeout=0.5, start_timeout=25.0, max_restarts=2)


def test_container_has_no_network():
    """The flag is only worth having if it is checked."""
    out = subprocess.run(
        ["docker", "run", "--rm", "--network=none", "--cap-drop=ALL",
         "--user", "65534:65534", "python:3.12-slim", "python", "-c",
         "import socket;socket.create_connection(('1.1.1.1',53),timeout=3)"],
        capture_output=True, text=True, timeout=120)
    assert out.returncode != 0
    assert "Error" in out.stderr or "error" in out.stderr.lower()


def test_a_bot_that_opens_a_socket_fails_and_the_match_survives():
    res = run_match(F / "socket_bot.py", D / "gun_only.py", 0, sandbox=True, limits=FAST)
    meta = res["meta"]
    assert meta["attacker_errors"]["policy_errors"] > 0
    assert sum(meta["drones_launched"].values()) == 0       # every act() was a no-op
    assert meta["ticks"] > 0
    assert meta["outcome"] == "defended"


def test_a_busy_looping_bot_is_cut_at_the_tick_timeout():
    start = time.monotonic()
    res = run_match(F / "busy_bot.py", D / "gun_only.py", 0, sandbox=True, limits=FAST)
    elapsed = time.monotonic() - start
    meta = res["meta"]
    assert meta["attacker_errors"]["policy_errors"] > 0
    assert meta["ticks"] == 600, "the match must still run to its natural end"
    # Without the timeout this would never return at all; with restarts capped it is bounded.
    assert elapsed < 120, f"busy bot was not contained quickly enough ({elapsed:.0f}s)"


def test_a_bot_that_exhausts_memory_dies_without_taking_the_match_down():
    res = run_match(F / "memory_bot.py", D / "gun_only.py", 0, sandbox=True, limits=FAST)
    meta = res["meta"]
    assert meta["attacker_errors"]["policy_errors"] > 0
    assert meta["ticks"] > 0
    assert meta["outcome"] == "defended"


def test_a_dead_policy_stops_costing_time():
    """After max_restarts the policy is treated as dead and calls become instant no-ops."""
    p = SandboxedPolicy(F / "busy_bot.py", "attacker", FAST)
    try:
        for _ in range(FAST.max_restarts + 2):
            p.act({"tick": 1})
        assert p.dead
        t = time.monotonic()
        for _ in range(50):
            assert p.act({"tick": 1}) == {}
        assert time.monotonic() - t < 1.0
        assert p.policy_errors >= FAST.max_restarts
    finally:
        p.close()


@pytest.mark.parametrize("attacker,defender,seed", [
    ("rush", "nearest_first", 0),
    ("flanker", "layered", 2),
    ("trickle", "identify_then_engage", 5),
])
def test_sandboxed_replays_are_identical_to_in_process(attacker, defender, seed):
    """Determinism must survive the container boundary, or sandboxed results are a
    different game from the in-process ones."""
    plain = replay_json(run_match(A / f"{attacker}.py", D / f"{defender}.py", seed))
    boxed = replay_json(run_match(A / f"{attacker}.py", D / f"{defender}.py", seed,
                                  sandbox=True))
    if plain != boxed:                               # report where, not just that
        pm, bm = json.loads(plain)["meta"], json.loads(boxed)["meta"]
        differing = {k: (pm[k], bm[k]) for k in pm if pm[k] != bm[k]}
        pytest.fail(f"sandboxed run differs from in-process: {differing or 'frames/events'}")
