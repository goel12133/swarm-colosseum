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
4x is about 5 seconds and well under 5 MB. With --gif, also a 360-wide 15 fps GIF next to it.

    python -m colosseum.clip --showcase

renders the five launch clips (SHOWCASE below) at 1x as mp4 + gif into out/clips/showcase/, with
a README.md that captions each one. Each pick names a pairing and the outcome the story
needs; the lowest seed whose replay has that outcome is used, so a rerun picks the same match.
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
GIF_MAX_BYTES = 8 * 1024 * 1024
SHOWCASE_DIR = ROOT / "out" / "clips" / "showcase"

# (file stem, attacker, defender, outcome wanted, title, caption). In story order: how a
# match works, then season one's arc as told in research/01.
SHOWCASE = [
    ("1_how_a_match_works", "rush", "nearest_first", "defended",
     "How a match works",
     "A baseline attacker sends everything straight in; a baseline defender shoots the "
     "nearest track. The green circle in the middle is the asset."),
    ("2_decoys_ignored", "decoy_screen", "2026-09-28_defender_discriminating_ledger",
     "defended",
     "A defender that ignores decoys",
     "discriminating_ledger only engages strikers it has identified, so the decoy screen "
     "costs it nothing. Before the ring, no attacker had breached it (0 in 60 matches)."),
    ("3_ring_vs_ledger", "2026-09-29_attacker_synchronized_ring",
     "2026-09-28_defender_discriminating_ledger", "breached",
     "The counter nobody asked for",
     "synchronized_ring holds every striker just outside the ledger's range, then releases "
     "them on one tick. Stock runs out and the survivors arrive together: 10 of 10 seeds."),
    ("4_collapse_vs_ring", "2026-09-29_attacker_synchronized_ring",
     "2026-10-02_defender_loiter_then_collapse", "defended",
     "The answer to the ring",
     "loiter_then_collapse waits over the asset until the closing ring is tighter than one "
     "blast, then fires into it. The ring got through in 1 of 10 seeds."),
    ("5_shell_ring_vs_collapse", "2026-10-04_attacker_interleaved_shell_ring",
     "2026-10-02_defender_loiter_then_collapse", "breached",
     "And the ladder moves on",
     "interleaved_shell_ring, the new #1 attacker, stages its ring in three interleaved "
     "shells so no two strikers ever share one blast, and still arrives in one wave."),
]


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
           speed: int = 4, gif: bool = False) -> dict:
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
             IMAGE, "python", "/in/render.py", str(frm), str(to), str(int(speed))]
            + (["gif"] if gif else []),
            capture_output=True, text=True, timeout=900)
        made = [tmp / "out" / "clip.mp4"] + ([tmp / "out" / "clip.gif"] if gif else [])
        if proc.returncode != 0 or not all(p.exists() for p in made):
            raise RuntimeError(f"clip render failed: {(proc.stderr or proc.stdout)[-600:]}")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(made[0]), out_path)
        if gif:
            shutil.move(str(made[1]), out_path.with_suffix(".gif"))
    size = out_path.stat().st_size
    info = dict(path=str(out_path), bytes=size, frames=proc.stdout.strip(),
                ticks=[frm, to], speed=speed, under_limit=size <= MAX_BYTES)
    if gif:
        gif_size = out_path.with_suffix(".gif").stat().st_size
        info.update(gif=str(out_path.with_suffix(".gif")), gif_bytes=gif_size,
                    under_limit=info["under_limit"] and gif_size <= GIF_MAX_BYTES)
    return info


def pick_seed(attacker: str, defender: str, outcome: str, replays: Path) -> Path:
    """The lowest-seed replay of this pairing with this outcome."""
    found = []
    for p in replays.glob(f"{attacker}__{defender}__s*.json"):
        seed = p.stem.rsplit("__s", 1)[1]
        if seed.isdigit() and json.loads(p.read_text())["meta"].get("outcome") == outcome:
            found.append((int(seed), p))
    if not found:
        raise LookupError(f"no {outcome} replay of {attacker} vs {defender} in {replays}")
    return min(found)[1]


def showcase(replays: Path = ROOT / "out" / "replays", dest: Path = SHOWCASE_DIR,
             picks=SHOWCASE, render_fn=None) -> list:
    """Render the launch clips (mp4 + gif) and a captioned README.md beside them."""
    render_fn = render_fn or render
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    lines =["# Five clips from season one", "",
             "Abstract strategy game, made-up units. Regenerate with "
             "`python -m colosseum.clip --showcase`.", ""]
    done = []
    for stem, att, dfn, outcome, title, caption in picks:
        replay = pick_seed(att, dfn, outcome, Path(replays))
        # 1x: season-one matches mostly end near tick 120, about one second at 4x.
        info = render_fn(replay, dest / f"{stem}.mp4", speed=1, gif=True)
        info.update(stem=stem, replay=replay.name)
        done.append(info)
        lines += [f"## {title}", "", f"![{title}]({stem}.gif)", "", caption, "",
                  f"`{replay.name}` ({outcome}) · [mp4]({stem}.mp4)", ""]
    (dest / "README.md").write_text("\n".join(lines))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("replay", type=Path, nargs="?")
    ap.add_argument("--from", dest="frm", type=int, default=0, help="first tick")
    ap.add_argument("--to", type=int, default=None, help="last tick (default: the end)")
    ap.add_argument("--speed", type=int, default=4, help="as the viewer's buttons (1/4/16)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--gif", action="store_true", help="also write a GIF next to the mp4")
    ap.add_argument("--showcase", action="store_true",
                    help="render the five launch clips into out/clips/showcase/")
    args = ap.parse_args()
    if args.showcase:
        infos = showcase()
    elif args.replay:
        out = args.out or Path("out") / "clips" / (args.replay.stem + ".mp4")
        infos = [render(args.replay, out, args.frm, args.to, args.speed, args.gif)]
    else:
        ap.error("give a replay, or --showcase")
    for info in infos:
        gif = f", gif {info['gif_bytes'] / 1e6:.2f} MB" if "gif" in info else ""
        print(f"{info['path']}: {info['bytes'] / 1e6:.2f} MB{gif}, {info['frames']}, "
              f"ticks {info['ticks'][0]}-{info['ticks'][1]} at {info['speed']}x")
    if not all(info["under_limit"] for info in infos):
        print("warning: over the 5 MB (mp4) / 8 MB (gif) target", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
