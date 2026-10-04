# Facilitator guide (one page)

New to this workshop? Read [`TEACHERS.md`](TEACHERS.md) first.

**Before the day.** Copy these folders from the repository onto each laptop, side by side
in one folder: `colosseum/`, `bots/attackers/`, `bots/defenders/`, `viewer/`, `workshop/`.
Leave out `bots/house/`, `out/` and everything else (the wrapper refuses league bots
anyway). Each laptop needs Python 3.11 and nothing else: no internet, no installs, no
Docker. On one laptop, run `make workshop`, or `python workshop/check.py` where there's
no `make` (Windows). It must print `all exercises solvable`. Then run the first `play.py`
command from `README.md` and open `my_match.html` to check that the browser shows the replay.

**Why it is safe to run student code here.** Students' bots run on their own laptops,
in-process, as themselves. The arena's sandbox is for the arena; it isn't needed for
someone running their own file. `play.py` and `check.py` still refuse anything except
the student's own `.py` file (no links, nothing over 64 KB, no league bots). That file
must first pass the arena's static checks: safe imports only, no `open`/`exec`/`eval`,
no double-underscore names. Opponents are picked by name from the built-in bots, never by
path. Tell students: only run files you wrote.

**Common errors and what they mean**

| message | fix |
|---|---|
| `There is no 'def act(obs):'` | indentation or a typo in `def act(obs):` |
| `import X is not allowed` | only math, random, itertools, collections and similar are allowed |
| `Python can't read this file ... on line N` | syntax error; look at line N and the one above |
| `There is no defender called ...` | run `play.py` without `--vs` to list names |
| match runs but the bot does nothing | `act` returned something other than a dictionary, or misspelt a key (`launch`, `steer`, `intercept`, `retarget`, `gun`) |

**Answers** (in `workshop/solutions/`, don't hand them out):
1. `USE_GUN = True`.
2. `SCREEN_TICKS = 4` (2 or more works).
3. `FIRE_AT = ["striker"]`.
4. `BEARINGS = [0.0, 90.0, 180.0, 270.0]`.
5. Give every striker its own bearing (a counter times 12°). Drones in a line die together
   because one burst catches everything within 10 u, so spreading them means each of the
   20 interceptors can take at most one of the 30 strikers. This is the same lesson as
   the "change one number" segment.

**Tone.** The game is abstract on purpose: invented units, no real equipment, no real
places. Keep it there. If a student wants to make it "realistic", steer them back to the
puzzle; that is the house rule of the whole project, not a workshop restriction.

**Afterwards.** Students keep their files. Submissions to the public arena aren't open
yet; when they are, `SUBMITTING.md` in the repository will say how.
