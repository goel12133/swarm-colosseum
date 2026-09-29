"""Submission pipeline: static checks on the host, smoke test in the sandbox."""
import json
from pathlib import Path

import pytest

from colosseum import submit as sb
from colosseum.policy import is_untrusted
from colosseum.sandbox import SandboxLimits, docker_available

CLEAN = '''"""Idea: launch a steady trickle from rotating bearings."""
import math

NAME = "steady_three"
ROLE = "attacker"


def act(obs):
    rules = obs["rules"]
    if obs["tick"] % 6 or obs["budget"] < rules["striker_cost"]:
        return {"launch": [], "steer": {}}
    b = (obs["tick"] * 40) % 360
    return {"launch": [{"type": "striker", "bearing": b}], "steer": {}}
'''

FAST = SandboxLimits(tick_timeout=0.5, max_restarts=1)


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "SUBMITTED", tmp_path / "submitted")
    monkeypatch.setattr(sb, "REJECTED", tmp_path / "rejected")


def write(tmp_path, source, name="bot.py"):
    p = tmp_path / name
    p.write_text(source)
    return p


def body(act_body, header="", name="x_bot", role="attacker"):
    return (f'{header}\nNAME = "{name}"\nROLE = "{role}"\n\n\ndef act(obs):\n'
            + "\n".join("    " + l for l in act_body.splitlines()) + "\n")


# --- static checks: every forbidden construct gets a reason ---------------------------

FORBIDDEN = [
    ("import os", body("return {}", header="import os"), "import os"),
    ("import subprocess", body("return {}", header="import subprocess"), "subprocess"),
    ("import socket", body("return {}", header="import socket"), "socket"),
    ("from os import system", body("return {}", header="from os import system"), "from os"),
    ("relative import", body("return {}", header="from . import sim"), "not allowed"),
    ("private import", body("return {}", header="from random import _os"), "_os"),
    ("import *", body("return {}", header="from math import *"), "import *"),
    ("open", body("open('/etc/passwd')\nreturn {}"), "`open`"),
    ("exec", body("exec('1')\nreturn {}"), "`exec`"),
    ("eval", body("return eval('{}')"), "`eval`"),
    ("compile", body("compile('1', 'f', 'eval')\nreturn {}"), "`compile`"),
    ("__import__", body("__import__('os')\nreturn {}"), "__import__"),
    ("getattr", body("getattr(obs, 'x')\nreturn {}"), "`getattr`"),
    ("globals", body("globals()\nreturn {}"), "`globals`"),
    ("dunder attribute", body("x = ().__class__\nreturn {}"), "__class__"),
    ("dunder name", body("x = __builtins__\nreturn {}"), "__builtins__"),
    ("dunder string", body("x = obs['__class__']\nreturn {}"), "hidden attribute"),
    ("private attribute", body("x = random._os\nreturn {}", header="import random"),
     "private"),
    ("frame walk", body("g = (i for i in [])\nf = g.gi_frame\nreturn {}"), "gi_frame"),
    ("os.system via attr", body("x = obs.system\nreturn {}"), "system"),
    ("top-level loop", body("return {}") + "\nwhile True:\n    pass\n", "top level"),
    ("top-level call", body("return {}") + "\nprint('hi')\n", "top level"),
    ("async", body("return {}") + "\nasync def f():\n    return 1\n", "async"),
    ("syntax error", "def act(obs)\n  return {}\n", "can't read"),
    ("no act", 'NAME = "x_bot"\nROLE = "attacker"\n', "def act"),
    ("bad NAME", body("return {}", name="<img src=x>"), "NAME must be"),
    ("NAME not a constant", body("return {}").replace('NAME = "x_bot"', 'NAME = "a" + "b"'),
     "plain string"),
    ("wrong ROLE", body("return {}", role="defender"), "must match"),
]


@pytest.mark.parametrize("label,source,reason", FORBIDDEN, ids=[f[0] for f in FORBIDDEN])
def test_each_forbidden_construct_is_rejected_with_a_reason(tmp_path, label, source, reason):
    result = sb.submit(write(tmp_path, source), "attacker", "ada")
    assert result["status"] == "rejected", label
    assert reason in result["reason"], result["reason"]
    assert Path(result["note"]).exists()
    assert not (tmp_path / "submitted").exists()           # nothing was kept


