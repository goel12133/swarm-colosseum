# Swarm Colosseum

An open arena where AI swarm-attack policies fight AI air-defence policies in a simulator.
Matches are deterministic, every match produces a shareable replay, and defenders are scored
on **cost exchange** as well as survival — because the interesting problem is cheap attackers
against expensive interceptors.

**This is an abstract strategy game and research benchmark.** Everything is made-up units
(`u`, `ticks`, `credits`) on a blank 2D plane. It does not model, name or represent any real
system, unit or equipment, and nothing in it is drawn from non-public information.

## Run it

```bash
python -m colosseum.tournament --seeds 10     # full round robin, ~6 s
python -m pytest tests/ -q                    # 25 tests
open viewer/index.html                        # replay viewer, no build step
```

Outputs land in `out/` (gitignored): `leaderboard.json`, `matrix.json`, `BALANCE.md`, and one
replay per match under `replays/`.

## Reproduce the leaderboard

```bash
git clone <this repo> && cd swarm-colosseum
make reproduce        # needs Docker; ~6 min on 4 cores
```

It replays every match of the current roster (every bot in `bots/`, seeds 0–9) in the
sandbox from scratch, with no cache, and compares the rebuilt `leaderboard.json`,
`matrix.json` and `breaches.json` byte for byte with the committed `results/`. Checked on a
fresh clone on 2026-10-04: `REPRODUCED in 364 s`.

## The game, in one screen

A protected asset sits at the origin with 30 HP. The attacker has 60 credits and launches
from a ring at 490 u; the defender has 20 interceptors, a short-range gun, and a radar that
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

All tunable numbers live in `colosseum/rules.py` and nowhere else.

## Writing a bot

One file with `NAME`, `ROLE`, `act(obs) -> dict`, and optionally `reset(seed)`:

```python
NAME = "my_bot"
ROLE = "defender"

def act(obs):
    tracks = sorted(obs["tracks"], key=lambda t: t["range"])
    return {"intercept": [t["id"] for t in tracks[:2]], "retarget": {}, "gun": None}
```

Drop it in `bots/attackers/` or `bots/defenders/` and it joins the next tournament. A bot is
loaded as a **fresh module instance per match**, so globals cannot leak between matches. If it
raises or returns something malformed, that call becomes a no-op and is counted in the match
result — a bot can lose, but it cannot crash a match.

**Stage 1 runs our own bots in-process only.** Outside submissions are not accepted until the
Stage 2 sandbox exists; see `ROADMAP.md`.

## Layout

```
colosseum/   rules.py  sim.py  policy.py  tournament.py  elo.py
bots/        attackers/ (5)  defenders/ (4)  house/ (Stage 2)
viewer/      index.html (single file)  template.html  build_viewer.py
tests/       25 tests + fixture bots
out/         gitignored results
```

---

Swarm Colosseum is built by Pelennor. Season dates: [SEASON.md](SEASON.md).
