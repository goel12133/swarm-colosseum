"""Inline one replay into viewer/index.html so the viewer works on open.

The viewer itself has no build step and no dependencies -- this only substitutes the
embedded sample, so index.html stays a single self-contained file that can be opened from
disk or dropped on a phone.

    python viewer/build_viewer.py [replay.json]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE.parent / "out" / "replays" / "trickle__nearest_first__s8.json"


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    replay = json.loads(src.read_text())
    replay["meta"]["rules"] = {}          # the viewer does not need the full rule dump
    html = (HERE / "template.html").read_text().replace(
        "__SAMPLE_REPLAY__", json.dumps(replay, separators=(",", ":")))
    out = HERE / "index.html"
    out.write_text(html)
    print(f"embedded {src.name} ({len(replay['frames'])} frames, "
          f"{len(replay['events'])} events) -> {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