def test_oversized_non_utf8_and_bad_handles_are_rejected(tmp_path):
    big = write(tmp_path, CLEAN + "#" * sb.MAX_BYTES)
    assert "limit" in sb.submit(big, "attacker", "ada")["reason"]
    bad = tmp_path / "latin.py"
    bad.write_bytes(b"NAME = '\xff'\n")
    assert "UTF-8" in sb.submit(bad, "attacker", "ada")["reason"]
    clean = write(tmp_path, CLEAN)
    for handle in ("", "a", "Ada", "ada/../x", "x" * 30):
        assert sb.submit(clean, "attacker", handle)["status"] == "rejected"


def test_the_checks_never_execute_the_file(tmp_path):
    marker = tmp_path / "ran"
    src = f'open({str(marker)!r}, "w").write("x")\n' + body("return {}")
    sb.submit(write(tmp_path, src), "attacker", "ada")
    assert not marker.exists()


def test_a_normal_bot_passes_the_static_checks():
    assert sb.check_source(CLEAN, "attacker") == "steady_three"
    ok = body("seen = deque()\nreturn {}",
              header="from collections import deque\nimport heapq")
    assert sb.check_source(ok, "attacker") == "x_bot"
    cls = ('NAME = "c_bot"\nROLE = "defender"\nclass Memo:\n    def __init__(self):\n'
           '        self._seen = set()\n\n\ndef act(obs):\n    return {}\n')
    assert sb.check_source(cls, "defender") == "c_bot"      # own self._x is fine


# --- sandbox --------------------------------------------------------------------------

needs_docker = pytest.mark.skipif(not docker_available(), reason="docker not available")


@needs_docker
def test_a_clean_bot_is_accepted_with_metadata(tmp_path):
    result = sb.submit(write(tmp_path, CLEAN), "attacker", "ada")
    assert result["status"] == "accepted", result
    dest = tmp_path / "submitted" / "attacker" / "ada__steady_three.py"
    assert dest.read_text() == CLEAN
    meta = json.loads(dest.with_suffix(".meta.json").read_text())
    assert meta["author"] == "ada" and len(meta["sha256"]) == 64
    assert meta["validation"]["static"] == "passed" and "ticks" in meta["validation"]["smoke"]


@needs_docker
def test_resubmitting_the_same_file_is_a_no_op(tmp_path):
    p = write(tmp_path, CLEAN)
    assert sb.submit(p, "attacker", "ada")["status"] == "accepted"
    before = sorted((tmp_path / "submitted").rglob("*"))
    again = sb.submit(p, "attacker", "someone_else")
    assert again["status"] == "duplicate" and "Already accepted" in again["message"]
    assert sorted((tmp_path / "submitted").rglob("*")) == before


@needs_docker
def test_a_bot_that_passes_ast_but_crashes_in_the_sandbox_is_rejected(tmp_path):
    src = body("raise ValueError('boom')")
    result = sb.submit(write(tmp_path, src), "attacker", "ada", limits=FAST)
    assert result["status"] == "rejected"
    assert "error on every tick" in result["reason"] and "boom" in result["reason"]


@needs_docker
def test_a_busy_loop_is_rejected_by_the_tick_timeout(tmp_path):
    src = body("while True:\n    pass")
    result = sb.submit(write(tmp_path, src), "attacker", "ada", limits=FAST)
    assert result["status"] == "rejected"
    assert "stopped answering" in result["reason"] and "0.5 s" in result["reason"]


def test_submitted_bots_are_untrusted_on_the_host():
    root = Path(sb.__file__).resolve().parents[1]
    assert is_untrusted(root / "bots" / "submitted" / "attacker" / "ada__x.py")


def test_submitting_md_matches_the_code():
    """The player guide's example bot passes, and its allowlist is the real one."""
    import re
    doc = (Path(sb.__file__).resolve().parents[1] / "SUBMITTING.md").read_text()
    example = doc.split("## A complete first bot", 1)[1].split("```python\n", 1)[1]
    example = example.split("```", 1)[0]
    assert sb.check_source(example, "attacker") == "even_trickle"
    listed = set(re.findall(r"`(\w+)`", doc.split("**Allowed imports**", 1)[1]
                            .split("**Not allowed**", 1)[0]))
    assert listed == set(sb.ALLOWED_IMPORTS)
    assert f"{sb.MAX_BYTES // 1024} KB" in doc
