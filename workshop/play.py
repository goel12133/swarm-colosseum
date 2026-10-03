"""Run one match: your bot against one of the arena's baseline bots.

    python workshop/play.py workshop/starters/attackers/straight_line.py --vs nearest_first --seed 3

It prints who won and writes the replay to my_match.html (open it in a browser; it works
offline). Your bot must be your own .py file; the opponent is chosen by name. Run with no
--vs to see the names.
"""
import argparse
import sys
from pathlib import Path

import kit


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run one match against a baseline bot.")
    ap.add_argument("bot", help="your bot, a .py file")
    ap.add_argument("--vs", help="the opponent's name (run without it to list them)")
    ap.add_argument("--seed", type=int, default=0,
                    help="which random world to play in (same seed = same match)")
    ap.add_argument("--replay", default="my_match.html",
                    help="where to write the replay page (default my_match.html)")
    args = ap.parse_args(argv)
    try:
        if not args.vs:
            _, side = kit.student_bot(args.bot)
            other = kit.OTHER[side]
            print(f"Your bot is an {side}. Pick an opponent with --vs, one of these "
                  f"{other}s:\n  " + "\n  ".join(kit.OPPONENTS[other]))
            return 2
        replay = kit.play(args.bot, args.vs, args.seed)
    except kit.NotAllowed as exc:
        print(f"Can't run that: {exc}")
        return 1
    print(kit.summary(replay["meta"]))
    out = Path(args.replay)
    out.write_text(kit.viewer_page(replay))
    print(f"Replay written to {out}. Open it in a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
