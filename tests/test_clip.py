"""Replay clips and the viewer page they are drawn with."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from colosseum.sim import replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "tests" / "fixtures"
HOSTILE = '</script><img src=x onerror="alert(1)">'


def viewer():
    spec = importlib.util.spec_from_file_location("bv", ROOT / "viewer" / "build_viewer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def small_replay(tmp_path, attacker_name=None):
    rep = run_match(F / "one_striker.py", F / "idle_def.py", 0)
    if attacker_name:
        rep["meta"]["attacker"] = attacker_name
    p = tmp_path / "r.json"
    p.write_text(replay_json(rep))
    return p


def test_a_hostile_bot_name_cannot_break_out_of_the_page(tmp_path):
    rep = json.loads(small_replay(tmp_path, HOSTILE).read_text())
    html = viewer().page_with(rep)
    assert "</script><img" not in html and "<img src=x" not in html
    assert html.count("</script>") == 1                  # only the page's own
    assert "\\u003c/script\\u003e" in html


def test_the_viewer_never_sets_bot_text_as_html():
    assert "innerHTML" not in (ROOT / "viewer" / "template.html").read_text()


def docker_image_available():
    return shutil.which("docker") and subprocess.run(
        ["docker", "image", "inspect", "colosseum-clip:1"], capture_output=True).returncode == 0


@pytest.mark.skipif(not docker_image_available(), reason="colosseum-clip image not built")
def test_a_clip_renders_small_and_phone_playable(tmp_path):
    from colosseum import clip
    out = tmp_path / "c.mp4"
    info = clip.render(small_replay(tmp_path, HOSTILE), out, speed=4)
    data = out.read_bytes()
    assert data[4:8] == b"ftyp" and len(data) > 1000
    assert info["under_limit"]
