"""The workshop's engine room: the safe loader, the exercises, and the checker.

Students never import this directly; play.py and check.py do. Everything here runs on a
school laptop with Python 3.11, offline, no Docker: a student's bot runs in-process, on
their own machine, as themselves. That is safe because of what this file refuses to load,
not because of a sandbox:

* the student's bot is exactly one `.py` file they name, a regular file (not a link),
  at most 64 KB, outside the league's untrusted folders (bots/house, bots/submitted);
* it must pass the arena's own static checks (colosseum.submit.check_source) before it is
  loaded: allowlisted imports only (math, random, ...), no open/exec/eval, no dunders. A
  bot that would be refused by the arena is refused here, with the same plain message;
* the opponent is picked by name from the bundled baselines below, never by path, so the
  wrapper cannot be pointed at anyone else's code.

The arena itself never uses this path: league and submitted bots run only in the sandbox.
"""
import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colosseum.policy import load_policy, is_untrusted          # noqa: E402
from colosseum.rules import SEASON0                              # noqa: E402
from colosseum.sim import Match                                  # noqa: E402
from colosseum.submit import MAX_BYTES, Rejected, check_source   # noqa: E402

OPPONENTS = {
    "attacker": {p.stem: p for p in sorted((ROOT / "bots" / "attackers").glob("*.py"))},
    "defender": {p.stem: p for p in sorted((ROOT / "bots" / "defenders").glob("*.py"))},
}
OTHER = {"attacker": "defender", "defender": "attacker"}


class NotAllowed(Exception):
    """The file can't be loaded. The message is meant for a student, as-is."""


def student_bot(path):
    """Check a student's file and load it. Returns (runner, side)."""
    p = Path(path)
    if p.suffix != ".py":
        raise NotAllowed(f"{p} is not a Python file (it should end in .py).")
    if p.is_symlink() or not p.is_file():
        raise NotAllowed(f"{p} is not a file I can find. Check the name and folder.")
    if is_untrusted(p):
        raise NotAllowed(f"{p} is a league bot. The workshop only runs your own file.")
    raw = p.read_bytes()
    if len(raw) > MAX_BYTES:
        raise NotAllowed(f"{p} is over {MAX_BYTES // 1024} KB. A bot is much smaller.")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NotAllowed(f"{p} isn't saved as UTF-8 text.")
    side = _declared_side(source)
    try:
        check_source(source, side)
    except Rejected as exc:
        raise NotAllowed(str(exc))
    return load_policy(p, side), side


def _declared_side(source):
    """ROLE, read with ast (nothing runs). check_source then holds the file to it."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise NotAllowed(f"Python can't read this file: {exc.msg} on line {exc.lineno}.")
    for node in tree.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(t, ast.Name) and t.id == "ROLE" for t in node.targets)
                and node.value.value in OTHER):
            return node.value.value
    raise NotAllowed('The file needs ROLE = "attacker" or ROLE = "defender" at the top.')


def opponent(name, side):
    """A bundled baseline for `side`, by name only."""
    if name not in OPPONENTS[side]:
        raise NotAllowed(f"There is no {side} called {name!r}. Choose one of: "
                         f"{', '.join(OPPONENTS[side])}.")
    return load_policy(OPPONENTS[side][name], side)


def play(bot_path, vs, seed, record=True):
    """One match: the student's bot against a named baseline. Returns the replay dict."""
    mine, side = student_bot(bot_path)
    theirs = opponent(vs, OTHER[side])
    att, dfn = (mine, theirs) if side == "attacker" else (theirs, mine)
    return Match(att, dfn, int(seed), rules=SEASON0, record=record).run()


def viewer_page(replay):
    """The arena's replay viewer with this match embedded: one HTML file, opens offline."""
    spec = importlib.util.spec_from_file_location("build_viewer",
                                                  ROOT / "viewer" / "build_viewer.py")
    viewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viewer)
    return viewer.page_with(replay)


def summary(meta):
    return (f"{meta['attacker']} vs {meta['defender']}, seed {meta['seed']}: "
            f"{meta['outcome']} after {meta['ticks']} ticks, base HP "
            f"{meta['asset_hp']}/{meta['asset_hp_max']}, "
            f"attacker score {meta['score_attacker']:.2f}")


# --- exercises -----------------------------------------------------------------

@dataclass(frozen=True)
class Exercise:
    number: int
    title: str
    starter: str          # file under starters/ the student edits
    solution: str         # file under solutions/ that passes
    vs: str               # bundled opponent
    seeds: tuple          # every one of these must give `want`
    want: str             # "breached" (attacker wins) or "defended" (defender wins)

    @property
    def goal(self):
        seeds = ", ".join(str(s) for s in self.seeds)
        who = "breach" if self.want == "breached" else "defend against"
        return f"{who} {self.vs} on seeds {seeds}"


EXERCISES = [
    Exercise(1, "Switch the gun on", "defenders/closest_first.py",
             "ex1_closest_first.py", "rush", (1, 3, 4), "defended"),
    Exercise(2, "Hide behind decoys", "attackers/screen_then_strike.py",
             "ex2_screen_then_strike.py", "nearest_first", (0, 1, 3, 4), "breached"),
    Exercise(3, "Don't shoot at decoys", "defenders/look_before_firing.py",
             "ex3_look_before_firing.py", "decoy_screen", (0, 1, 2, 3, 4, 5), "defended"),
    Exercise(4, "Come from every side", "attackers/many_sides.py",
             "ex4_many_sides.py", "nearest_first", (0, 1, 2, 3), "breached"),
    Exercise(5, "Beat the patient defender", "attackers/many_sides.py",
             "ex5_many_sides.py", "identify_then_engage", (0, 1, 2, 3, 4, 5), "breached"),
]
BY_NUMBER = {e.number: e for e in EXERCISES}


def check(ex, bot_path):
    """Run the exercise's matches. Returns (passed, one line per seed)."""
    lines, ok = [], True
    for seed in ex.seeds:
        meta = play(bot_path, ex.vs, seed, record=False)["meta"]
        hit = meta["outcome"] == ex.want
        ok = ok and hit
        lines.append(f"  {'PASS' if hit else 'MISS'}  {summary(meta)}")
    return ok, lines
