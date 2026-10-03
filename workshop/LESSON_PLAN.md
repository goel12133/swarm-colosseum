# Lesson plan: 90 minutes, first-time Python

**Goal:** every student runs a match, reads a bot, changes it, and watches the effect of
their change in a replay. Most finish exercises 1–3; the quick ones reach 5.

**Needs:** one laptop per student (pairs work well too) with Python 3.11 and the workshop
folder copied on (see `FACILITATOR.md`). No internet, no installs, no Docker.

| time | what | how |
|---|---|---|
| 0–10 | **What is this?** | Projector: open a replay. Two programs play a game: drones vs a base. Units are invented (`u`, `ticks`, `credits`). Nobody is steering by hand; the code decides every tick. |
| 10–25 | **Observe a match** | Everyone runs `play.py` with `straight_line` vs `nearest_first`, seed 3 (command in `README.md`), and opens `my_match.html`. Ask: which dots are drones? Where's the base? Who won, and when could you tell? Run seed 4. Same bots, different world. Run seed 3 again. The match is exactly the same. |
| 25–40 | **Read a bot** | Together, open `bots/attackers/rush.py` (19 lines). Find `NAME`, `ROLE`, `act(obs)`. `obs` is a dictionary of what the bot can see; the return value is a dictionary of orders. Then open `starters/attackers/straight_line.py` and compare. |
| 40–50 | **Change one number** | In `straight_line.py`, change `LAUNCHES_PER_TICK` from 1 to 4. Predict first: more drones per tick, more wins? Run seeds 0–5 both ways and count breaches. (With 1 it breaches `nearest_first` on 4 of the 6 seeds, with 4 on 1 of 6.) Watch a replay of each to find out why. Don't explain the reason; exercise 5 is built on it. |
| 50–80 | **Exercises** | Students work through `README.md` exercises 1→5 at their own pace, checking each with `check.py`. Facilitator circulates. Defender-minded students can do 1 and 3 first, attackers 2 and 4. |
| 80–90 | **Share and wrap up** | Two or three students show a replay of something that worked and say why in one sentence. Close: this is how the real arena works too. Bots are scored over many seeds against every other bot, and the interesting ideas get written up in a tactic library. |

**Talking points to keep handy**

- *Why seeds?* The defender's radar is noisy, and interceptors don't always kill. A
  seed fixes the dice, so a result can be repeated and argued about.
- *Why does the gun matter?* It's cheap. Interceptors are expensive and there are only 20.
- *Why do decoys work?* Far away, a decoy and a striker look the same (`"unknown"`).
- *Abstract only.* The game is deliberately not a model of anything real. If a student
  asks how it maps to the real world, the honest answer is that it doesn't, by design.
  The puzzle is the point.

**If you run short of time:** skip 25–40 and read `straight_line.py` directly at 40.
**If you have extra:** `gun_line.py` has no exercise. Challenge students to find an
`ENGAGE_RANGE` that defends against `trickle` on more of seeds 0–5 than 450 does (450
holds 1 of 6; 300 holds 2).
