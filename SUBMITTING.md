# Submitting a bot to Swarm Colosseum

> **Not open yet.** Everything below works on the league's own machine, but there is no way
> to send a file in over the internet yet. This page is here so you can get a bot ready.

Swarm Colosseum is a strategy game played by programs. You write one Python file. Every
night it plays every bot on the other side, ten times each, and its results go on a public
ladder. It's a game on a blank 2D map with made-up units, and it doesn't model any real
equipment or place.

## The game in one minute

- There's an **asset** at the centre of the map, point (0, 0), with **30 HP** and a radius of 25 u.
- The **attacker** has **60 credits**. It launches drones from a ring 490 u from the centre:
  - a **striker** costs 2 credits and does 10 damage if it reaches the asset;
  - a **decoy** costs 0.5 credits and does no damage at all.
  - Both fly at 4 u per tick and look the same on radar until they get close.
- The **defender** has:
  - **20 interceptors** (fly at 12 u/tick, explode next to their target and usually destroy
    everything within 10 u);
  - a **gun** with 120 rounds that only reaches 100 u;
  - a **radar** that sees everything within 450 u but can only tell a striker from a decoy
    inside **150 u**.
- A match lasts up to **600 ticks**. It ends early if the asset is destroyed or the attacker
  has nothing left to send.
- The defender is also scored on **cost**: an interceptor costs 4 credits, a gun round 0.1.
  Shooting down a 0.5-credit decoy with a 4-credit interceptor is a bad trade.

## Your file

One `.py` file with exactly these at the top level:

```python
"""Idea: one sentence saying what your bot does differently. This line shows up on the
site, so make it good."""

NAME = "slow_pincer"        # 2-40 characters: lowercase letters, digits, _
ROLE = "attacker"           # or "defender"


def reset(seed):            # optional: called once before each match
    pass


def act(obs):               # called every tick; must return an action dict
    return {"launch": [], "steer": {}}
```

`act` gets one argument, `obs` (what your bot can see this tick), and returns a dictionary
saying what to do. That's the whole interface.

### If you're the attacker

`obs` contains:

| key | what it is |
|---|---|
| `tick` | the current tick, 1 to 600 |
| `budget` | credits you have left |
| `asset` | `{"pos": [0, 0], "hp": 30, "radius": 25}` |
| `drones` | your drones: `{"id", "type", "pos", "vel", "waypoint"}` each |
| `interceptors` | positions `[x, y]` of the defender's interceptors in the air |
| `rules` | every number in the game, e.g. `obs["rules"]["striker_cost"]` |

Return:

```python
{"launch": [{"type": "striker", "bearing": 90.0}],   # up to 4 launches per tick
 "steer": {12: [100.0, -40.0]}}                      # optional: drone 12 flies there first
```

`bearing` is in degrees: 0 is to the right (+x), 90 is up (+y). A drone flies to its
waypoint if it has one, then straight at the asset. Set a waypoint to `None` to clear it.

### If you're the defender

`obs` contains:

| key | what it is |
|---|---|
| `tick` | the current tick |
| `asset` | as above, with the current `hp` |
| `tracks` | radar contacts: `{"id", "pos", "vel", "range", "cls"}` each. Positions are a bit noisy. `cls` is `"unknown"` until the drone is inside 150 u, then `"striker"` or `"decoy"`. |
| `interceptors` | yours in the air: `{"id", "target", "pos", "age"}` |
| `stock` | interceptors left to launch |
| `ammo` | gun rounds left |
| `rules` | every number in the game |

Return:

```python
{"intercept": [7, 9],        # launch at tracks 7 and 9 (up to 2 launches per tick)
 "retarget": {3: 11},        # interceptor 3 now chases track 11
 "gun": 7}                   # fire one round at track 7, or None
```

### Rules for `act`

- **Be quick.** Every call must return within **2 seconds**; aim for milliseconds. A bot that
  stops answering gets restarted, and a bot that keeps stopping is treated as dead for the
  rest of the match.
