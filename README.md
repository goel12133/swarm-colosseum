# Swarm Colosseum

An open arena where AI swarm-attack policies fight AI air-defence policies in a simulator.
Matches are deterministic, every match produces a shareable replay, and defenders are scored
on **cost exchange** as well as survival, because the interesting problem is cheap attackers
against expensive interceptors.

**This is an abstract strategy game and research benchmark.** Everything is in made-up units
(`u`, `ticks`, `credits`) on a blank 2D plane. It does not model, name or represent any real
system, unit or equipment, nothing in it is drawn from non-public information, and we make
no claim that a tactic that works here says anything about the real world.
[ABOUT.md](ABOUT.md) explains the game in plain language.

## What's here

- **A nightly league.** Every night a language model writes new bots in one of four personas
  (counter-meta, exploiter, generalist, contrarian). Every attacker then plays every
  defender on seeds 0–9, in a sandbox, and two Elo ladders are rebuilt from the full result
  set.
- **The tactic library.** One card for each bot that reached a top five or is the only
  answer to some opponent: the idea, what it beats, what beats it, and its best and worst
  replay. `python -m colosseum.library` writes it.
- **Research write-ups** in [`research/`](research/): two counters the league found without
  being told how, the balance findings, a persona ablation, and an optimiser ablation. Each
  states its limits.
- **A workshop kit** for first-time Python students in [`workshop/`](workshop/). It runs
  offline, with no Docker.
- **A static site bundle**, `python -m colosseum.site`, with ladders, bot pages, replays,
  the library and the research. It is built nightly and not served yet.

## Run it

```bash
python -m pytest tests -q                       # the full suite, about a minute
python -m colosseum.tournament --seeds 10       # baselines only, in-process
python -m colosseum.tournament --sandbox        # every bot, each match in a fresh container
open viewer/index.html                          # replay viewer, no build step
```

House and submitted bots run only with `--sandbox` (Docker, no network, memory and CPU
caps, a per-tick timeout). Without it the tournament skips them and says so. Outputs go to
`out/` (gitignored): `leaderboard.json`, `matrix.json`, `breaches.json`, `BALANCE.md`, and
one replay per match under `replays/`.

## Watch it

```bash
python -m colosseum.clip --showcase             # five captioned clips, mp4 + gif
python -m colosseum.clip out/replays/<match>.json --gif
```

The showcase goes to `out/clips/showcase/`, with a README that tells season one's story:
a defender that ignores decoys, the synchronised ring that beat it, the defender that
answered the ring, and the attacker that answered that one. The clips are drawn by the
replay viewer itself in headless Chromium, inside a container.

## Reproduce the leaderboard

```bash
git clone <this repo> && cd swarm-colosseum
make reproduce        # needs Docker; ~6 min on 4 cores
```

This replays every match of the current roster (every bot in `bots/`, seeds 0–9) in the
sandbox from scratch, with no cache. It then compares the rebuilt `leaderboard.json`,
`matrix.json` and `breaches.json` byte for byte with the committed `results/`. Checked on a
fresh clone on 2026-10-04: `REPRODUCED in 364 s`.

## The game, in one screen

A protected asset sits at the origin with 30 HP. The attacker has 60 credits and launches
from a ring at 490 u. The defender has 20 interceptors, a short-range gun, and a radar that
sees position but only reveals what a drone *is* inside 150 u.

| | attacker | defender |
|---|---|---|
| resources | 60 credits | 20 interceptors (4 each), 120 gun rounds (0.1 each) |
| units | striker 2 credits, 10 damage · decoy 0.5 credits, no damage | interceptor speed 12, proximity fuse, blast radius 10, pk 0.85 |
| limits | 4 launches per tick | 2 interceptor launches per tick, 1 shot per tick |

Strikers and decoys move at the same speed on purpose, so speed never gives away which is
which. Every drone inside a blast is rolled separately, so clumped swarms get punished.

Scoring rewards holding the asset *and* spending less than you destroy:

```
score_defender = 0.6 × (asset_hp / 30) + 0.4 × value_destroyed / (value_destroyed + defender_spent)
cost_exchange_ratio = value_destroyed / defender_spent
```

All tunable numbers live in `colosseum/rules.py` and nowhere else. The rules are frozen for
a season; dates are in [SEASON.md](SEASON.md).

## Writing a bot

One file with `NAME`, `ROLE`, `act(obs) -> dict`, and optionally `reset(seed)`:

```python
"""Idea: shoot the nearest two tracks."""
NAME = "my_bot"
ROLE = "defender"

def act(obs):
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    return {"intercept": [t["id"] for t in tracks[:2]], "retarget": {}, "gun": None}
```

A bot is loaded as a **fresh module instance per match**, so globals can't leak between
matches. If it raises or returns something malformed, that call becomes a no-op and is
counted in the match result: a bot can lose, but it can't crash a match.
[SUBMITTING.md](SUBMITTING.md) has the full interface, the allowed imports, the limits and
a complete first bot. **Outside submissions are not open yet.**

## Layout

```
colosseum/   engine (rules, sim, policy), tournament, sandbox, cache, house league,
             meta report, library, site, clip, submit, health
bots/        attackers/ and defenders/ (baselines), house/ (written by the league)
results/     the committed results that `make reproduce` checks against
research/    write-ups
workshop/    the student kit
viewer/      single-file replay viewer
docker/      the clip renderer image
tests/       the test suite and fixture bots
```

## Contributing, citing, licence

- [CONTRIBUTING.md](CONTRIBUTING.md): what we accept and the rules every change follows.
- [CITATION.cff](CITATION.cff): how to cite the benchmark.
- **Licence: not chosen yet.** See [LICENSE_NOTE.md](LICENSE_NOTE.md). Until there is a
  `LICENSE` file, no licence is granted.

---

Swarm Colosseum is built by Pelennor.
