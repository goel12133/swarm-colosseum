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


@pytest.mark.skipif(not docker_image_available(), reason="colosseum-clip image not built")
def test_a_clip_can_come_with_a_gif(tmp_path):
    from colosseum import clip
    info = clip.render(small_replay(tmp_path), tmp_path / "c.mp4", speed=16, gif=True)
    assert (tmp_path / "c.gif").read_bytes()[:6] == b"GIF89a"
    assert info["gif_bytes"] > 1000 and info["under_limit"]


def fake_replays(tmp_path, outcomes):
    d = tmp_path / "replays"
    d.mkdir()
    for seed, outcome in outcomes.items():
        (d / f"a__d__s{seed}.json").write_text(json.dumps({"meta": {"outcome": outcome}}))
    return d


def test_the_showcase_uses_the_lowest_seed_with_the_wanted_outcome(tmp_path):
    from colosseum import clip
    d = fake_replays(tmp_path, {12: "breached", 3: "defended", 7: "breached", 1: "defended"})
    assert clip.pick_seed("a", "d", "breached", d).name == "a__d__s7.json"
    with pytest.raises(LookupError):
        clip.pick_seed("a", "d", "timeout", d)


def test_the_showcase_writes_mp4_gif_and_a_captioned_readme(tmp_path):
    from colosseum import clip
    d = fake_replays(tmp_path, {0: "defended", 1: "breached"})
    calls = []

    def fake_render(replay, out, speed, gif):
        calls.append((replay.name, out.name, gif))
        return dict(path=str(out), bytes=1, frames="1 frames", ticks=[0, 1], speed=speed,
                    gif=str(out.with_suffix(".gif")), gif_bytes=1, under_limit=True)

    picks = [("1_x", "a", "d", "breached", "Title X", "Caption X."),
             ("2_y", "a", "d", "defended", "Title Y", "Caption Y.")]
    clip.showcase(d, tmp_path / "show", picks, fake_render)
    assert calls == [("a__d__s1.json", "1_x.mp4", True), ("a__d__s0.json", "2_y.mp4", True)]
    readme = (tmp_path / "show" / "README.md").read_text()
    assert "![Title X](1_x.gif)" in readme and "Caption Y." in readme
    assert "[mp4](2_y.mp4)" in readme


def test_the_five_launch_clips_are_five_distinct_pairings():
    from colosseum import clip
    assert len(clip.SHOWCASE) == 5
    assert len({(a, d) for _, a, d, *_ in clip.SHOWCASE}) == 5
    assert all(pick[3] in ("breached", "defended") for pick in clip.SHOWCASE)
