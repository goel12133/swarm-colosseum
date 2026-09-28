# Progress

## Plan (written before building)

Build order, following the brief: rules + engine with tests, then bots, then tournament,
then viewer, then the balance pass.

1. **`colosseum/rules.py`** — Season 0 constants in one place, as a dataclass so a test can
   build a modified ruleset (e.g. pk forced to 1.0) without touching globals.
2. **`colosseum/policy.py`** — load a bot from a file path as a *fresh module instance per
   match*, and wrap `act()` so any exception or malformed action becomes a no-op and a
   counter, never a crash.
3. **`colosseum/sim.py`** — the tick loop with a fixed, documented order of operations. One
   seeded RNG per match; every random draw made in sorted-id order so the same
   (attacker, defender, seed) is byte-identical.
4. **Tests** alongside, not after: determinism, resource limits, ID masking, blast kills,
   impact damage, a bot that always raises, the scoring formula against a hand calculation.
5. **Bots**: 5 attackers, 4 defenders, each with a docstring naming the idea it tests.
6. **`tournament.py` + `elo.py`** — round robin over seeds, two ladders, deterministic
   match order, writes `out/leaderboard.json`, `out/matrix.json`, `out/replays/`,
   `out/BALANCE.md`.
7. **`viewer/index.html`** — single file, canvas, file picker + drag-and-drop + one embedded
   sample replay, light/dark, phone width.
8. **Balance pass** — run, check the >90% bot / >85% role thresholds, tune only `rules.py`,
   at most 3 iterations, each change and its reason recorded here and in BALANCE.md.

### Decisions I am making up front (flagging, not deviating silently)

- **Track id = drone id.** The brief has the defender intercepting `track_id` and the
  attacker owning `drone.id`; one stable identifier keeps replays readable. A track only
  exists while the drone is inside radar range.
- **Guidance and fuse.** Lead pursuit uses the *noisy* estimate, as specified. The
  proximity fuse detonates on the assigned target only; an interceptor that coasts past an
  unrelated drone does not spontaneously detonate. Otherwise "if its target dies it keeps
  coasting" has no stable meaning.
- **`random.normalvariate`, not `random.gauss`.** `gauss` caches a spare value between
  calls, which makes the draw sequence depend on call history. `normalvariate` does not.
- Every random draw is made iterating ids in sorted order, so determinism does not depend
  on dict insertion order.

---

## Session 1 — Stage 1 complete

### What I built

Engine, nine bots, tournament with two Elo ladders, replay viewer, balance pass. Order was
rules → engine → tests → bots → tournament → viewer → balance, as planned.

### Commands run, and what they showed

```
$ python -m pytest tests/ -q
25 passed in 2.94s

$ python -m colosseum.tournament --seeds 10 --quiet
200 matches -> /root/swarm-colosseum/out
top attacker: trickle (1106)
top defender: layered (1061)

$ python viewer/build_viewer.py
embedded trickle__nearest_first__s8.json (163 frames, 188 events) -> viewer/index.html (71,543 bytes)
```

The viewer was rendered headless and checked by eye at `#t=96`: strikers point at the asset,
decoys are visually distinct, gun tracers draw from the asset, the HP ring is partial, and the
sidebar shows CER and outcome. Sidebar values on the embedded sample: breached, CER 0.57,
value destroyed 52.5 against 92.0 spent.

### Balance pass

**Iteration 1 (the only one needed): `gun_ammo` 400 → 120.**

The first full run flagged `identify_then_engage` winning **100%** of its matches. I checked
the obvious cause first and it was wrong: sweeping `id_range` from 150 down to 60 barely moved
it (100% → 100%), so "identification is too generous" was not the explanation.

The actual cause is the gun. One shot per tick over a 100 u approach at speed 4 is roughly 19
shots per drone, and 400 rounds in a 600-tick match is effectively an unlimited magazine — so
the gun was a free backstop, which made waiting for identification risk-free. A sweep over
`gun_range`, `gun_ammo` and `attacker_budget` at 4 seeds, then the shortlist re-run at 10:

| variant | defender role win | ITE win | max any-bot win | verdict |
|---|---|---|---|---|
| ammo 400 (baseline) | 68% | 100% | 100% | flagged |
| ammo 200 | 67% | 100% | 100% | flagged |
| ammo 150 | 64% | 92% | 92% | flagged |
| **ammo 120** | **58%** | **82%** | **82%** | **clean** |

Post-change: 200 matches, defenders hold 58%, attackers breach 42%, no bot above 82%, no
threshold flagged. One iteration used of the three allowed.

### Deviations from the brief, and why

- **Python 3.12.3**, not 3.11 — it is what is on the box. Standard library only in the engine,
  as specified.
- **`flanker`'s dogleg radius 300 → 470.** Its docstring claims it arrives from an unexpected
  side; turning at 300 u is inside the 450 u radar, so the defender simply watched the turn and
  the bot was only flying a longer exposed path. Moving the turn outside radar range made the
  implementation match its stated idea. **It changed nothing** — flanker still wins 0%, and
  against a passive defender it destroys the asset, so it is not broken. Spreading out to dodge
  a 10 u blast costs more saturation than it saves. Recorded in ROADMAP.md as an open question
  rather than tuned away.
- **Viewer `#t=NN` deep link**, not in the brief. One line, and it makes a specific moment in a
  replay linkable, which the brief's "replay you can share" wants.
- **`viewer/template.html` + `build_viewer.py`.** `index.html` is still a single dependency-free
  file that works on open; the generator only substitutes the embedded sample so it cannot go
  stale against the replay format.

### What is not done

Stage 2, deliberately. No ports opened, nothing deployed, no outside code executed.
