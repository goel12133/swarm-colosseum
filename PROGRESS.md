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

---

## Session 2 — flanker rewrite, and the Stage 2 sandbox

### 1. Flanker: 0% → 68% win rate, last → second in the ladder

Rewritten around a rate limit rather than geometry: the defender can answer 2 interceptors
and 1 gun shot per tick, and the attacker's own 4-per-tick launch cap puts a ceiling of 4
arrivals per tick on any single-axis attack. Two axes with different path lengths break that
ceiling — a dogleg wave and a direct wave launched later by exactly the difference in flight
time, both landing in the same few ticks.

Two things had to be measured rather than assumed:

- **The dogleg has to be an arc, not a chord.** A straight line from 0° to 120° at radius 480
  passes within ~240 u of the asset, deep inside the 450 u radar. The wave was tracked and
  destroyed for 200 ticks before arriving: **0 impacts against every active defender**. The bot
  now walks 9° around the circle per tick, staying outside radar for the whole transit.
- **Zero spreading is a free multi-kill, not concentration.** Four drones launched on the same
  tick from the same bearing sit at *identical* coordinates. Kill events showed single blasts
  taking 6, 8 and 11 drones. A 2.5° de-stack puts same-tick launches ~20 u apart, outside one
  blast radius, without moving them out of the arrival window.

The de-stack is a deliberate, documented departure from "drop the spreading": the fan that was
dropped was 11° per drone across 7 dogleg bearings, which desynchronised arrivals. This does
not — it is the minimum separation that stops four drones occupying one point.

```
$ python -m pytest tests/ -q
25 passed in 2.75s

$ python -m colosseum.tournament --seeds 10 --quiet
200 matches; top attacker: trickle (1082); top defender: identify_then_engage (1054)
```

Per-defender breaches, seeds 0-9: nearest_first 10/10, layered 7/10, gun_only 10/10,
identify_then_engage 0/10 — **27/40 against active defenders**.

**Pass conditions, all met:** at least one win against a non-passive defender ✓ (27); no bot
above 90% — highest is identify_then_engage at 82% ✓; neither role above 85% — 44% defended
against 56% breached ✓. `rules.py` untouched, as instructed.

Ladder after the rewrite: trickle 1082, **flanker 1067**, multi_axis 1060, decoy_screen 1023,
rush 908. Defenders: identify_then_engage 1054, layered 1032, nearest_first 894, gun_only 878.
The role split moved from 58/42 to 44/56, still inside the thresholds.

### 2. Docker sandbox (Stage 2, step one only)

`colosseum/sandbox.py` (host) and `colosseum/sandbox_runner.py` (inside the container).
`SandboxedPolicy` has the same surface as `PolicyRunner`, so `run_match(..., sandbox=True)` is
the only thing that changes — a bot that behaves differently between modes is a sandbox bug,
which is what the determinism test exists to catch.

Container: `--network=none`, `--cpus=0.5`, `--memory=128m` with `--memory-swap=128m` so the
limit actually kills rather than swaps, `--pids-limit=64`, `--read-only` plus an 8 MB tmpfs,
`--cap-drop=ALL`, `--security-opt=no-new-privileges`, non-root user, `PYTHONHASHSEED=0`.
Host enforces a wall-clock deadline on every call.

A timeout or crash is a counted no-op, exactly as in-process. A container that stops answering
is restarted up to `max_restarts`; after that the policy is dead and every remaining call is an
instant counted no-op, so a busy loop costs bounded time rather than 600 timeouts. One
container per match, not per tick — a start is ~0.3 s, which would be 600 × that per match.

```
$ python -m pytest tests/test_sandbox.py -q
8 passed in 10.29s

$ python -m pytest tests/ -q
33 passed in 13.11s

$ /usr/bin/time python -m colosseum.tournament --seeds 10 --quiet --no-replays
3.08 s
$ /usr/bin/time python -m colosseum.tournament --seeds 10 --quiet --no-replays --sandbox
152.55 s
```

**Sandboxed is ~50× slower: 152.55 s against 3.08 s** for 200 matches (400 container starts).
The leaderboard and matrix from the two runs are **byte-identical**, so determinism survives
the container boundary at tournament scale, not just in the three single-match tests.