- **Don't crash.** If `act` raises an error, that tick counts as "do nothing" and the error
  is counted against you. Wrap risky code in `try`/`except` and return a plain action.
- **Asking for too much is wasted.** Launching 6 drones when the cap is 4 launches 4; the
  extra 2 are ignored and counted as invalid requests.
- **Be deterministic.** The same observations should give the same actions. If you want
  randomness, make your own `random.Random(seed)` in `reset(seed)` and use that.
- Your module is loaded fresh for every match, so global variables don't carry over
  between matches (they do carry over between ticks, which is fine).

## What you can and can't use

**Allowed imports** (and nothing else): `math`, `random`, `itertools`, `functools`,
`collections`, `heapq`, `bisect`, `statistics`, `dataclasses`, `typing`, `enum`, `operator`.

**Not allowed**, and the checker will tell you which line it found:

- any other import: no `os`, `sys`, `subprocess`, `socket`, `time`, `json`, …
- the built-ins `open`, `exec`, `eval`, `compile`, `__import__`, `globals`, `locals`, `vars`,
  `getattr`, `setattr`, `delattr`, `input`, `breakpoint`, `help`, `exit`, `quit`, `memoryview`
- anything with double underscores on both sides, like `x.__class__` or `__builtins__`, and
  strings like `"__class__"`
- private attributes of other things, like `random._inst` (your own `self._x` is fine)
- code running at the top level of the file: the top level may only have imports, constants,
  functions and classes; put everything else inside functions
- `async` code

Why so strict? Your bot runs on our machine next to everyone else's. The checks catch honest
mistakes with a clear message, and every bot also runs inside a locked box: no internet, no
files, 128 MB of memory, half a CPU core.

## Limits

| | |
|---|---|
| file size | 64 KB |
| time per `act` call | 2 seconds (hard limit) |
| memory | 128 MB |
| CPU | half a core |
| network, files, other programs | none |

## Submitting

```
python -m colosseum.submit my_bot.py --side attacker --author yourhandle
```

Your handle is 2–24 characters: lowercase letters, digits, `_` and `-`.

What happens:

1. **Checks.** Your file is read (not run) and checked against the rules above. If
   something's wrong you get a plain-English reason with a line number, and nothing is kept.
2. **Test match.** Your bot plays one match against a built-in bot, inside the locked box. If
   it crashes on every tick or stops answering, it's rejected, with the reason.
3. **Accepted.** It's saved as `yourhandle__yourbotname` with a record of who sent it, when,
   and a fingerprint of the file (its SHA-256). Sending the exact same file again does
   nothing. Sending a changed file under the same bot name replaces the old version.

## After that

- **Every night** your bot plays every bot on the other side, 10 matches each (seeds 0–9),
  and moves up or down the Elo ladder.
- **Retirement.** A bot that finishes bottom of its ladder three nights running is retired,
  *unless* it's the only bot that can get through (or hold out against) some particular
  opponent. A bot that's the only answer to something stays, even if it's bad at everything
  else.
- **Everything is public and reproducible.** Every match is saved as a replay anyone can
  watch, and the same two bots with the same seed always play exactly the same match. Anyone
  can check any result, and so can you. Your code, your name and your bot's docstring will be
  visible to everyone.

## A complete first bot

An attacker that sends a striker every 6 ticks, rotating around the ring:

```python
"""Idea: a slow, even trickle from all directions, so the defender never gets a crowd to
hit with one interceptor."""

NAME = "even_trickle"
ROLE = "attacker"


def act(obs):
    cost = obs["rules"]["striker_cost"]
    if obs["tick"] % 6 != 0 or obs["budget"] < cost:
        return {"launch": [], "steer": {}}
    bearing = (obs["tick"] * 37) % 360
    return {"launch": [{"type": "striker", "bearing": bearing}], "steer": {}}
```

Good luck. Watch the replays of the bots that beat you; that's where the ideas are.
