"""Render a replay to a phone-friendly video clip.

    python -m colosseum.clip out/replays/rush__layered__s0.json
    python -m colosseum.clip replay.json --from 100 --to 300 --speed 4 --out clip.mp4

How: the replay is embedded in the real viewer page (viewer/template.html, via the same
page_with() that builds viewer/index.html), and headless Chromium runs the viewer's own
draw() for each frame. So there is one source of truth for how a match looks: change the
viewer and the clips change with it. A Python port of the canvas code would have been
simpler to run but would drift from the viewer the first time either was edited.

The browser and ffmpeg run in a container (docker/clip, built on first use) with
--network none, as a non-root user, so nothing is installed on the host. Chromium runs with
its own sandbox off, as it must inside an unprivileged container; the page it loads is our
template plus replay data, and bot names in that data are only ever set as text.

Output: H.264, yuv420p, 30 fps, faststart, 720 x 776. A full 600-tick match at the default
4x is about 5 seconds and well under 5 MB.
"""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .tournament import ROOT

IMAGE = "colosseum-clip:1"
DOCKER_DIR = ROOT / "docker" / "clip"
MAX_BYTES = 5 * 1024 * 1024


def _viewer():
    spec = importlib.util.spec_from_file_location("build_viewer",
                                                  ROOT / "viewer" / "build_viewer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_image():
    if subprocess.run(["docker", "image", "inspect", IMAGE],
                      capture_output=True).returncode != 0:
        print(f"building {IMAGE} (first use only)...", file=sys.stderr)
        subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(DOCKER_DIR)], check=True)


def render(replay_path: Path, out_path: Path, frm: int = 0, to: int = None,
           speed: int = 4) -> dict:
    replay = json.loads(Path(replay_path).read_text())
    replay["meta"]["rules"] = {}
    last_tick = replay["frames"][-1]["t"] if replay["frames"] else 0
    to = last_tick if to is None else min(int(to), last_tick)
    frm = max(0, int(frm))
    if frm > to:
        raise ValueError(f"--from {frm} is after --to {to}")
    ensure_image()
    with tempfile.TemporaryDirectory(prefix="clip_") as tmp:
        tmp = Path(tmp)
        (tmp / "in").mkdir()
        (tmp / "out").mkdir()
        (tmp / "out").chmod(0o777)                  # the container user is uid 10001
        (tmp / "in" / "page.html").write_text(_viewer().page_with(replay))
        shutil.copy(DOCKER_DIR / "render.py", tmp / "in" / "render.py")
        proc = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "--memory", "2g",
             "--cpus", "2", "--pids-limit", "512", "--shm-size", "512m",
             "-v", f"{tmp / 'in'}:/in:ro", "-v", f"{tmp / 'out'}:/out",
             IMAGE, "python", "/in/render.py", str(frm), str(to), str(int(speed))],
            capture_output=True, text=True, timeout=900)
        if proc.returncode != 0 or not (tmp / "out" / "clip.mp4").exists():
            raise RuntimeError(f"clip render failed: {(proc.stderr or proc.stdout)[-600:]}")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp / "out" / "clip.mp4"), out_path)
    size = out_path.stat().st_size
    return dict(path=str(out_path), bytes=size, frames=proc.stdout.strip(),
                ticks=[frm, to], speed=speed, under_limit=size <= MAX_BYTES)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("replay", type=Path)
    ap.add_argument("--from", dest="frm", type=int, default=0, help="first tick")
    ap.add_argument("--to", type=int, default=None, help="last tick (default: the end)")
    ap.add_argument("--speed", type=int, default=4, help="as the viewer's buttons (1/4/16)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or Path("out") / "clips" / (args.replay.stem + ".mp4")
    info = render(args.replay, out, args.frm, args.to, args.speed)
    print(f"{info['path']}: {info['bytes'] / 1e6:.2f} MB, {info['frames']}, "
          f"ticks {info['ticks'][0]}-{info['ticks'][1]} at {info['speed']}x")
    if not info["under_limit"]:
        print("warning: over the 5 MB target", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