### Still not done, deliberately

House league, meta report, video export, public site. No ports opened, nothing deployed, no
firewall or SSH changes, no outside submissions accepted.

---

## Session 3 — parallel tournament, and the nightly house league

### 1. Parallelism instead of container reuse

One fresh container per match stays the rule. Matches now run across `cores - 1` workers
(3 on this 4-core box). The job list is built in sorted order and **results are consumed in
that order regardless of completion order** — Elo is path dependent, so consuming by
completion would make the ladder depend on machine timing. Each worker writes its own
replay so only the match meta crosses the process boundary.

```
$ /usr/bin/time python -m colosseum.tournament --seeds 10 --quiet --no-replays --sandbox
152.55 s          # sequential, session 2
57.86 s           # workers=3
```

**57.86 s, down from 152.55 s.** Byte-identical leaderboard *and* matrix across three runs:
parallel sandboxed, sequential sandboxed, and in-process. A nightly run is far under the
20-minute mark that would justify revisiting reuse.

This also fixed house-bot discovery: `ROLE` is now read out of the file with a regex rather
than a substring check on the first 400 characters, and house **defenders** are picked up,
which the old code silently dropped. The host still never imports a house bot.

### 2. The nightly house league

`python -m colosseum.house_league --once [--dry-run]`.

One night: read the leaderboard, matrix, balance read and the three most lopsided pairings
with one replay each → check caps → ask Claude for one attacker and one defender that
exploit a weakness named in the docstring → validate → write date-stamped into `bots/house/`
→ smoke-test **in the sandbox** → rerun the full tournament → apply the retirement rule.

**Spend controls.** Dollar, token and call caps all come from env vars and are checked
*before* the call, never after. The input-token estimate is deliberately rounded up, so the
error is on the side of not spending. A night that would exceed a cap logs an `ABORT` line
and spends nothing. Every call's token counts go to `out/house_league.log`. Prices come from
a table in the module — `claude-opus-5` at $5/$25 per MTok — and if Anthropic's prices move,
that table is what has to change, because the dollar cap is enforced against it.

**House bots are untrusted from the moment they are written.** The host validates with `ast`
and never imports them; a test asserts that a bot whose module body writes a file leaves no
file behind. The only place they execute is a container.

```
$ python -m pytest tests/test_house_league.py -q
16 passed in 0.05s

$ python -m pytest tests/ -q
49 passed in 11.96s

$ time python -m colosseum.house_league --once --dry-run
"written": ["2026-09-28_attacker_dryrun_attacker.py", "2026-09-28_defender_dryrun_defender.py"]
"rejected": [], "retired": [], "spend": {"calls": 0, "usd": 0.0}, "seconds": 89.1
real 1m29.206s
```

The dry run wrote both canned bots, smoke-tested each in the sandbox, reran the full
tournament at 300 matches, and placed them in the ladders (attacker elo 956.9 / 46% win,
defender elo 904.9 / 32% win). The canned bots were then deleted — they exist to exercise
the path, not to compete.

**Unattended failure path, verified:**

```
$ .venv/bin/python -m colosseum.house_league --once      # no API key set
"status": "error"
"reason": "TypeError: Could not resolve authentication method..."
"spend": {"calls": 0, "usd": 0.0}
exit code: 2
```

A log line and exit 2, not a traceback.

**Cron:** `30 3 * * * /root/swarm-colosseum/scripts/nightly.sh`, installed. The wrapper
sources `.house_league.env` (gitignored; `.house_league.env.example` is committed) so the
key and caps never enter the crontab, and prefers `.venv/bin/python` because the engine is
standard-library only while the house league needs the SDK and this box's python is
Debian-managed.

### Blocked: the real night

**No Anthropic credentials exist on this machine** — `ANTHROPIC_API_KEY` is unset, the `ant`
CLI is not installed, and there is no `~/.config/anthropic` profile. Everything except the
API call is tested and working; one real night and its recorded spend is waiting on a key.

### Still not done, deliberately

