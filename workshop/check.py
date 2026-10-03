"""Check an exercise.

    python workshop/check.py 3                   checks starters/defenders/look_before_firing.py
    python workshop/check.py 3 path/to/bot.py    checks your own copy instead
    python workshop/check.py                     facilitator: every bundled solution passes,
                                                 and no unedited starter does (`make workshop`)
"""
import sys

import kit


def check_one(number, path=None):
    ex = kit.BY_NUMBER.get(number)
    if ex is None:
        print(f"There is no exercise {number}. They go from 1 to {len(kit.EXERCISES)}.")
        return 2
    path = path or kit.HERE / "starters" / ex.starter
    print(f"Exercise {ex.number}: {ex.title}. Goal: {ex.goal}.")
    try:
        ok, lines = kit.check(ex, path)
    except kit.NotAllowed as exc:
        print(f"Can't run that: {exc}")
        return 1
    print("\n".join(lines))
    print("Solved!" if ok else "Not yet. Change something and try again.")
    return 0 if ok else 1


def check_all():
    """Every exercise is solvable with its bundled solution, and none is solved before the
    student touches anything."""
    bad = 0
    for ex in kit.EXERCISES:
        solved, _ = kit.check(ex, kit.HERE / "solutions" / ex.solution)
        unedited, _ = kit.check(ex, kit.HERE / "starters" / ex.starter)
        good = solved and not unedited
        bad += not good
        print(f"{'ok  ' if good else 'FAIL'} exercise {ex.number} ({ex.goal}): "
              f"solution {'passes' if solved else 'FAILS'}, "
              f"starter {'already passes' if unedited else 'does not pass yet'}")
    print("all exercises solvable" if not bad else f"{bad} exercise(s) broken")
    return 1 if bad else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return check_all()
    if not argv[0].isdigit():
        print(__doc__)
        return 2
    return check_one(int(argv[0]), argv[1] if len(argv) > 1 else None)


if __name__ == "__main__":
    sys.exit(main())
