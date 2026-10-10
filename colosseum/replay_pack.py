"""Compact replays for the site (post-launch site trim, 2026-10-10).

The replays in out/replays are the record: the canonical JSON that `make reproduce` checks.
The site serves a packed copy of each one: the same JSON document with each frame's
positions stored as changes from the previous frame, in tenths of a unit, then gzipped.
Every position in a replay is a multiple of 0.1 u, so unpacking gives back the original
replay value for value (tests/test_replay_pack.py checks this on real replays); the one
thing not kept is the sign of a zero (-0.0 comes back as 0.0), which nothing draws or uses.
About 5.5 KB a replay instead of 54 KB.

Packed layout (JSON, inside gzip):
  {"format": "replay-delta-1", "meta": {...}, "events": [...],
   "frames": [[t, hp, drones, interceptors], ...]}
  drones        [[id, type, dx, dy], ...]   dx, dy: change in round(10 * x), round(10 * y)
  interceptors  [[id, dx, dy], ...]         since that id's last frame (0 before its first)
Drones and interceptors keep separate id spaces. The site's viewer unpacks the same layout
in the browser (viewer/template.html, unpackReplay).

    python -m colosseum.replay_pack unpack replays/data/<stem>.json.gz > <stem>.json
"""
import gzip
import json
import sys

FORMAT = "replay-delta-1"


def _pack_rows(rows, prev, kind):
    out = []
    for r in rows:
        x, y = round(r[-2] * 10), round(r[-1] * 10)
        px, py = prev.get((kind, r[0]), (0, 0))
        prev[(kind, r[0])] = (x, y)
        out.append([*r[:-2], x - px, y - py])
    return out


def _unpack_rows(rows, prev, kind):
    out = []
    for r in rows:
        px, py = prev.get((kind, r[0]), (0, 0))
        x, y = px + r[-2], py + r[-1]
        prev[(kind, r[0])] = (x, y)
        out.append([*r[:-2], x / 10, y / 10])
    return out


def pack_doc(replay: dict) -> dict:
    prev = {}
    frames = [[f["t"], f["hp"], _pack_rows(f["d"], prev, "d"), _pack_rows(f["i"], prev, "i")]
              for f in replay["frames"]]
    return {"format": FORMAT, "meta": replay["meta"], "events": replay["events"],
            "frames": frames}


def unpack_doc(doc: dict) -> dict:
    if doc.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} replay")
    prev = {}
    frames = [{"d": _unpack_rows(d, prev, "d"), "hp": hp, "i": _unpack_rows(i, prev, "i"),
               "t": t} for t, hp, d, i in doc["frames"]]
    return {"events": doc["events"], "frames": frames, "meta": doc["meta"]}


def pack(replay: dict) -> bytes:
    """Deterministic: same replay, same bytes (no gzip timestamp, fixed key order)."""
    text = json.dumps(pack_doc(replay), separators=(",", ":"), sort_keys=True)
    return gzip.compress(text.encode(), compresslevel=9, mtime=0)


def unpack(data: bytes) -> dict:
    return unpack_doc(json.loads(gzip.decompress(data)))


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "unpack":
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    with open(sys.argv[2], "rb") as f:
        json.dump(unpack(f.read()), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