Meta report, video export, public site. No ports opened, nothing deployed, no firewall or
SSH changes, `rules.py` frozen.

## Session 4 — house league on the Claude Code CLI, and the first real night

### Backend

Default generator is now the Claude Code CLI on this box, headless, on the subscription
login in `~/.claude` — no API key. The API backend stays behind `--backend api` /
`HOUSE_LEAGUE_BACKEND=api`. On the cli backend only the token cap and call cap apply.

The child call: `claude -p --output-format json --model opus --tools "" --setting-sources ""
--strict-mcp-config --disable-slash-commands --no-session-persistence --system-prompt ...`,
prompt on stdin, run in an empty temp dir. `--bare` was the obvious choice but it refuses
OAuth, i.e. the subscription. No setting sources means no plugins and none of their hooks;
the temp dir means no CLAUDE.md. The child env is built from scratch (HOME, PATH, LANG,
`CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000`): `ANTHROPIC_API_KEY` is dropped so a stray key can't
turn a free night into a billed one. Validation is unchanged: `ast` only, never imported on
the host, smoke test and tournament in the sandbox.

Failure path, verified from `env -i HOME=<empty dir> PATH=/usr/bin:/bin bash scripts/nightly.sh`:
`ABORT: BackendError: claude CLI failed (exit 1): Not logged in · Please run /login`, exit 2,
nothing written, no tournament. Missing binary, timeout (900s) and non-JSON output take the
same path; each has a test.

Cron: `nightly.sh` now puts `~/.local/bin` on PATH (cron's is `/usr/bin:/bin`). Both real
nights below were run as `env -i HOME=/root PATH=/usr/bin:/bin bash scripts/nightly.sh`,
i.e. with cron's environment, not this session's.

### The first real nights

**Attempt 1 (04:45 UTC)** — call succeeded (5,927 in / 6,411 out, 77s, model resolved to
`claude-opus-5-5`), but both bots rejected: "model returned too few code blocks". The raw
response was not saved, so **the cause is unknown** — could have been a fence the regex
didn't accept, could have been prose. Fixed the gap, not the guess: every response now goes
verbatim to `out/house_raw/`, and the fence regex accepts ```py / ```Python / CRLF.

**Attempt 2 (04:48 UTC)** — the night of record.

| | |
|---|---|
| tokens | 2,929 in + 5,742 out = **8,671**, 1 call (cap 200,000 / 4) |
| model call | 56.5s |
| tournament | **300 sandboxed matches in 90.9s** (≈0.30 s/match, same rate as session 3) |
| whole night | 150.2s |

`2026-09-28_attacker_staggered_screen_trickle` — targets identify_then_engage, which waits
to classify inside id range and then burns gun ammo on decoys. Groups of 2 decoys then 1
striker on the same bearing, a group every 18 ticks, golden-angle bearing rotation, strikers
jink sideways when an interceptor closes. **#1 attacker: elo 1109, 76% win rate.**

`2026-09-28_defender_discriminating_ledger` — targets defenders that waste resources on
decoys (nearest_first, identify_then_engage). Never engages decoys; one interceptor per
confirmed striker, reassigned when its target dies; gun only at strikers. **#1 defender:
elo 1195, 100% win rate** (mean score_defender 0.66–0.77 against every attacker). A clean
sweep is worth a closer look before it's taken at face value; it is at least consistent with
the docstring, since every baseline attacker leans on decoys.

### Fixes found on the way

- `log()` bound the log path at import, so tests wrote into the real `out/house_league.log`
  (the stray "retired 2026-09-01_attacker_loser" line there came from a test).
- Retirement recorded the lowest-ranked *house* bot, not the bottom of the ladder: a lone
  house bot at #1 would have counted as a bottom finish. Tonight's history entry was
  rewritten with the fixed rule (neither house bot is bottom).
- Dry runs no longer count toward retirement.
- The CLI adds its own input overhead, so the "deliberately high" estimate (≈2,300) was
  under the real 2,929. Added a 4,000-token CLI overhead; a test pins it above 5,927.

```
$ python3 -m pytest tests -q
68 passed
```
