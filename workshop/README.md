# Swarm Colosseum workshop

Swarm Colosseum is a strategy game played by programs. One bot, the **attacker**, sends
drones at a base. The other, the **defender**, tries to stop them with interceptors and a
short-range gun. Everything is made up: distances are in `u`, time is in `ticks`, money
is in `credits`. It's a game and a puzzle, not a model of anything real.

You will write bots in Python. Your bot is one file with one function, `act(obs)`. Every
tick the game hands it what it can see (`obs`) and it answers with what to do.

## Run your first match

From the folder that holds `workshop/` (use `python` instead of `python3` on Windows):

    python3 workshop/play.py workshop/starters/attackers/straight_line.py --vs nearest_first --seed 3

It prints who won, and writes `my_match.html`. Open that file in a browser to watch the
match. Change `--seed` to play the same two bots in a different random world; the same
seed always gives exactly the same match.

Leave out `--vs` to see which opponents you can play against.

## The starter bots

Each one has a single `# TODO` showing you where to start.

| attackers (`starters/attackers/`) | defenders (`starters/defenders/`) |
|---|---|
| `straight_line.py`: strikers from one direction | `closest_first.py`: interceptor at the nearest drone |
| `screen_then_strike.py`: decoys first, then strikers | `look_before_firing.py`: chooses which drones are worth it |
| `many_sides.py`: strikers from several directions | `gun_line.py`: saves interceptors, lets the gun work |

## The rules you need

- The attacker has **60 credits**. A striker costs 2 and does 10 damage if it reaches the
  base. A decoy costs 0.5 and does nothing, but from far away it looks like a striker.
- At most **4 launches per tick**. Drones fly at 4 u per tick and start 490 u out.
- The base has **30 HP**: three strikers get through and it's breached.
- The defender has **20 interceptors** (4 credits each, at most 2 launches per tick). One
  bursts when it gets near its target and can catch every drone within 10 u.
- The defender's radar sees 450 u out. Only inside **150 u** can it tell a striker from a
  decoy; before that a track says `"unknown"`.
- The gun reaches 100 u, costs 0.1 a shot, and hits more often the closer the drone is.

## Exercises

Check one with `python3 workshop/check.py <number>`. It runs the starter file you've been
editing. To check a copy somewhere else, add its path at the end.

1. **Switch the gun on.** Edit `starters/defenders/closest_first.py` so it defends
   against `rush` on seeds 1, 3 and 4.
2. **Hide behind decoys.** Edit `starters/attackers/screen_then_strike.py` so it breaches
   `nearest_first` on seeds 0, 1, 3 and 4. *Hint: how long should the screen be?*
3. **Don't shoot at decoys.** Edit `starters/defenders/look_before_firing.py` so it
   defends against `decoy_screen` on every seed from 0 to 5. *Hint: what does an
   interceptor fired at an "unknown" drone usually hit?*
4. **Come from every side.** Edit `starters/attackers/many_sides.py` so it breaches
   `nearest_first` on seeds 0, 1, 2 and 3.
5. **Beat the patient defender.** Keep going with `many_sides.py` until it breaches
   `identify_then_engage` on every seed from 0 to 5. *Hint: check which entries of
   `BEARINGS` actually get used each tick; you may need to change the code, not just the
   list.* Then watch a replay closely: what happens to drones flying close together when an
   interceptor bursts?

Got stuck? Watch the replay of a match you lost. It usually shows you why.

## What the workshop will and won't run

`play.py` and `check.py` only run **your own file**, and only after it passes the same
checks the arena uses for every bot: only safe imports like `math` and `random`, no
`open`, `exec` or `eval`, nothing that starts and ends with `__`. Opponents are chosen by
name from the game's built-in bots. Your bot runs on your computer as you, so only run
files you wrote yourself.
