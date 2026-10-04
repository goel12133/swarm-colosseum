"""Rebuild the published results from bots and seeds, and check them byte for byte.

    make reproduce            # = python3 -m colosseum.reproduce

The single command a sceptical reader runs on a fresh clone. It replays every match of the
current roster (every bot in bots/, 10 seeds each) in the sandbox, from scratch: no result
cache, no replays, nothing from out/. Then it compares the rebuilt leaderboard.json,
matrix.json and breaches.json with the copies committed in results/. Byte-identical or it
fails, and it says which file differs.

results/ is committed by the league after each night (colosseum.ops after-night), together
with that night's new house bots, so a clone at any commit holds both the bots and the
results they produce. Needs Docker (every bot runs in its own container); takes roughly
6-8 minutes on a 4-core machine for the current roster.
"""
import argparse
import filecmp
import sys
import tempfile
import time
from pathlib import Path

from .tournament import ROOT, run_tournament

RESULTS = ROOT / "results"
FILES = ("leaderboard.json", "matrix.json", "breaches.json")


def reproduce(results: Path = RESULTS, seeds: int = 10, workers=None):
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="reproduce_") as tmp:
        out = Path(tmp)
        run_tournament(seeds=seeds, out=out, sandbox=True, quiet=True, cache=False,
                       write_replays=False, workers=workers)
        report = {f: filecmp.cmp(out / f, results / f, shallow=False)
                  if (results / f).exists() else None for f in FILES}
    return report, round(time.monotonic() - t0, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    if not (RESULTS / "leaderboard.json").exists():
        print("no committed results/ to compare against")
        return 2
    print("replaying every match in the sandbox from scratch (no cache) ...", flush=True)
    report, seconds = reproduce(workers=args.workers)
    for f, same in report.items():
        print(f"  {f:18} {'identical' if same else 'MISSING' if same is None else 'DIFFERS'}")
    ok = all(report.values())
    print(f"{'REPRODUCED' if ok else 'NOT REPRODUCED'} in {seconds:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
