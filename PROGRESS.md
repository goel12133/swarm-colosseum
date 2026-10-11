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

## Session 5 — auditing discriminating_ledger's sweep, and personas

### 1. Leak or tactic: no leak

`tests/test_leakage.py`, permanent. Two tests, idle defender so no kill roll touches the RNG:

- **Counterfactual, exact.** A random mixed launch plan, then the same plan with every
  striker ↔ decoy swapped. Outside id range the defender's entire view (every track field,
  track order, ids) is bit-identical, four seeds. This catches fields nobody has thought of.
- **Statistical.** 40 random plans, 480 drones per type, one sample per drone (its mean over
  out-of-range ticks), two-sample KS at alpha 0.001, critical 0.126. Largest statistic:
  heading error 0.083; speed 0.058, id rank 0.042, id parity 0.012, list position 0.042.
  Track dicts carry exactly `id, pos, vel, range, cls` — no hp, no radius.

A first version counted every tick as a sample and flagged `id_rank` (KS 0.085 vs 0.038).
That was the test, not the engine: a drone's ~75 consecutive ticks are not independent, so
the sample size was inflated ~75× and KS found chance structure in six shuffles.

The bot decides on `cls` alone (plus "unknown inside 135 u", which effectively never
happens). sim.py unchanged; nothing to fix, no rerun needed.

### 2. Characterising the win

`python3 scripts/audit_defender.py <defender>` — engine on the host, both bots sandboxed,
per-tick launch/cap/backlog instrumentation. For discriminating_ledger (10 seeds each):

| attacker | mean score | CER | defended | cap ticks (binding) | stock out |
|---|---|---|---|---|---|
| multi_axis | 0.661 | 0.67 | 10/10 | 88 (32) | 10/10 |
| staggered_screen_trickle | 0.731 | 0.49 | 10/10 | 0 (0) | 10/10 |
| trickle | 0.745 | 0.57 | 10/10 | 10 (0) | 10/10 |
| decoy_screen | 0.766 | 0.71 | 10/10 | 98 (90) | 10/10 |
| flanker | 0.771 | 0.75 | 10/10 | 39 (30) | 10/10 |
| rush | 0.771 | 0.75 | 10/10 | 100 (90) | 10/10 |

"100% win rate" means never breached. By score it lost 2 of 60 (multi_axis seeds 2 and 6,
0.354), and its CER is below 1 in every pairing. Its real edge over identify_then_engage is
not collapsing against trickle-style attackers (0.745 vs 0.16); against multi_axis it is
worse (0.661 vs 0.77).

**Flanker:** neither hypothesis. The cap bound only 2–3 ticks per match (≈ tick 336), and
stock does *not* cover every striker — 30 strikers against 20 interceptors, stock gone every
match. It is the blast radius: 297 of 300 strikers died to 200 interceptors because timed
two-axis arrival bunches strikers inside 10 u (90 of 158 blasts killed ≥ 2; one killed 10).

**Two most vulnerable replays** (multi_axis s2 and s6, asset 10/30, near-identical):
stock hit zero at tick 124 with 2–3 identified strikers still uncovered; two got past the gun
at ticks 165–166. *What breaks it:* one more striker held back until after tick 124 — a
third impact is a breach. Same in s6.

**Rules finding** recorded in the new committed `BALANCE.md` (S0-1): decoys are worthless
against a defender that ignores them, because identification at 150 u leaves ~31 ticks and an
interceptor needs ~9. Not fixed; season-two options listed there. `out/BALANCE.md` now ends
with a copy of it, so the house league's context includes it too.

### 3. Personas

`colosseum/personas.py`. Each persona is its evidence plus the bot it must beat:

| persona | evidence | must beat |
|---|---|---|
| exploiter | standings, matrix, most lopsided pairings | opponent with the single worst result |
| counter_meta | opposing #1's full source, its matrix row, best pairings, closest calls | opposing #1 |
| generalist | full matrix, every opponent's docstring | the field (mean score) |
| contrarian | every same-role bot's docstring, as approaches to avoid | opposing #1, with a new idea |

Selection: `HOUSE_LEAGUE_PERSONAS` override → counter_meta if the opposing #1 wins ≥ 90% →
else rotate exploiter/generalist/contrarian by night (defender offset by one). One call per
bot now (was one call for both); two bots per night is still the cap. Every bot gets a
`.meta.json` sidecar (persona, target, backend, model, tokens, raw response) and, after the
tournament, a `result` with its score vs the target and `beat_target`. Retirement moves the
sidecar with the bot. Last night's two bots got backfilled sidecars (persona exploiter).

**Tonight (03:30):** attacker = counter_meta vs discriminating_ledger, shown its source and
its closest calls (the multi_axis stock-exhaustion matches). Defender = contrarian vs
staggered_screen_trickle (76% < 90%, so rotation). Projected worst case ≈ 78k tokens over
2 calls, under the 200k / 4-call caps.

```
$ python3 -m pytest tests -q
88 passed
```

## Session 6 plan (Stage 2, second half)

(The brief calls this "Session 5 plan"; Session 5 is already taken above, so it is Session 6.)

**Done first, before the plan: a hard-rule-2 violation, fixed.** `bots/house/__pycache__`
showed host Python had compiled both house bots (2026-09-28 04:51). `tests/test_tournament.py`
runs the tournament in-process, and discovery included `bots/house/`, so every test run since
the first real night executed house-bot module code on the host. Fixed in `00257fb`: an
in-process tournament now leaves untrusted bots out, and `load_policy` refuses anything under
`bots/house/` or `bots/submitted/`. Regression test: a trap bot whose module body writes a
marker file never executes. `python3 -m pytest tests -q` → 90 passed, and no `__pycache__`
reappears in `bots/house/` after a full run.

**Order**
1. Section 1 after tonight's 03:30 UTC night. Nothing on the nightly path changes before
   then, so the discovery test runs on exactly the prompt described in Session 5.
2. Right after section 1, on main: the two persona decisions (below), the prompt moved into
   `colosseum/prompts/`, `SEASON.md` and the README attribution. `--once --dry-run` on a
   scratch copy before committing.
3. Section 2 in a separate `git worktree` (`../swarm-colosseum-s2`), so cron keeps running
   main from `/root/swarm-colosseum` and never sees season-two code. The branch is never merged.
4. Sections 3 → 9 in order, and I stop cleanly after whichever section completes last.

**Where I read the brief differently, and why**
- *Counter-meta, no threshold.* Counter-meta already always targets the opposing #1; what
  changes is my 90% trigger for *choosing* it. That trigger goes. counter_meta joins the
  rotation as a fourth persona, and the brief's escalation rule takes over the dominance case.
- *Escalation, "both opposite-side slots".* A night has one attacker slot and one defender
  slot. I read it as: if a bot has been unbeaten by every opponent for two consecutive nights,
  both of that night's bots are written for the opposite side, as counter_meta against it
  (e.g. two attackers, no defender). It stays within the two-bot cap. "Unbeaten" means no
  opponent scores above 0.5 against it in the matrix, not just "never breached".
- *Section 1 isn't fully unaided.* The counter-meta prompt includes the target's closest calls,
  and those are the multi_axis matches where stock hits zero (`stock_left: 0`, impact ticks
  165–166). It is not told the diagnosis. The section 1 report says so.
- *Section 3, "commits a copy to reports/".* Cron would make git commits in the repo I work in.
  I'll make that commit touch only `reports/` and skip it if the tree has other staged
  changes, so it can never sweep in half-finished work.
- *Section 5.* No Chromium, ffmpeg or Pillow on the host. Rather than install system
  packages, the renderer runs in a Docker image (headless Chromium + ffmpeg) driving
  `viewer/index.html`, so the viewer stays the single source of truth for how a match looks.
  Pulling that image is the only new network use.
- *Hard rule 7.* In Session 4 I read `.house_league.env` (key redacted) and rewrote it. From
  now on I don't touch it or `.house_league.env.save`.

### Section 2 — season-two candidates ✅ (branch only, not merged)

Worktree `../swarm-colosseum-s2`. Branches: `season2-candidates` (measurement script +
`SEASON2_CANDIDATES.md`), `s2-a-imperfect-id`, `s2-b-score-reweight`, each cut from the base
and tested alone. (`season2-candidates/a` style names are impossible alongside a
`season2-candidates` branch in git, hence the `s2-` prefix.)

Every run: full house, `--seeds 10`, sandboxed, 300 matches, `scripts/s2_measure.py`. The
season-one rerun reproduces main exactly (Elo 1109 / 1195).

```
                         S1            A (dwell 8, err 8%)   B (hp × CER/(CER+0.5))
defender share of wins   50%           47%                   39%
flags                    ledger 100%   none                  staggered_trickle 98%
#1 defender win rate     100%          90%                   78%
Elo spread att / def     63 / 118      76 / 88               61 / 148
interaction share        0.315         0.303                 0.269
tests on branch          —             91 passed             92 passed
```

**Recommend A.** It hits S0-1's cause (identification that is instant and certain) without
breaking role balance or creating a new dominant bot. B addresses the CER symptom by moving
the imbalance to the attackers and producing a 98% bot. Honest limit on A: with today's field
decoys are still not worth buying (the gains don't track decoy use), so its strategic payoff
depends on bots learning to hedge against labels. Details, tables and the parameter sweep:
`git show season2-candidates:SEASON2_CANDIDATES.md`.

### Section 3 — weekly meta report 🚧 (built and tested; cron wiring after section 1)

`colosseum/meta_report.py`, `tests/test_meta_report.py`. Supporting pieces on the nightly path,
each dry-run on a scratch copy before commit (exit 0 each time, 420 sandboxed matches in
124–142 s):
- `out/nights.jsonl`: one line per real run (status, reason, tokens, written/rejected/retired,
  positions, seconds per phase). An unexpected crash inside a night is now a logged
  `status=error`, not a traceback.
- `out/breaches.json` from the tournament, and `out/history/<date>/` snapshots per real night.
- 2026-09-28 backfilled from `out/` and the log (ledger: 2 runs; snapshot + breaches from
  that night's 300 replays).

Week n = real nights 7(n−1)+1…7n (a failed night counts, a date with no run doesn't).
`--if-due` fires on the 7th night only and only once; `--commit` is a pathspec commit of
`reports/WEEK_n.md` under the author "Swarm Colosseum league", so it can't sweep in anything
else. `SEASON.md`: season one runs 2026-09-28 → 2026-10-25 and ends 2026-10-26 (it's
`season 0` in code). A preview on real data works; "best new idea" now prefers an `Idea:`
docstring line, which the prompt will ask for after tonight.

### Section 4 — coverage-aware retirement ✅

A bot at the bottom of its ladder three nights running is retired unless it is the only live
bot that covers some opponent. An attacker covers a defender if it destroys the asset in ≥ 1
seed; a defender covers an attacker if it holds the asset in ≥ 1 seed. It's the same bar both
ways, and "live" means every bot in the last tournament, baselines included. The exemption
is logged with the opponent's name. Retirement now also handles `bots/submitted/<side>/`
(each folder gets its own `RETIRED/`). On the current field no bot has unique coverage.

```
$ python3 -m pytest tests -q
104 passed
```

### Section 5 — replay clip export ✅

`python -m colosseum.clip <replay.json> [--from T] [--to T] [--speed 4] [--out clip.mp4]`.

**Single source of truth: the viewer.** The replay is embedded in `viewer/template.html` by
the same `page_with()` that builds `viewer/index.html`. Headless Chromium then runs the
viewer's own `draw()` for each frame (new `#clip=from,to,speed` hook) and ffmpeg encodes.
A Python port of the canvas code would have been simpler to run but would drift the first
time either was edited. Both tools run in a container (`docker/clip`, `colosseum-clip:1`,
1.45 GB, built on first use) with `--network none`, non-root, memory/CPU/pid limits. Nothing
is installed on the host.

```
$ python -m colosseum.clip full600.json            # 600-tick match, sandboxed scratch attacker
full600.mp4: 0.08 MB, 75 frames, ticks 0-600 at 4x
$ python -m colosseum.clip full600.json --speed 1
full600_1x.mp4: 0.17 MB, 300 frames, ticks 0-600 at 1x
$ ffprobe full600.mp4
h264 High, 720x776, yuv420p, 30 fps, 4.5 s  (faststart: plays inline on phones)
```

The weekly meta report renders the best new idea's strongest match (against its target if
that pairing exists) into `out/meta/WEEK_n_<bot>.mp4` and links it. A failed render becomes
a line in the report, never a failed report. `*.mp4` is gitignored.

**Found and fixed on the way: two injection paths from untrusted bot names.**
1. The viewer set `meta.attacker` and `meta.defender` (the bots' own `NAME` strings) with
   `innerHTML`, so a bot named `<img src=x onerror=…>` would run script in the viewer.
   They're now text nodes, and a test asserts the template has no `innerHTML`.
2. Replays were embedded in `<script>` with plain `json.dumps`, so a `NAME` containing
   `</script>` would end the script. `embed_json()` now escapes `<`, `>` and `&`, and a test
   asserts a hostile name produces exactly one `</script>` in the page.

```
$ python3 -m pytest tests -q
108 passed
```

### Section 6 — submission pipeline ✅ (prepared, not opened)

`python -m colosseum.submit <path.py> --side attacker|defender --author <handle>`. Nothing
listens on the network.

Order: size ≤ 64 KB and UTF-8 → `ast` checks on the host (nothing imported or run) → sha256
duplicate check (no-op) → one sandboxed match against a baseline (`layered` or `rush`), seed
0 → copy to `bots/submitted/<side>/<handle>__<NAME>.py` + `.meta.json` (author, UTC time,
sha256, bytes, replaced sha, validation). A rejection prints a plain-English reason with a
line number and writes it to `out/submissions/rejected/`. Rejected code is never kept.

- **Allowlist:** `math random itertools functools collections heapq bisect statistics
  dataclasses typing enum operator`.
- **Forbidden:** other imports, relative imports, `import *`, private names from allowed
  modules; `open exec eval compile __import__ globals locals vars getattr setattr delattr
  input breakpoint help exit quit memoryview`; any dunder name, attribute or dunder-looking
  string; frame/code-walking attributes (`gi_frame`, `f_globals`, …); private attributes
  except your own `self._x` / `cls._x` (modules expose `os` as `random._os`); async; any
  top-level statement other than imports, constants, functions and classes.
- **`NAME`** must match `^[a-z][a-z0-9_]{1,39}$`: safe in file names and in HTML, which
  closes the injection route found in section 5 at the source. Handles match
  `^[a-z0-9][a-z0-9_-]{1,23}$`.
- **Smoke rejects:** the bot can't start; the sandbox had to restart it (a busy loop hits the
  2 s per-tick timeout); or it errored on every tick.
- Submitted bots join the nightly tournament, ladders and retirement rule alongside house
  bots, and `load_policy` refuses them on the host.

`SUBMITTING.md` is the player guide, and a test checks its example bot passes and its
allowlist matches the code.

```
$ python3 -m pytest tests/test_submit.py -q     # 28 forbidden constructs, each with its reason;
37 passed in 4.6s                               # clean accepted; crash, busy loop rejected;
                                                # same sha256 is a no-op
$ python3 -m pytest tests -q
145 passed
```

### Section 7 — static site bundle ✅ (prepared, not served)

`python -m colosseum.site` writes `out/site/`: `index.html` (both ladders, latest meta
report), `bots/<name>.html` (docstring, origin/persona/author, every `.meta.json` field, mean
score against each opponent, ten most recent matches with replay links),
`replays.html` (a plain-link picker), `replays/<match>.html` (the viewer with that replay
embedded by the same `page_with()`), `submitting.html`, and `style.css`.

- **No JavaScript except the viewer's.** The picker is a list of links, one viewer page per
  replay (300 now, 20.5 MB in all, builds in 0.9 s).
- **No external requests.** External markdown links are dropped, and a test fails on any
  `http(s):` or `//` href or src.
- **Untrusted text escaped everywhere.** A small standard-library markdown renderer escapes
  before formatting. Bot files are read with `ast`, never imported.
- **Phone and dark mode, checked by eye**, from headless-Chromium screenshots at 390 px in
  both themes. First pass: long house names pushed Elo off-screen and ragged docstrings.
  Fixed with short display names plus a house/baseline tag, the full id on the bot page,
  docstrings reflowed as markdown, and the mean-score column hidden under 480 px.
- **"Ten most recent results":** only the latest tournament's replays exist, so each bot
  page shows ten matches from that night plus a per-opponent summary from the matrix.

```
$ python -m colosseum.site
out/site: 11 bots, 300 replays, 20.5 MB
$ python3 -m pytest tests/test_site.py -q     # builds; every link resolves inside the
5 passed                                      # bundle; index lists every live bot; escaping
```

### Section 8 — operations hardening 🚧 (built and tested; nightly.sh wiring after section 1)

- **Alerting.** A failed real night writes `out/ALERT.md` (reason + last 30 log lines); the next
  successful real night deletes it; dry runs never touch it. This is already live in
  `run_night`. `nightly.sh` will also write one if Python dies before `run_night` can.
- **Rotation** (`python -m colosseum.ops rotate [--dry-run]`). Replays younger than 14 days are
  kept. Older ones are kept only if a weekly report clipped them (recorded in
  `out/meta/clips.json`) or they are some bot's best or worst match; the rest are deleted.
  `out/house_raw/` is capped at 30 days. Disk usage is in the meta report and health check.
- **Backups** (`python -m colosseum.ops backup`). One tar.gz per night in `~/backups/`, last 14
  kept. It holds `bots/ reports/ out/leaderboard.json out/matrix.json BALANCE.md SEASON.md`;
  `__pycache__` and anything named `.house_league*` are excluded.
- **Health** (`python -m colosseum.health`): docker, CLI login (`claude auth status`, reading
  only `loggedIn` and `authMethod` and never printing the email), cron entry, disk, last
  night, alert. Exits 1 if any is bad. The meta report includes its output.
- **Phase times.** The night ledger has generation / validation / smoke / tournament;
  `ops after-night` adds "reports". The meta report flags any phase that doubled week over
  week.

```
$ python -m colosseum.health
ok  docker     server 29.1.3
ok  cli-login  logged in via claude.ai
ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
ok  disk       162 GB free, out/ is 41 MB
ok  last-night 2026-09-28: ok
ok  alert      none
$ python -m colosseum.ops rotate --dry-run
{"deleted": 0, "freed_bytes": 0, "kept_old": 0}
$ python -m colosseum.ops backup && tar -tzf ~/backups/swarm-colosseum-2026-09-29.tar.gz
bots/... (18 files), out/leaderboard.json, out/matrix.json, BALANCE.md, SEASON.md
  -- 0 entries matching house_league.env / pycache / credentials
$ python3 -m pytest tests -q
157 passed
```

### Section 9 — annealed-assignment defender family ✅ (joins the ladder after tonight)

`bots/defenders/annealed_assignment.py` and `annealed_assignment_eager.py`. Each tick's
launch and gun decisions are one small QUBO:
- **Variables:** `x_t` launch at a track, `y_t` fire the gun at it, plus slack bits.
- **Value:** P(striker | label) × damage × urgency, plus 0.7 × the same for neighbours inside
  the blast radius. P(striker | unknown) is learned in-match from the labels seen.
- **Cost:** the interceptor price, scaled up when stock is short of live threats.
- **Penalties:** the launch cap and stock (equality with slack), gun one-hot, two
  interceptors into one cluster, and gun plus interceptor on one target.
- **Solver:** simulated annealing in the standard library, 60 sweeps, seeded by (match seed,
  tick), keeping the best state seen.

The eager variant differs only in its knobs: horizon 60, interceptor price × 0.8 and an
unknown-prior floor of 0.4.

Measured sandboxed with `scripts/audit_defender.py`, 6 attackers × 10 seeds, same field as
`layered`:

| attacker | annealed | eager | same model, greedy picker | layered |
|---|---|---|---|---|
| staggered_screen_trickle | 0.721 | 0.744 | 0.722 | 0.128 |
| decoy_screen | 0.788 | 0.780 | 0.771 | 0.805 |
| flanker | 0.799 | 0.787 | 0.788 | 0.344 |
| multi_axis | 0.704 | 0.662 | 0.682 | 0.272 |
| rush | 0.800 | 0.809 | 0.796 | 0.807 |
| trickle | 0.747 | 0.747 | 0.645 | 0.435 |
| **mean score_defender** | **0.760** | **0.755** | **0.734** | **0.465** |

Both variants held the asset in 60 of 60 matches. **Honest reading:** it beats `layered`
by a wide margin, but most of that comes from the *value model*, not the optimiser. The
ablation (same model, greedy top-k picker) already scores 0.734. Annealing adds +0.026 on
average, almost all of it against trickle (0.747 vs 0.645), where choosing jointly across
many simultaneous small threats matters. Against discriminating_ledger's ~0.74 it's slightly
ahead, and it trades better against saturation (CER ≈ 1.0 against flanker and rush, vs 0.75)
because it values blast clusters.

Time: median 0.7 ms per tick, p99 2 ms, worst 37 ms including the sandbox round trip,
against a 2 s limit.

Tests (`tests/test_annealed.py`): the annealer hits the brute-force optimum on 20 random
QUBOs of 4–10 bits; the launch cap holds; matches are byte-deterministic; each variant beats
`layered` on a quick two-seed check; and no tracked file uses the word the brief rules out.

### Section 1 — the first unaided-discovery test ✅ found it

Night 2026-09-29 (cron, 03:30 UTC). The counter-meta attacker was given
discriminating_ledger's source and its closest calls; it was not told the diagnosis.

`2026-09-29_attacker_synchronized_ring`, from its docstring:
> "Its closest calls were all multi_axis (asset hp 10). Stock hit 0 and strikers leaked at
> ticks 165 and 166, arriving at nearly the same time from different axes … multi_axis did
> that partly by accident and wasted budget on decoys. We do it on purpose, with all strikers
> and no decoys."

Plan, in its own words: hold 30 strikers on a ring at 190 u, outside ledger's id gate
(`unknown and range < 135`, found by reading the source), then release them on one tick.
The 20 interceptors are spent, and about 10 survivors overlap on the one gun. It also spaced
the ring 12° apart to deny blast splash, the effect behind yesterday's flanker result, which
it read off the rush replay ("the ledger killed all 30 with only 20 interceptors").

That is the stock-exhaustion counter: a synchronised wave rather than a held-back reserve,
equivalent in effect. The raw response (`out/house_raw/2026-09-29T033135_cli_attacker_counter_meta.md`)
is only the code block; the CLI returns no reasoning text, so whether it weighed a reserve
wave specifically can't be seen.

```
.meta.json: persona counter_meta, target discriminating_ledger, tokens 5,816 in / 8,791 out
result:     score vs target 0.861, field mean 0.833, rank #1 attacker, beat_target true
breaches:   ledger 10/10 -- the only attacker that breaches it at all
ladder:     #1 attacker, Elo 1261, 98% win rate (over the 90% flag) -> BALANCE.md S0-2
```

The defender, `miss_budget_scheduler` (contrarian vs staggered_screen_trickle), plans
re-tries against a 0.85 kill chance and launches pairs when only one try fits. It beat its
target (0.735) and ties ledger at #1 defender (Elo 1113). Night: 23,672 tokens, 2 calls,
tournament 420 matches in 135 s. Season so far: 44,681 tokens, 3 real runs.

### After the night: staged changes merged, sections 3 and 8 wired ✅

Master was fast-forwarded to `post-night` (prepared and dry-run on a scratch copy before
03:30, so cron ran the old path untouched):
- **Prompt change** (`colosseum/prompts/generator.py`, PROMPT_VERSION `2026-09-29.1`):
  docstrings must start with `Idea: <one sentence>`, and there's a second-of-two note for
  escalation nights. Otherwise it's a verbatim move. The version is recorded in every bot's
  metadata.
- **Personas:** counter_meta in the rotation with no threshold; escalation after two
  unbeaten nights. Tomorrow: generalist attacker; contrarian defender vs synchronized_ring.
- **`nightly.sh`:** runs `ops after-night` (report if due, site, rotation, backup) and
  writes `ALERT.md` if Python dies early. The whole pipeline was dry-run on a scratch copy
  under a cron-like `env -i`: exit 0, 560 matches in 172 s.
- Tonight's after-night step was run by hand (the old wrapper didn't have it): site 13 bots
  and 420 replays, backup written, reports phase 1.8 s. `colosseum.health`: all six ok.
- The annealed defenders join tomorrow. Against synchronized_ring they are breached 10/10
  as well (mean 0.14).

```
$ python3 -m pytest tests -q
185 passed
```

## Session 7 — decisions of 2026-09-29

- **Candidate A approved** for season two. `s2-a-imperfect-id` is rebased on master (clean;
  190 tests pass on it) and recorded in `SEASON.md` to merge on 2026-10-26, not before.
- **S0-2 deferred a week.** New `ops` watch: after each night, `out/watch.jsonl` and
  `out/WATCH.md` record synchronized_ring's win rate overall and against each defender.
  "Under 90%" means it breaches that defender in ≤ 8 of 10 seeds. Nights 2026-09-30 to
  10-06; the verdict is written into the file and the weekly report. Baseline, night
  2026-09-29: 98% overall; best defender identify_then_engage, which it still beats 90%.
- **greedy_value_model** (in `bots/defenders/`, from tonight): annealed_assignment's value
  model with a greedy picker. A test keeps the two files' model code identical, so the
  ladder shows what the optimiser is worth.

**Escalation does not fire tomorrow.** The rule needs a bot unbeaten on *two* consecutive
nights. synchronized_ring is unbeaten on 2026-09-29 (every defender's mean score against it
is 0.13–0.29); on 2026-09-28 it did not exist. `personas.escalation(last two matrices)` → `{}`.
- **Night 09-30** (plan, checked by dry run): attacker generalist vs the field; defender
  **contrarian vs synchronized_ring**. The contrarian sees the standings plus the docstring of
  every existing defender, as approaches it must not reuse, then the rules and API. It is
  *not* shown synchronized_ring's source or replays.
- **Night 10-01**, if synchronized_ring is still unbeaten after 09-30: escalation, with **two
  counter_meta defenders** against it. Each sees the standings, synchronized_ring's full
  source (its docstring spells out its plan), its mean score against each defender, its
  three best pairings and its three closest calls, then the rules and API. The second also
  gets "Tonight two bots are being written against it; take a different approach from the
  most obvious counter."

### S0-2 economy levers on top of A (branch `s2-a-economy`, not merged)

Each lever alone on top of candidate A, full house (7 × 9, 10 seeds, sandboxed), stopping at
the first value that passes (ring < 90%, defender share 40–60%, no bot > 90%):

```
lever               smallest tried that moves the ring      result
A only              ring 98%, defenders 58%                 fail
gun rate of fire    1.75 rounds/tick: ring 88%, def 58%     PASS  (CER +0.00..0.02; gun_only +0.44)
gun ammo            400: ring still 98%                     fail  (ammo is never binding)
striker cost        2.25: ring 82%, but defenders 67%       fail
interceptor cost    2.0: ring 100%                          fail  (accounting only; stock unchanged)
interceptor stock   24: ring 87%, but defenders 68%         fail
```

**Recommend gun rate of fire 1.75** if the watch comes back structural. Caveats: it passes by
two matches (79 of 90), 10-seed results aren't smooth (1.9 overshoots the role band), and
the role band was already 58% under A because of the four strong new defenders. Rerun at
20 seeds on the decision date. Full table: `git show season2-candidates:SEASON2_CANDIDATES.md`.
The branches are rebased on master: `s2-a-imperfect-id` has 190 tests passing and contains
`71f427f`.

### Watch log (synchronized_ring, a defender under 90%?)

- **2026-09-30 (night 1/7): no.** It won 99%; best defender identify_then_engage (still
  beaten 90%). The contrarian `reveal_timed_prelaunch` scored 0.136 against it and ranks #2
  defender. The generalist attacker `phase_locked_ring` also wins 98%. Escalation confirmed
  for 10-01: both defender slots are counter_meta vs synchronized_ring. Optimiser vs model
  on the ladder: annealed_assignment mean score 0.608 (the best defender) vs
  greedy_value_model 0.582, but Elo 976 vs 1004 because Elo depends on match order. 26,357
  tokens; tournament 800 matches in 261 s.
- **2026-10-01 (night 2/7): yes, so a meta by the founder's rule.** Escalation ran as
  planned (two counter_meta defenders vs synchronized_ring). The first,
  `convergence_blast_scheduler`, holds it to a 40% win rate (4 breaches in 10 seeds; no other
  attacker breaches it at all). Its idea: wait until the synchronized ring has converged
  inside one blast radius, then fire on an earliest-deadline schedule for two or three kills
  per interceptor. It works inside the current rules, so the economy fix isn't needed on
  this evidence. It loses on mean score against the ring (0.402), so its `beat_target` is
  false; the watch criterion is win rate. synchronized_ring overall: 94%.
- **The second escalation slot was refused by the generator**
  (`out/house_raw/2026-10-01T033605_cli_defender_counter_meta.md`, 440 chars): it says an
  earlier attempt was stopped by a safety classifier, and that tuning interceptor allocation,
  gun targeting and timing against a synchronised saturation attack "maps closely onto real
  counter-drone engagement tactics". Input was 15,999 tokens against 7,912 for the same-size
  first prompt, consistent with a retry inside the call. The pipeline treated it as a
  rejection; the night completed. **Not worked around: a founder decision** (hard rule 1).
  56,669 tokens; tournament 880 matches in 280 s.
- **2026-10-02 (night 3/7): yes again.** Escalation night 2. `loiter_then_collapse`
  (counter_meta) holds synchronized_ring to 10% (it beats it on score too, 0.647). Idea:
  launch after the release, hold the interceptors over the asset by retargeting them back
  and forth, then fire them together into the closing ring. synchronized_ring overall 87%,
  under 90% for the first time. **Second refusal**, this time the first slot
  (`out/house_raw/2026-10-02T033341_cli_defender_counter_meta.md`): "stopped by a safety
  check". So far 2 of 4 escalation calls refused, both counter_meta defenders aimed at the
  synchronised wave. Escalation ends (the ring is now beaten on score). 10-03: counter_meta
  attacker vs convergence_blast_scheduler (#1 defender, 95%), generalist defender. Over the
  90% flag: convergence_blast_scheduler 95%, loiter_then_collapse 92.5%. 55,937 tokens;
  tournament 960 matches in 326 s.
- **2026-10-03 (night 4/7): yes.** Three defenders hold synchronized_ring under 90%
  (loiter_then_collapse 10%, convergence_blast_scheduler, and the new generalist
  `backscheduled_blast_packer`); it is at 86% overall. No refusals. The counter_meta attacker
  `depth_shell_saturation` beat convergence_blast_scheduler (0.585, #3 attacker). 54,667
  tokens; tournament 1,170 matches in 353 s, growing by roughly 100–200 matches a night.

## Session 8 — operating charter

Started from the charter. `BACKLOG.md`, `DAILY.md` and `DECISIONS.local.md` are written.
Where I've read the charter differently, and why:

1. **3.12 Stage 3 scoping is blocked, not deferred.** It asks what fidelity would let an
   arena result "predict anything about their defence logic", with a sensor model, 2.5D
   physics, and transfer experiments for the tactic library. That pulls directly against
   hard rule 1. On 2026-10-01 and 10-02 the generator itself refused two counter-meta
   defender prompts as mapping "closely onto real counter-drone engagement tactics". A
   roadmap whose explicit goal is real-world predictiveness is a decision for the founder
   to make with that in view. I won't write it on my own judgement. Everything else on the
   backlog stays abstract and proceeds.
2. **The daily session can't hold a hard per-call token cap.** `claude -p` has no token limit
   for an agentic session. `daily.sh` gets a 2-hour wall clock, records the session's tokens
   from the CLI's JSON output, and refuses to start the next day's session if the last one
   went over 200k. It's a cap by consequence, not by pre-check like the league's.
3. **No raw `docker` in the daily session's allow-list** (`docker run -v /:/host` is root).
   The project's own commands still run the sandbox. See DECISIONS.local.md.
4. **The cache key hashes the Rules object in force**, not `rules.py`'s bytes, so season-two
   candidate runs can't be served season-one results. See DECISIONS.local.md.

### 3.1 Match result cache ✅

`colosseum/cache.py`; `run_tournament(cache=True)` is the default. Key = (attacker sha256,
defender sha256, seed, hash of the Rules in force, engine version over sim / policy /
sandbox / sandbox_runner). The value is the full match meta plus the replay file name.
Results are consumed in the same fixed job order, so Elo doesn't move; every match that
does run still gets a fresh container.

```
live house, sandboxed, 10 seeds (scratch copy)
cold   1,170 matches, 1,170 played, 372.1 s
warm   1,170 matches,     0 played,   0.0 s
leaderboard / matrix / breaches: cold == warm == last night's pre-cache output (byte compare)
dry-run night on the warm copy: 1,400 matches, 230 played (exactly the 23 new pairings × 10),
  65 s for the whole night instead of ~6 min
tests/test_cache.py: cold == warm == no-cache; +1 bot plays exactly its matches; a rules or
  engine change replays everything; a cached entry == a fresh match; editing one bot replays
  only its matches
python3 -m pytest tests -q -> 196 passed
```

Live `out/cache/` was pre-warmed from that run (the 230 dry-run rows removed): 0 of tonight's
1,170 matches are missing. Rotation now keeps every current-roster replay, because a cached
pairing never rewrites its replay. Cache size and hit rate are in the ledger and the meta
report.

### 3.2 Generator token discipline ✅ — **prompt change: PROMPT_VERSION 2026-10-03.1**

**What grew, 8.7k → ~55k a night** (per call, from the log):
1. One call per persona from 09-29, instead of one call for both bots: about 2×.
2. **Output** (thinking plus code) went from 6k to 8–28k a call, about 65% of all tokens.
   Nothing in the evidence controls it; the 32k output ceiling per call stays.
3. Input prompts went from 6k to 21k chars. The generalist pasted the whole N×M matrix (now
   9 × 13) plus every opponent's docstring; counter_meta pasted 8–11 KB house-bot sources plus
   six indented JSON match summaries; the standings listed every bot.
4. Two calls that hit the safety check and retried internally used ~16k input each.

**Now:** a fixed evidence budget per persona, items added most informative first, with the
first item always included:

```
counter_meta 4000: target source, its 2 closest calls, its per-opponent row
exploiter    1500: the single most lopsided matchup (one match), the target's docstring
generalist   3000: compact matrix (2 dp), the top three opponents (first 600 chars each)
contrarian   3500: its target's source, nothing else
standings: top 5 per side (+ the target)
input tokens, live ladder, before -> after:
  attacker exploiter 3261->1345  counter_meta 6030->4583  generalist 8965->~2600  contrarian 4870->4155
  defender exploiter 3258->1323  counter_meta 4990->3952  generalist 6437->~2600  contrarian 7394->3514
```

`.meta.json` now records `evidence: {budget, used, included, dropped}`. The pre-call input
guard is raised (CLI overhead 4,000 → 12,000) because the retried calls used 15,999 input
tokens on prompts it had estimated at ~9,500. A test checks every logged call's (chars,
actual) pair. Dry run on a scratch copy: exit 0, 230 played / 1,170 cached, 66 s.
`python3 -m pytest tests -q` → 207 passed.

## Daily session 2026-10-03

Night 2026-10-03 ok, no `out/ALERT.md`, no WIP.md. 3.3 is lead-engineer only; 3.4–3.6 are
waiting for their dates; 3.12 is blocked. Next unblocked item: 3.7.

### 3.7 Tactic library export ✅

`python -m colosseum.library` writes `out/library/`: `INDEX.md` (families, one line per card,
written for an outside reader), `cards/<name>.md`, and `library.json` (for the site bundle
in 3.10). Each card gives name, side, family, persona, author, live/retired, the idea in one
sentence, a one-paragraph description from the docstring, best finish, nights in the top
five, the target it was written against, its unique coverage, what it beats and what beats
it (seeds won, mean score, last night it played), its best and worst replay, and its full
source. Selection rules and families: DECISIONS.local.md.

Bot files are parsed with `ast` and never imported. Every untrusted string is escaped:
no HTML, no links, no code spans, no table cells. The source sits in a fence longer than
any backtick run inside it, so a bot can't close the fence and inject markdown. That's
groundwork for the 3.8 red team (cards are one of its injection targets).

```
python3 -m colosseum.library     (on the out/ snapshot, 6 nights)
  -> out/library: 20 tactic cards, as of 2026-10-03
     attackers 8 (saturation 1, synchronised arrival 3, decoy screening 2, trickle 2),
     defenders 12 (identify first 3, patient 3, budgeted 2, value model 2, controls 2);
     none unsorted; rush and annealed_assignment get no card (never top five, no unique
     coverage)
python3 -m pytest tests/test_library.py -q -> 10 passed
  (selection, retired bot keeps its card, beats/beaten from breaches, replays only from the
   current roster, hostile docstring stays inert, never imported, byte-identical rebuild,
   unsorted family, every family member real and on its side)
python3 -m pytest tests -q -> 226 passed in 39 s
```

Not done here: it isn't in the nightly cron yet. Rebuilding it nightly and linking it from
the site is item 3.10.

### 3.3 Daily engineering session ✅ — watched once, then enabled

First run, by hand, under a cron-like `env -i` (`scripts/daily.sh`), watched through its
transcript:

```
{"branch": "fresh", "exit": 0, "seconds": 418, "status": "merged",
 "tokens": 132874, "tokens_incl_cache_reads": 2357191,
 "detail": "1 commit(s) fast-forwarded onto master"}
```

It took the next unblocked item, 3.7 the tactic library, and finished it in 7 minutes.
The wrapper reran the full suite (226 passed) and fast-forwarded master. Review of the
commit: bots parsed with `ast`, never imported; untrusted text escaped; 10 tests; choices
logged in DECISIONS.local.md. **Two corrections:** it added a `Co-Authored-By: Claude`
trailer (master history isn't rewritten, per rule 9; the prompt now forbids trailers, with a
test), and it writes the library to `out/library/` (regenerated, gitignored) rather than a
committed `library/`. That second one is flagged for the founder, not changed.

**Permission probe** (a throwaway session with the exact daily flags): `ls && touch …`,
`ls; touch …` and `ls | xargs touch …` were all refused, and no marker files exist. The
matcher checks each part of a compound command. The first session's `ls && cat …` ran because
the CLI treats `cat` as read-only. Its one real refusal was `python3 -c`, which is
deliberately not allowed.

Cron: `0 5 * * * /root/swarm-colosseum/scripts/daily.sh`, after the 03:30 league.
`python3 -m pytest tests -q` → 227 passed.

## Daily session 2026-10-03 (second run)

No ALERT. 3.8 and 3.12 are blocked, so this session took 3.9.

### 3.9 Engine fuzzing and invariants ✅ — and an engine fix

> **SECURITY:** any bot could crash a match from inside the sandbox, and (reading
> `tournament.py`, which has no per-match exception handling) the whole night's tournament
> with it. The bot just had to return `Infinity` or a 400-digit integer as an id, bearing or
> waypoint. The host decodes container replies with `json.loads`, which accepts NaN,
> Infinity and long integers. `int(inf)` and `float(10**400)` raised `OverflowError`, which
> the sanitiser didn't catch. A NaN bearing or waypoint didn't crash anything, but the drone
> then carried NaN coordinates for the rest of the match, into the replay (non-strict JSON).
> Fixed in `policy.py` with tests, including one through a real container. No night was
> affected: every night so far is `ok`, and none of the 1,270 replays in the out/ snapshot
> contains `NaN` or `Infinity` (grep). I didn't reproduce a whole-night crash end to end. The match-level crash is reproduced (fuzz run before the fix, below).

`python3 -m colosseum.fuzz` is a seeded fuzzer in the standard library (no `hypothesis`; see
DECISIONS). One integer fixes a trajectory: a rules variant (season 0 and five tuned edges:
certain kills, a large economy, budget 3 / stock 1 / ammo 1, launch caps of 1, a 50-tick
match), the match seed, and two random in-process policies. Those are defined in fuzz.py,
so they're trusted code and nothing from bots/ runs on the host. About one action in eight is
malformed on purpose. After every tick it checks: budget, stock and ammo stay in [0, start]
and never rise; budget used = cost of drones launched, stock used = interceptors, ammo used =
shots; per-tick launch caps hold; HP never rises; every position and velocity is finite;
launched = killed + impacted + alive for each drone type. Per match it checks: ends by
max_ticks; the result is strict JSON; a second run gives a byte-identical replay.

```
before the fix:  python3 -m colosseum.fuzz --start 0 --n 300
  -> failed 298/300: OverflowError (int too large to convert to float; cannot convert
     float infinity to integer), "drone 12 has a non-finite position", plus my own
     fuzzer bug (dict keys that JSON can't produce; fixed in the fuzzer)
after the fix:   python3 -m colosseum.fuzz --start 0 --n 300
  -> failed 0; end reasons asset_destroyed 212, attacker_exhausted 53, tick_limit 35; 20.0 s
python3 -m colosseum.fuzz --start 0 --n 10000   (run by the lead engineer; the session
  exited before its own 10k run finished)
  -> failed 0 of 10,000; 1,828,614 ticks; asset_destroyed 6,677, attacker_exhausted 1,662,
     tick_limit 1,661; 617.7 s
python3 -m pytest tests/test_fuzz.py -q -> 31 passed (sandbox test ran: docker available)
```

Tests (`tests/test_fuzz.py`): sanitiser regressions for each non-finite value; finite
actions cleaned exactly as before; a fixture pair that sends non-finite numbers can't crash
a match in-process or through a real container (replays identical both ways); 60
trajectories hold every invariant; trajectories reproduce from their number; every rules
variant is reached; the fuzz policies really do send malformed actions; three deliberately
broken engines (asset heals, free ammo, NaN drone) and an over-launch are all caught; the
nightly step logs and alerts.

Determinism of real bots under the fix: the baseline-only tournament, rerun in-process with
the fixed engine (`python3 -m colosseum.tournament --out out/verify-3.9 --quiet`, 350
matches). A dozen `rush` replays spot-checked against last night's `out/replays` all match
`score_defender` exactly. That's a sample, not a full diff (the session's allow-list has no
diff or hashing tool). The unit test that finite actions clean identically is the general
argument. `out/verify-3.9/` is scratch inside the gitignored out/ snapshot.

**Nightly:** `ops after-night` now runs 500 new trajectories (numbered from the date, about
35 s), appends to `out/fuzz.jsonl`, and writes ALERT.md on any failure. **The engine
version changed (policy.py), so tonight's tournament runs cold, all pairs.** That's expected
per the charter. Last cold run was 372 s.

`python3 -m pytest tests -q` → 258 passed in 46 s (227 + 31 new).

### Founder steer 2026-10-03: build session every 3 hours, build items only

- `colosseum/daily.py` is scoped: the session may work only on **3.10, 3.11, 3.12 and
  standing hygiene**. It must declare its item in `SESSION_ITEM` before starting; the wrapper
  refuses to merge (status `out-of-scope`, with an alert) if the item is missing, gated
  (G, 3.8) or frozen.
- **No looping:** an item whose last two sessions both ended without a merge is frozen.
  The prompt lists frozen items to be written up, not worked on.
- **Cron:** `0 0,6,9,12,15,18,21 * * *` replaces the 05:00 entry. That's every three hours
  except 03:00, which would overlap the 03:30 league. The lock stops two sessions overlapping.
- **G (generator prompts and content check):** untouched, waiting for the founder's text.
  **3.8:** held; it runs only interactively, with the founder.
- Tests: an out-of-scope session is never merged; an item with two unmerged sessions in a
  row is frozen; the prompt names the scope. `python3 -m pytest tests -q` → 261 passed.

### 2026-10-03 build session: 3.10 site bundle kept current + about page

**Alert from the previous session:** the 09:00 build session was refused
(`out-of-scope -- SESSION_ITEM is None`). It never wrote `SESSION_ITEM`, so the wrapper
correctly declined to merge. The cause was the prompt, and 94fea0b already fixed it (write
`SESSION_ITEM` with the Write tool, and how to run allowed commands). This session wrote
`SESSION_ITEM` = `3.10` first. Nothing else to fix. `out/ALERT.md` is the snapshot's copy;
the live one clears on the next successful night.

**3.10, done:**
- `ops after-night` now builds the tactic library (`library.build()`) after the meta
  report and before the site, so the bundle is current every night. A "no ladder" exit
  from the library becomes an alert, and the later steps (fuzz, rotation, backup) still run.
- `colosseum/site.py` adds:
  - `library/index.html` and `library/cards/<bot>.html`, rendered from `out/library/`.
    Replay links in the cards point at the bundle's viewer pages. If a replay is missing
    the link goes to the picker. A live bot's card links to its ladder page.
  - `seasons.html`: SEASON.md, then every archived season under `seasons/<S>/`. Each
    markdown file gets a page, links between archive pages are kept, and every other
    link is dropped. No season is archived yet, and the page says so.
  - `about.html` from the new `ABOUT.md`, plain language for a sixteen-year-old: what it
    is, why it exists, how a match works, how to read the ladder, how to submit (closed for
    now), and the abstract-only rule stated honestly.
  - The nav on every page links to Tactic library, Seasons and About.
- Renderer fixes that the library needed. Backslash escapes and `&amp; &lt; &gt;` (what
  `library.md_safe` writes) now render as literal text, escaped once for HTML. Before,
  they would have shown up as `\[` and `&amp;lt;`. An escaped `|` stays inside its table
  cell. A long code fence only closes on a run of backticks at least as long, so bot
  source with ``` inside stays code.
- Still unserved. Nothing was opened or published.

```
python3 -m colosseum.library -> /srv/swarm-daily/out/library: 20 tactic cards, as of 2026-10-03
python3 -m colosseum.site    -> /srv/swarm-daily/out/site: 22 bots, 1170 replays, 20 tactic cards,
                                0 archived seasons, 76.4 MB
grep of out/site/library for &amp;lt; / &amp;amp; / \[ / \| / href="*.json" -> no matches
python3 -m pytest tests/test_site.py tests/test_library.py -q -> 23 passed
python3 -m pytest tests -q -> 270 passed in 47.27s
```

New tests (`tests/test_site.py`): the bundle has the library, seasons and about pages. Every
non-viewer page links all three. The library index links every card, and cards link replay
pages with no raw `.json`. Archive links are kept or dropped correctly, including the
stylesheet path two levels deep. The about page has its six sections and the abstract-only
line. A missing library gives a placeholder page. Library escapes render once and never as
markup. Escaped pipes and long fences render correctly. The existing link test now covers
every new page.

### 2026-10-03 build session: 3.11 workshop kit

**Alert:** none (`out/ALERT.md` absent, no `WIP.md`). Night 10-03 was ok. `SESSION_ITEM` =
`3.11`, written first.

**3.11, done.** `workshop/`, for first-time Python students. It runs offline with Python
3.11 and no Docker:
- `LESSON_PLAN.md`: 90 minutes. Observe a match, read `rush.py`, change one number in
  `straight_line.py`, then the exercises, then share.
  `FACILITATOR.md`: one page. Setup, why it's safe, common errors, answers, tone.
  `README.md`: the student sheet, with rules and exercises.
- Starters, three per side with one `# TODO` each. Attackers: `straight_line`,
  `screen_then_strike`, `many_sides`. Defenders: `closest_first`, `look_before_firing`,
  `gun_line`.
- Five exercises, each with a success test of the form "breach/defend against X on these
  seeds". 1: gun on vs `rush`, seeds 1, 3, 4. 2: decoy screen vs `nearest_first`, seeds
  0, 1, 3, 4. 3: confirmed strikers only vs `decoy_screen`, seeds 0–5. 4: four sides vs
  `nearest_first`, seeds 0–3. 5: one bearing per striker vs `identify_then_engage`, seeds
  0–5. Solutions are in `workshop/solutions/`.
- The targets come from a seed sweep (seeds 0–5) of every starter's knob against the
  baselines. I ran it as a temporary pytest file and didn't commit it. The game is noisy,
  so I only kept targets where the edit flips every listed seed. The sweep also gave the
  lesson's "more isn't better" moment: `straight_line` breaches `nearest_first` on 4 of 6
  seeds at 1 launch per tick and on 1 of 6 at 4. Clumped drones die to one burst, and
  exercise 5 builds on that.
- `play.py` (one match, writes an offline replay page through the viewer's
  `page_with`) and `check.py` (one exercise, or every exercise) are both built on `kit.py`.
  The student's file is refused unless it is a regular `.py` file (no links), at most 64 KB,
  outside `bots/house` and `bots/submitted`, and passes `colosseum.submit.check_source`.
  The opponent can only be named, never given as a path.
- Root `Makefile`: `make workshop` runs `python3 workshop/check.py`. That checks every
  solution passes and no unedited starter does.
- Decision logged in `DECISIONS.local.md`: workshop bots run in-process, the same way the
  baselines do.

```
python3 -m pytest tests/test_workshop.py -q -> 23 passed in 1.01s
python3 -m pytest tests -q                  -> 293 passed in 55.61s
```

What was and wasn't run: the session's allow-list has no `make` and no plain
`python3 workshop/...`. So `make workshop` itself was not run here. Its command was:
`test_make_workshop_passes` calls `check.main([])` in-process and asserts the output says
`all exercises solvable` with five `ok` lines. `play.py` runs the same way in
`test_play_writes_an_offline_replay`. New tests also cover: the starter counts and one TODO
each, every bundled bot passing the arena's static checks, single-exercise checks, the
opponent list, a repeated match being identical, refusal of league bots, of `import os` /
`open`, of non-.py files, missing files, symlinks, oversized files and files with no ROLE,
opponents by name only, and workshop code importing only stdlib + `colosseum`. The refusal
inputs are inert one-liners, and none of them is ever loaded.

Not verified here: an actual run on Python 3.11 or Windows (this host's Python ran the
tests). The facilitator guide says to run `make workshop` / `python workshop/check.py` on
one laptop before the day.

## Build session 2026-10-03 — 3.12 engine scoping, for the game ✅

There was no ALERT. Night 10-03 was ok. 3.12 was the next unblocked item in scope. Session 8
had blocked it because the old text was about real-world predictiveness. On 2026-10-03 the
founder rewrote it to cover the game only ("no goal of predicting real defence
performance"). So it's now within the charter, and I wrote it.

`ENGINE_SCOPING.md` (two pages). It works from `sim.py` and `rules.py` as they are and
finds three thin spots: one noise σ at every range, a classification cliff at 150 u with no
mislabels, and instant turns (which is why `flanker` wins 0%). It scopes four features as
Rules fields, each with a neutral default that reproduces today's engine:
1. sensor noise growth, dropouts and phantom tracks
2. classification confusion with a `cls_conf` key
3. turn rates for drones and interceptors
4. altitude bands

For each one it covers the texture it adds, the change to the bot API, size and risk.
Constraints: no new RNG draws at neutral defaults, plus a byte-identical replay test against
today's engine; additions to observations only; fuzzer coverage; abstract names and
defaults only. Success is measured in the game: occupied library families, unique
coverage, no bot over 90%, roles 40–60. Proposed order: confusion → turn rates → sensors,
on a later-season candidate branch. Bands only with a founder decision. No transfer claims,
and real systems are out of scope.

Raised with the founder under the scope rule: `ROADMAP.md` Stage 3 still lists "a paid API
for a company to test its own defence logic". That points away from the stated scope. I
haven't changed ROADMAP. It's a yes/no for the founder.

No code changed.

```
python3 -m pytest tests -q -> 293 passed in 55.72s
```

## Build session 2026-10-03 (evening) — hygiene

There was no ALERT. Night 10-03 was ok. 3.10, 3.11 and 3.12 are done, so this session took
hygiene (charter section 4). Checks and what they printed:

```
python3 -m colosseum.health
ok  docker     server 29.1.3
ok  cli-login  logged in via claude.ai
ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
ok  disk       160 GB free, out/ is 161 MB
ok  last-night 2026-10-03: ok
ok  alert      none
python3 -m pytest tests -q --durations=10 -> 293 passed in 54.03s (slowest: clip test 10.32s)
ls -la out/cache -> results.sqlite, 2,043,904 bytes
```

- `health`: all ok.
- Disk: health prints free space (160 GB) but not a percentage. The session's commands
  can't run `df`, so I haven't checked the 70% rule as a percentage.
- pytest: under a minute, well inside the five-minute limit. No slow-marking needed.
- No `WIP.md`. The only untracked file in the root is `SESSION_ITEM`, which is gitignored.
- Cache: 2.0 MB on disk. The hit rate wasn't measured this session; it belongs in the next
  meta report.
- Backups: **not verified against a real archive.** Listing `/root/backups` was refused
  (it's outside the worktree), and extracting a tar isn't an allowed command anyway. As a
  stand-in I added `test_a_backup_restores_byte_identical_into_a_scratch_copy`
  (`tests/test_ops.py`). It writes a backup with `ops.backup`, extracts it into a scratch
  directory and asserts every file comes back byte-identical. That covers the code path, not
  last night's archive. Restoring a real archive and running the tournament from it still
  needs an interactive session that can reach `~/backups`.

```
python3 -m pytest tests -q -> 294 passed in 44.88s
```

## Build session 2026-10-03 (night) — hygiene

There was no ALERT. Night 10-03 was ok. 3.10, 3.11 and 3.12 are done, so this session took
hygiene again. It closed one gap from the evening session: the 70% disk rule couldn't be
checked as a percentage.

- `colosseum/health.py`: the disk line now prints `% used` (from `shutil.disk_usage`) and
  fails at 70% or more, as well as on the existing free-space and out/-size limits. Test:
  `test_health_disk_fails_at_70_percent_used` (`tests/test_ops.py`) stubs the disk at 69%
  (ok) and 70% (bad).
- Checks at the start, before the change:

```
python3 -m colosseum.health -> all six ok; disk "160 GB free, out/ is 161 MB"
python3 -m pytest tests -q -> 294 passed in 48.51s
ls -la out/cache -> results.sqlite, 2,043,904 bytes
```

- After the change:

```
python3 -m colosseum.health
ok  docker     server 29.1.3
ok  cli-login  logged in via claude.ai
ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
ok  disk       23% used, 160 GB free, out/ is 161 MB
ok  last-night 2026-10-03: ok
ok  alert      none
python3 -m pytest tests -q -> 295 passed in 43.93s
```

- No `WIP.md`. The only untracked root file is `SESSION_ITEM`, which is gitignored.
- Still open: the cache hit rate wasn't measured (it belongs in the meta report). Restoring a
  real archive from `~/backups` still needs an interactive session.

## Daily session 2026-10-04 — hygiene

There was no ALERT and no WIP. 3.10, 3.11 and 3.12 are done, so hygiene was the only
in-scope item. This session changed no code.

```
python3 -m colosseum.health
ok  docker     server 29.1.3
ok  cli-login  logged in via claude.ai
ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
ok  disk       23% used, 160 GB free, out/ is 161 MB
ok  last-night 2026-10-03: ok
ok  alert      none
(1.7 s)
python3 -m pytest tests -q -> 295 passed in 56.42s
ls -la out/cache -> results.sqlite, 2,043,904 bytes, dated Oct 3 04:23
git status --short --ignored -> only gitignored entries (SESSION_ITEM, out/, caches)
```

- **Night 10-04 isn't in this snapshot.** The `out/` copy is dated Oct 4 00:00, before the
  03:30 run. `out/nights.jsonl` has no 2026-10-04 entry, and `health` reports 10-03 as the
  last night. I can't say whether night 10-04 ran or how it went.
- **Why the cache hit rate is still missing.** No real night has run with the cache yet.
  The cache landed in `13a62b6` at 2026-10-03 04:23 UTC, about 40 minutes after night 10-03
  finished. The 10-03 log line still uses the old wording ("1170 sandboxed matches in
  352.8s"), and its summary has no `cache` key. The code to report the rate already exists:
  `house_league.py` writes `cache=` (matches, ran, cached, entries) into each night's summary
  and logs "N played in the sandbox, M from the cache". `meta_report.py` turns that into a
  weekly hit rate. Night 10-04 is the first that can produce the number. The next session
  should read it from that night's log.
- Not done again: restoring a real archive from `~/backups` and running the tournament from
  it. No allowed command reaches `~/backups`, so it still needs an interactive session.
- The build session's scope is used up. 3.10, 3.11 and 3.12 are done, and every other open
  item is waiting on a date (3.4, 3.5, 3.6, 3.13), on 3.8 (3.14), or on the founder (G,
  3.8). Until the scope changes, each session can only repeat these hygiene checks.

## Session 9 — launch sprint (2026-10-04)

`LAUNCH_STATUS.md` is the dashboard. Where I've read the sprint differently, and why:
- **Unattended sessions take only the mechanical items** (L5–L10, L12, L14, hygiene). L1–L4
  and L13 (research write-ups at the content seam where all four safety stops clustered),
  L11 (the secret audit) and L15–L16 stay with me, interactively. That follows the founder's
  own steer to keep a human on that seam.
- **Cadence:** every 2 h except 02:00 and 04:00 (they'd overlap the 03:30 league):
  `0 0,6,8,10,12,14,16,18,20,22`. A session that finishes with time left may take more items,
  listed in order in `SESSION_ITEM`, and all of them must be in scope or nothing merges.
- **L11 vs hard rule 7.** L11 says to move `.house_league.env.save` out of the repo; rule 7,
  which still applies, says never to move it. It becomes a one-line founder action in
  `LAUNCH_CHECKLIST.md`.
- **L10 vs hard rule 9.** The publish script force-pushes the built site to `gh-pages`. That's
  a generated branch, never master, and the script stays dry until the founder's yes. Noted
  here as the one exception to "no force pushes".
- **Item G is not installed.** No new prompt text has arrived; `PROMPT_VERSION` is still
  `2026-10-03.1`.

### L5 `make reproduce` ✅

`colosseum/reproduce.py` + `make reproduce`. It replays the whole roster in the sandbox with
no cache and byte-compares the result with the committed `results/`. `ops after-night` now
commits `results/` together with the night's new house bots, so every commit holds the bots
and the results they produce. Proof on a fresh clone:

```
$ git clone /root/swarm-colosseum clone1 && cd clone1 && time make reproduce
  leaderboard.json   identical
  matrix.json        identical
  breaches.json      identical
REPRODUCED in 364 s          (real 6m4s, with the persona ablation sharing the CPU)
```

### Founder decisions 2026-10-04, applied

- **Season two = candidate A only.** S0-3 is logged in BALANCE.md (defenders 61.6%,
  convergence_blast_scheduler 91%), with a 7-night watch from 2026-10-05
  (`out/WATCH_S0-3.md`; does any attacker hold it under 90%?). Watches are a list in
  `ops.WATCHES` now. The charter's role test reads "inside 40–60 in either direction".
- **The 14-night persona ablation is its own session:** `scripts/ablation_session.sh`, cron
  05:00, never inside the nightly run. Due from real night 14. Each run spends at most 200k
  minus that night's league tokens, stops cleanly before a call that could cross it (exit 3),
  and resumes from `generation.json`. It only evaluates, re-renders research/03 and commits
  once every slot is filled. About 3 slots a night fit, so it takes roughly 9 nights.
  `ops ablation-session` today → `not due (7 of 14 nights)`.
- **Item G reduced to the content check** (`colosseum/content_check.py`). The prompts are
  unchanged for season one. Generic real-world vocabulary plus the shape of a designation
  code, so the file names nothing real. It runs before validation; a hit is logged
  `CONTENT: rejected …`, the bot is never written, and the night continues. No false positives
  across the 50 existing bot and workshop files (after excluding encoding names such as
  UTF-8). Scratch dry run: exit 0, 250 played / 1,400 cached, 94 s. 309 tests.

### L11 secret and history audit — SECURITY finding, stopped for the founder

`scripts/audit_secrets.py` (no scanner installs offline, so a regex pass) covers every
commit on every branch: each file version, each message, each author/committer identity.
It prints where, never what.

```
$ python3 scripts/audit_secrets.py
scanned 89 commits, 341 distinct file versions
  home-path: 7 hit(s) in 2 path(s): .house_league.env.example, PROGRESS.md
  hostname: 85 hit(s) in 1 path(s): (commit message / identity)
  ipv4: 2 hit(s) in 2 path(s): tests/fixtures/socket_bot.py, tests/test_sandbox.py
```

- **No key or token shapes anywhere in history.** `.house_league.env`, `.house_league.env.save`,
  anything under `out/` (including `out/house_raw/`) and `~/.claude` were **never committed**.
- `ipv4` is `1.1.1.1`, the address the sandbox's no-network test tries; it is not this
  machine. The `home-path` hits are `/root/.local` and `/root/backups`, which are generic.
- **SECURITY: 84 commits are authored `root@<this server's hostname>`**, because git fell back
  to the machine's hostname with no identity configured. A public push would publish the
  hostname, which names the hosting provider and the server. Per L11, the fix is a history
  rewrite on a fresh clone that the founder approves, not an amend. The exact commands are in
  LAUNCH_CHECKLIST.md, step 2; I haven't run them. The leak is stopped going forward:
  repo-local identity `Swarm Colosseum <dev@swarm-colosseum.invalid>`.
- The site bundle and `results/` contain no hostname or IP. The site's home page did embed
  the meta report's **Health** section (Docker version, login method, cron path, disk), so the
  site now drops that section (`site.public_report`, with a test); the report keeps it.
- `.house_league.env.save` is still in the working tree: moving it is a founder action under
  hard rule 7 (LAUNCH_CHECKLIST.md, step 1).

### L11 rewrite, approved by the founder 2026-10-04 ✅

`scripts/rewrite_identity.sh SOURCE DEST "Name" "email"` mirrors the repo into a fresh bare
clone and, there only, rewrites every `root@<host>` author and committer. It then drops
filter-branch's backup refs and prunes, so the old identity is really gone. The live repo is
never rewritten (hard rule 9); the publish step (L10) pushes from the rewritten clone. The
audit allow-lists exactly the reviewed benign values (`1.1.1.1`, `/root/.local`,
`/root/backups`, a synthetic `/root/x`), so it exits 0 only when nothing else is found.

```
$ scripts/rewrite_identity.sh /root/swarm-colosseum public.git "$(sed -n 1p scripts/public_identity)" "$(sed -n 2p scripts/public_identity)"
rewritten: 90 commits
$ git -C public.git log --all --format='%an <%ae>' | sort | uniq -c
     84 Vikram Goel <...>     5 Swarm Colosseum league <league@localhost>     1 Swarm Colosseum <dev@...invalid>
live repo untouched: 84 root@ commits remain there
```
- Identity switched to the GitHub noreply address at the founder's request (`scripts/public_identity`).
- `.house_league.env.save` moved out of the repo by the founder (2026-10-04); `git status` shows no untracked files.

## Build session 2026-10-04 — L6 site redesign ✅, hygiene

There was no ALERT and no WIP. Night 10-04 was ok (in the log: 2 bots written, 0 rejected,
835.8 s). L6 was the first open in-scope sprint item.

**L6.** `colosseum/site.py`:
- `index.html` is now a home page. It says what the project is and states abstract-only.
  Four start-here cards: about, replays, tactic library, research. Then the top five of each
  ladder, a link to the full ladders, and the research list.
- `ladders.html` has both full ladders and the latest meta report (the old index content).
- `research.html` and `research/<n>.html` render `research/*.md`. Links between the
  write-ups are kept; every other link is dropped and its label kept. Everything is
  HTML-escaped as before.
- The nav on every page now has Home, Ladders and Research. One shared `ladder_table()`
  builds both ladder views.
- Tests (`tests/test_site.py`): the home page shows the top five and only the top five, and
  has the start-here links. Research pages keep links between write-ups and drop the rest.
  An empty research directory says so. Every page links home, ladders and research. The
  existing every-link-resolves and escaping tests now also cover the new pages.

```
python3 -m pytest tests/test_site.py -q -> 17 passed in 2.09s
python3 -m colosseum.site -> out/site: 24 bots, 1400 replays, 20 tactic cards, 4 research pages, 0 archived seasons, 93.7 MB
python3 -m pytest tests -q -> 313 passed in 49.97s
```

**Hygiene: why night 10-04 got 0 cache hits.** The night log says "1400 played in the
sandbox, 0 from the cache (2570 entries)". This is not a cache bug. `38f2a8e` (3.9, the
non-finite-number fix, 10-03 05:07) changed `colosseum/policy.py`. That file is one of
`cache.ENGINE_FILES`, so every key from the 10-03 cold run (1170 entries) was invalidated,
which is the intended behaviour. 1170 + 1400 = 2570 entries fits. No engine file has changed
since then (`git log` on sim/policy/sandbox/sandbox_runner/rules/cache/tournament), so night
10-05 should be the first warm night. Night 10-04 took 835.8 s, under the 15-min limit.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok
```

I didn't start L7. It renders clips in a Docker/Chromium container, and an unfinished L7
would need a WIP.md, which would also block today's L6 merge.

## Build session 2026-10-04 (second) — L7 five clips ✅

No ALERT, no WIP. L7 was the first open in-scope sprint item.

**L7.** `colosseum/clip.py` and `docker/clip/render.py`:
- `--gif`: the container also writes a GIF next to the mp4 (360 wide, 15 fps, one 64-colour
  palette, no dither). `render.py` is mounted at run time, so the image is unchanged.
  The GIF limit is 8 MB; the mp4 limit stays 5 MB. `*.gif` is gitignored like `*.mp4`.
- `--showcase` renders five fixed picks at 1x into `out/clips/showcase/`, with a captioned
  `README.md` (gif inline, mp4 linked). Each pick names a pairing and the outcome the story
  needs; the lowest seed with that outcome is used, so reruns pick the same match. The picks
  are: rush vs nearest_first (how a match works), decoy_screen vs discriminating_ledger,
  synchronized_ring vs the ledger (breached), the ring vs loiter_then_collapse (defended),
  interleaved_shell_ring vs loiter_then_collapse (breached). Captions use research/01's numbers
  and the bots' own docstrings.
- At 4x these matches were about 1 s long (16 frames for 122 ticks), so the showcase uses 1x.
- Tests: a real GIF render in the container (`GIF89a`, under the limit), seed picking
  (lowest seed with the outcome; none raises), showcase output with a stub renderer (calls,
  README captions and links), and five distinct pairings.

```
python3 -m pytest tests/test_clip.py -q -> 7 passed in 7.33s
python3 -m colosseum.clip --showcase ->
  1_how_a_match_works.mp4: 0.02 MB, gif 0.06 MB, 61 frames, ticks 0-122 at 1x
  2_decoys_ignored.mp4: 0.03 MB, gif 0.06 MB, 59 frames, ticks 0-118 at 1x
  3_ring_vs_ledger.mp4: 0.05 MB, gif 0.13 MB, 61 frames, ticks 0-122 at 1x
  4_collapse_vs_ring.mp4: 0.05 MB, gif 0.13 MB, 62 frames, ticks 0-124 at 1x
  5_shell_ring_vs_collapse.mp4: 0.07 MB, gif 0.21 MB, 119 frames, ticks 0-238 at 1x
python3 -m pytest tests -q -> 317 passed in 48.61s
```

The clips were rendered from this session's `out/` snapshot. The live `out/` gets them on
the next `python -m colosseum.clip --showcase`. They aren't on the site yet.

## Same session — L8 README, CITATION, CONTRIBUTING, licence note ✅

- `README.md` was still the Stage 1 text ("25 tests", "Stage 2 not started", in-process
  only). It's rewritten for launch: what's here (league, library, research, workshop, site),
  how to run it (`--sandbox` for house bots; without it the tournament skips them), the clip
  showcase, `make reproduce`, the game in one screen (numbers checked against `rules.py`), a
  short bot example pointing to SUBMITTING.md, the layout, and contribute/cite/licence. It
  doesn't link ROADMAP.md, because the ROADMAP "paid API" line is still an open founder
  question.
- `CITATION.cff` (CFF 1.2.0) names Pelennor as author. It has no URL, version or licence:
  the repo name and the licence are founder decisions.
- `CONTRIBUTING.md` covers the rules (abstract only, sandbox, determinism, frozen rules,
  tests), what's accepted now (bug reports, fixes, docs; bots not yet) and how to report
  security issues without public details.
- `LICENSE_NOTE.md` says no licence is granted yet, and gives the recommendation that
  LAUNCH_CHECKLIST step 3 refers to: Apache-2.0 for code and bots, CC BY 4.0 for write-ups and
  results, inbound = outbound for submissions, with MIT as the simpler alternative. It
  doesn't add a `LICENSE` file.
- `tests/test_launch_docs.py`: local links in all four files resolve, `content_check`
  finds nothing in them, the citation has its required keys and claims no licence, and the
  README says submissions are closed and no licence is granted.

The showcase GIFs aren't embedded in the README. `out/` and `*.gif` are gitignored, so
embedding them would need either committed GIFs or the publish step (L10) copying them in.
That's left for L10.

```
python3 -m pytest tests/test_launch_docs.py -q -> 10 passed in 0.02s
python3 -m pytest tests -q -> 327 passed in 47.86s
```

## Build session 2026-10-04 (third) — L9 submissions via PR + workflow ✅

Alert: none. Night 10-04 ok (log above).

- `colosseum/submit_pr.py`:
  - `check` (for CI) takes `git diff --name-status` output and the PR author's login. It
    passes only when the PR adds or updates at most one bot per side, at
    `bots/submitted/pr/<login lowercased>/<NAME>.py`, and touches nothing else (not the
    checker, the workflow, the engine or other players' folders). Each file must be a
    plain file (no symlinks), within 64 KB, UTF-8, pass `submit.check_source` with its
    ROLE, be named NAME.py, and pass `content_check`. It reads text and runs `ast`; it never
    imports or runs a bot.
  - `intake` (league machine, after merge) sends every PR bot through `submit.submit`: the
    static checks again, then the sandbox smoke test, then a copy into
    `bots/submitted/<side>/`. It's not wired into the nightly run, because submissions are
    closed.
- `.github/workflows/submission.yml` triggers on `pull_request` for `bots/submitted/pr/**`.
  `contents: read`, `persist-credentials: false`, no secrets, Python 3.11, stdlib only.
  The login and base ref reach the shell only through env variables. A PR can edit its own
  workflow, so the green check is advisory and intake is the gate (DECISIONS.local.md).
  Nothing is pushed or enabled. The file is inert until the repo is public.
- SUBMITTING.md and CONTRIBUTING.md describe the PR route. Both still say submissions are
  closed.
- `tests/test_submit_pr.py` (18 tests):
  - a clean bot passes; one bot per side is fine, two on one side are refused;
  - refused: edits outside the author's folder (checker, workflow, `bots/submitted/<side>`),
    someone else's folder, a wrong file name, a nested path, a deletion, an empty PR, more
    than 2 files, unusable logins, a forbidden import, a real-world term, a symlink;
  - the check never executes the file;
  - PR bots count as untrusted and aren't in the tournament's folders;
  - intake routes through submit (stubbed: no bot runs on the host);
  - a lint of the workflow (trigger, read-only, no secrets, no `${{ }}` in `run:`);
  - the docs mention the path.

```
python3 -m pytest tests/test_submit_pr.py tests/test_submit.py tests/test_launch_docs.py -q -> 65 passed in 11.21s
python3 -m pytest tests -q -> 345 passed in 70.38s
```

Not done: the workflow has never run on GitHub (there's no remote, and nothing is public).
L10/L15 should run it on the publish mirror once the founder says yes. The founder also
needs to turn on "require approval for first-time contributors' workflows" when the repo is
created.

## Same session — L12 workshop README for teachers ✅

L10 (the dry publish pipeline) was next in order, but I took L12 first:
- L10's inputs aren't decided yet: the licence, the repo name and visibility are still with
  the founder.
- Its core step, `scripts/rewrite_identity.sh`, can't be run with this session's allowed
  commands.

L10 is next.

- `workshop/TEACHERS.md`, one page for a teacher deciding whether to run the workshop:
  - who it's for, what students practise, and what it isn't (abstract on purpose);
  - what's needed (Python 3.11, a browser, a projector; no internet, installs, accounts or
    Docker);
  - the kit's files in the order a teacher uses them, with solutions marked teacher-only;
  - three setup steps;
  - safety in one paragraph;
  - what happens after: submissions aren't open, and no licence has been chosen, so check
    before copying beyond your own class.

  It claims nothing the kit doesn't do. A first draft had an age, a setup time and an
  "eight lines" that I couldn't back up, so they're gone.
- Linked from the root README (workshop line) and from the top of FACILITATOR.md.
- Test `test_the_teachers_page_matches_the_kit`: its links and the files it names exist,
  the setup command and its expected output match `check.py`, `content_check` finds nothing,
  and the README links it.

```
python3 -m pytest tests/test_workshop.py tests/test_launch_docs.py -q -> 34 passed in 1.67s
python3 -m pytest tests -q -> 346 passed in 66.49s
```

## Build session 2026-10-04 (fourth) — L14 season report draft ✅

No alert, and the 10-04 night was ok. I skipped L10 again because its inputs (licence, repo
name, visibility) are still with the founder, and took L14.

- `python3 -m colosseum.meta_report --season` writes `out/meta/SEASON_1.md` and copies it to
  `reports/SEASON_1.md`. It's generated from league data, so item 3.6 at the boundary is a
  rerun plus the copy into `seasons/S1/`, not a rewrite. Until all 28 nights exist, the
  title says "draft, n of 28 nights".
- Sections, following charter 3.6:
  - the season in numbers: nights, bots written/alive/retired/rejected, matches (one
    attackers × defenders × seeds round-robin a night, from history/), cache entries,
    tokens;
  - top of each ladder;
  - the five best ideas: best rank on own ladder, then Elo, house bots only. Each has its
    one-sentence idea, taken from `library.idea_of` so it matches the tactic card, and one
    clip of its best match;
  - every BALANCE.md finding and the watch verdict;
  - the research write-ups by title (the ablations and the unaided discoveries; their
    titles state the answer);
  - coverage at the end: defenders nobody gets through, attackers nobody stops, unique
    coverage;
  - what season two changes, from SEASON.md's approved table plus the S0-2 verdict.
- `export_clip`'s rendering is now `render_best_match`, shared with the season clips. The
  weekly report's behaviour is unchanged.
- Test `test_season_report_draft` builds the report from the fabricated history and checks
  every section, the numbers and the absence of raw JSON.

Draft on the snapshot in out/ (7 nights): 12 house bots written, 12 alive, 4 rejected;
5,930 matches in 7 round-robins; 2,570 cache entries; 277,925 tokens; no unique coverage;
5 clips rendered, each ≤0.04 MB.

```
python3 -m colosseum.meta_report --season -> season report: wrote /srv/swarm-daily/out/meta/SEASON_1.md
python3 -m pytest tests -q -> 347 passed in 53.24s
```

## Build session 2026-10-04 (fifth) — hygiene

No alert, no WIP. Night 10-04 was ok (log: 2 bots written, 0 rejected, 835.8 s). The only open
in-scope item is L10, and its inputs (licence, repo name, visibility) are still with the
founder, so this session did hygiene only. L10's line in LAUNCH_STATUS.md now says what it's
waiting on.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status --porcelain --untracked-files=all -> nothing (no untracked files in the root)
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 53.71s (under the five-minute limit)
```

- The cache hit rate still can't be read: the out/ snapshot ends at night 10-04 (0 hits,
  explained above). Night 10-05 is the first warm night.
- Backup restore is still not checked: no allowed command reaches `~/backups`.

## Build session 2026-10-04 (sixth) — hygiene

No alert, no WIP. Night 10-04 was ok (log: 2 bots written, 0 rejected, 835.8 s). L10 is still
the only open in-scope item and still waits on the founder (licence, repo name, visibility;
LICENSE_NOTE.md still says "not chosen yet"), so this session did hygiene only. Nothing changed
since the fifth session; no code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status --ignored --short -> no untracked files; only ignored caches, out/ and SESSION_ITEM
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 53.17s (under the five-minute limit)
```

- Cache hit rate: still unreadable until night 10-05 (first warm night).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

## Build session 2026-10-04 (seventh) — hygiene

No alert, no WIP. Night 10-04 was ok (log: 2 bots written, 0 rejected, 835.8 s). L10 is still
the only open in-scope item and still waits on the founder (LICENSE_NOTE.md still says "not
chosen yet"; LAUNCH_STATUS has no repo name or visibility), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status -> working tree clean (no untracked files; SESSION_ITEM is ignored)
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 62.29s (under the five-minute limit)
```

- Cache hit rate: still unreadable until night 10-05 (first warm night).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Several sessions today have found nothing to do but hygiene. Until the founder answers L10,
  further build sessions add no value; worth pausing them or answering L10.

## Build session 2026-10-04 (eighth) — hygiene

No alert, no WIP. Night 10-04 still the latest (ok). L10 still waits on the founder
(LICENSE_NOTE.md "not chosen yet"; no repo name or visibility in LAUNCH_STATUS or
DECISIONS.local.md), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status --porcelain --untracked-files=all -> empty (no untracked files)
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 57.81s (under the five-minute limit)
```

- Cache hit rate: still unreadable until night 10-05 (first warm night).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Eighth hygiene-only session today. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-04 (ninth) — hygiene

No alert, no WIP. Night 10-04 still the latest (ok). L10 still waits on the founder
(LICENSE_NOTE.md "not chosen yet"; no repo name or visibility recorded), so hygiene only.
No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status --porcelain --untracked-files=all -> empty (no untracked files)
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 49.52s (under the five-minute limit)
```

- Cache hit rate: still unreadable until night 10-05 (first warm night).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Ninth hygiene-only session today. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 — hygiene

No alert, no WIP. The out/ snapshot still ends at night 10-04 (ok); out/nights.jsonl has no
2026-10-05 entry, so night 10-05 is not in this snapshot. L10 still waits on the founder
(LICENSE_NOTE.md "not chosen yet"; no repo name or visibility in LAUNCH_STATUS or
DECISIONS.local.md), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 194 MB"; last-night 2026-10-04: ok; alert none
git status --porcelain --untracked-files=all -> empty (no untracked files)
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 56.14s (under the five-minute limit)
```

- Cache hit rate: still unreadable; night 10-05 (first warm night) is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Tenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (second) — hygiene

No alert, no WIP. Night 10-05 is now in the snapshot: ok. L10 still waits on the founder
(LICENSE_NOTE.md "not chosen yet"; no repo name or visibility recorded), so hygiene only.
No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status --short --untracked-files=all -> empty (no untracked files)
WIP.md -> none in the worktree
out/nights.jsonl, night 10-05 -> status ok; cache {"matches": 1500, "ran": 100, "cached": 1400, "cache_entries": 2670, "seconds": 32.6}
python3 -m pytest tests -q -> 347 passed in 66.86s (under the five-minute limit)
```

- Cache hit rate, first warm night: 1400 of 1500 matches from the cache (93%); tournament
  32.6 s against 520.1 s on night 10-04 (0 cached, after the 3.9 engine-version bump).
- Night 10-05 rejected the attacker: "model returned no code block" (contrarian persona,
  evidence 3064/3500 tokens). Night status stays ok and nothing to fix in the pipeline; the
  raw response is not in this snapshot (out/house_raw has no 10-05 file), so I can't say
  why. If it repeats on contrarian nights, look at the raw output on the live host.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Eleventh hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (third) — hygiene

No alert, no WIP. L10 still waits on the founder (LICENSE_NOTE.md "not chosen yet"; no repo
name or visibility in LAUNCH_STATUS.md), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> nothing to commit, working tree clean
WIP.md -> none in the worktree
ls out/house_raw -> no such directory in the snapshot
python3 -m pytest tests -q -> 347 passed in 75.29s (under the five-minute limit)
```

- Night 10-05's rejected attacker ("model returned no code block") still can't be looked at:
  the snapshot has no out/house_raw. Check it on the live host.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Twelfth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (fourth) — hygiene

No alert, no WIP. L10 still waits on the founder (LICENSE_NOTE.md line 1 "Licence: not
chosen yet"; LAUNCH_STATUS.md L10 still "waiting on you: licence, repo name, visibility"),
so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status --porcelain --ignored -> nothing tracked or untracked to commit; only ignored caches, out/ and SESSION_ITEM
WIP.md -> none in the worktree
python3 -m pytest tests -q -> 347 passed in 72.04s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Thirteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (fifth) — hygiene

No alert, no WIP. L10 still waits on the founder (LICENSE_NOTE.md line 1 "Licence: not
chosen yet"), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> nothing to commit, working tree clean
ls WIP.md out/house_raw -> neither exists in the worktree
python3 -m pytest tests -q -> 347 passed in 67.58s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Fourteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (sixth) — hygiene

No alert, no WIP. L10 still waits on the founder (LICENSE_NOTE.md line 1 "Licence: not
chosen yet"; LAUNCH_STATUS.md L10 "waiting on you: licence, repo name, visibility"), so
hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status --porcelain -> empty (clean tree)
python3 -m pytest tests -q -> 347 passed in 67.28s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Fifteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (seventh) — hygiene

No alert, no WIP. L10 still waits on the founder (LAUNCH_STATUS.md L10 "waiting on you:
licence, repo name, visibility"; LICENSE_NOTE.md, DECISIONS.local.md and LAUNCH_STATUS.md
unchanged since commit 00065d2), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status --porcelain -> empty (clean tree)
ls WIP.md -> no such file
python3 -m pytest tests -q -> 347 passed in 68.50s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Sixteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (eighth) — hygiene

No alert, no WIP. L10 still waits on the founder (LAUNCH_STATUS.md L10 "waiting on you:
licence, repo name, visibility"; LICENSE_NOTE.md, DECISIONS.local.md and LAUNCH_STATUS.md
unchanged since commit 00065d2), so hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 60.15s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Seventeenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (ninth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing, so no answer has landed. Hygiene only.
No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> clean tree at start
git status --ignored -> only caches, out/ and SESSION_ITEM; no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 58.15s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Eighteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-05 (tenth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 53.46s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Nineteenth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 199 MB"; last-night 2026-10-05: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 62.53s (under the five-minute limit)
```

- Night 10-06 is not in this session's snapshot: out/nights.jsonl has no 2026-10-06 line and
  health reports last-night 2026-10-05. Its status is unknown from here; check it on the live host.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twentieth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (second) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 72.39s (under the five-minute limit)
```

- Night 10-06 is now in the snapshot and ok (league log: 2 accepted, 0 rejected, 1760 matches,
  260 run, 1500 cached, 93.0 s; 25,421 tokens). The earlier "check on the live host" note is closed.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-first hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (third) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 71.04s (under the five-minute limit)
ls out/house_raw -> "No such file or directory" (raw generator output is not in the snapshot)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker (raw output was 295 chars, "no code block"): out/house_raw is
  not in the snapshot, so still only checkable on the live host.
- Twenty-second hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (fourth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 69.82s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-third hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (fifth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 73.63s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-fourth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (sixth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 66.15s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-fifth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (seventh) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 66.72s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-sixth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (eighth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 69.00s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-seventh hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (ninth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 52.85s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-eighth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-06 (tenth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 54.52s (under the five-minute limit)
```

- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Twenty-ninth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 215 MB"; last-night 2026-10-06: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 64.93s (under the five-minute limit)
```

- Night 10-07: the snapshot in out/ has no record of it (health reports last night as
  2026-10-06; no `*.log` under out/ mentions 2026-10-07). Its status is unknown from here.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Night 10-05's rejected attacker: still only checkable on the live host.
- Thirtieth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (second) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 74.70s (under the five-minute limit)
```

- Night 10-07: ok (league log). One defender accepted (`deadline_cluster_ledger`, rank 4,
  Elo 1099.3); the attacker (counter_meta vs `convergence_blast_scheduler`) was rejected,
  "model returned no code block", with a 403-char raw response.
- Pattern: this is the second short no-code reply in three nights, and both targeted
  `convergence_blast_scheduler` (10-05: contrarian, 295 chars). `out/house_raw` is not in the
  snapshot, so I can't tell whether these are refusals or format slips. The two raw files need
  reading on the live host: `2026-10-05T033210_cli_attacker_contrarian.md` and
  `2026-10-07T033125_cli_attacker_counter_meta.md`. Under the safety-stop rule, the prompt is
  not to be reworded to get past a refusal.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-first hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (third) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own)
python3 -m pytest tests -q -> 347 passed in 70.04s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  are still unread: `ls out/house_raw` -> "No such file or directory" in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-second hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (fourth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD -- LICENSE_NOTE.md
DECISIONS.local.md LAUNCH_STATUS.md` printed only e43df39, the previous session's own status
line. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own)
python3 -m pytest tests -q -> 347 passed in 65.30s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  are still unread: `ls out/house_raw` -> "No such file or directory" in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-third hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (fifth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own)
python3 -m pytest tests -q -> 347 passed in 67.44s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  are still unread: `ls out/house_raw` -> "No such file or directory" in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-fourth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (sixth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls -la (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own)
python3 -m pytest tests -q -> 347 passed in 62.29s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  are still unread: `ls out/house_raw` -> "No such file or directory" in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-fifth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (seventh) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls -a (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own)
python3 -m pytest tests -q -> 347 passed in 64.74s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  are still unread: `out/house_raw` is not in the snapshot (`ls out` doesn't list it).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-sixth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (eighth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own, gitignored)
python3 -m pytest tests -q -> 347 passed in 68.84s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  still can't be read: `out/house_raw` is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-seventh hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (ninth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own, gitignored)
python3 -m pytest tests -q -> 347 passed in 56.05s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  still can't be read: `out/house_raw` is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-eighth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-07 (tenth) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files (SESSION_ITEM is this session's own, gitignored)
ls out/house_raw -> "No such file or directory" (not in the snapshot)
python3 -m pytest tests -q -> 347 passed in 51.85s (under the five-minute limit)
```

- No new night since the last session; night 10-07 was ok.
- The two short no-code attacker replies (10-05, 10-07, both vs `convergence_blast_scheduler`)
  still can't be read: `out/house_raw` is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Thirty-ninth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-08 — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 00065d2..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 221 MB"; last-night 2026-10-07: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
wc -l out/nights.jsonl -> 11; grep 2026-10-08 in it -> no matches
python3 -m pytest tests -q -> 347 passed in 65.95s (under the five-minute limit)
```

- No night 2026-10-08 in the snapshot. Health reports last-night 2026-10-07 as ok and
  no alert, so this session can't tell whether tonight's run hasn't been copied yet or
  didn't happen. Worth checking `out/nights.jsonl` on the live host.
- The two short no-code attacker replies (10-05, 10-07) still can't be read: `out/house_raw`
  is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Fortieth hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Build session 2026-10-08 (second) — hygiene

No alert, no WIP. L10 still waits on the founder: `git log 604562d..HEAD --oneline --
LICENSE_NOTE.md DECISIONS.local.md LAUNCH_STATUS.md` printed nothing. Hygiene only. No code touched.

```
python3 -m colosseum.health -> all six ok; disk "23% used, 160 GB free, out/ is 236 MB"; last-night 2026-10-08: ok; alert none
git status -> clean tree at start
ls (repo root) -> no WIP.md, no stray files
python3 -m pytest tests -q -> 347 passed in 71.99s (under the five-minute limit)
```

- Night 2026-10-08 is now in the snapshot and was ok (league log): 2 bots accepted, 0 rejected,
  33,628 tokens, 2160 matches (290 in the sandbox, 1870 from the cache) in 127.2 s, night 454.2 s.
  `2026-10-08_defender_hover_bank_late_binder` (contrarian) entered at defender rank 2;
  `2026-10-08_attacker_staggered_trishell_blast_denial` (generalist) at attacker rank 5.
  Tops unchanged: `synchronized_ring` and `convergence_blast_scheduler`.
- The two short no-code attacker replies (10-05, 10-07) still can't be read: `out/house_raw`
  is not in the snapshot.
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Forty-first hygiene-only session in a row. Same recommendation: pause build sessions or answer L10.

## Session 10 — final sprint run (2026-10-08, deadline 03:00 UTC 10-09)

Build sessions paused for this run (DECISIONS.local.md); restored after L16.

### Licences ✅
Apache-2.0 for code (`LICENSE`, the official text), CC BY 4.0 for replays, results and research
(`LICENSE-CC-BY-4.0`, the official legal code). `LICENSING.md` maps folders to licences;
README, CONTRIBUTING, SUBMITTING, `CITATION.cff` (both ids) and a footer on every site page
match. `LICENSE_NOTE.md` removed. The content check now ignores licence ids such as CC-BY-4.0.

### L10 publish pipeline, dry ✅
`scripts/publish.sh [--live] [--site DIR] REMOTE [DEPLOY_KEY]`: rewrite identities in a fresh
mirror → audit the rewritten history (any finding aborts) → build the site → push `master` to
`main`, fast-forward only → the site as one orphan commit, force-pushed to `gh-pages` (the
project's one force push: a generated branch, never master). Non-local remotes are refused
without `--live`.

```
$ python3 -m pytest tests/test_publish.py -q     # local bare remote only
3 passed   # rewritten main (no root@), gh-pages = one commit with .nojekyll;
           # republishing leaves main at the same hash (deterministic rewrite);
           # git@github.com:... refused without --live
```
Launch-day steps (create repo, deploy key, publish, Pages) are in LAUNCH_CHECKLIST.md 4–7.

### L13 one-page summary ✅
`research/00_summary.md` (520 words): what it is, why, what the league does nightly, three headline results with links, honest limits, what is next. Content check clean on all five research pages; the site renders it as `research/00_summary.html`. Figures as of night 11 (2026-10-08).

### L14 season report draft, kept current ✅
The session-built draft (`meta_report --season`) was frozen at night 7: nothing reran it. `ops after-night` now rewrites `reports/SEASON_1.md` every night and commits it (pathspec, league author). It is a marked draft until night 28 and the finished report, with clips, on the boundary night, so it completes itself. Scratch after-night: exit 0, `season report: written (11 of 28 nights)`. 353 tests.

### L15 full rehearsal on a scratch clone ✅

`scripts/rehearse.sh SCRATCH [SCREENS]`: every step logged ok/FAIL, a failure doesn't stop
the rest, and nothing is pushed anywhere (the publish target is a bare repo in the scratch dir).

```
ok   clone 0s
ok   reproduce 1000s        REPRODUCED in 999 s (byte-identical, 2,160 matches)
ok   tournament 1112s       cold, sandboxed, populates the clone's out/
ok   library 3s
ok   site 9s
ok   pr_good 0s             submit_pr check passes a bot in the author's own folder
ok   pr_bad_is_refused 0s   a PR touching colosseum/sim.py fails the check
ok   intake 1s              ACCEPTED -> bots/submitted/defender/rehearsal__rehearsal_closest.py
ok   publish 19s            local bare remote: main ef8181c, gh-pages 85ad546
ok   screenshots 50s        56 pages at 390 px, dark mode, in out/launch_screens/
rehearsal: 0 failed step(s)   (real 36m34s)
```
No manual fix was needed. Screenshots cover every page except the 2,160 replay pages, plus
three of them (DECISIONS.local.md). Checked by eye: home and the one-page summary read well
at phone width. **Found:** the README and summary said `make reproduce` takes ~6 min; at
night 11 it takes ~17, and the time grows with the roster. Both now say so.

### L16 reports/LAUNCH_READY.md ✅ — launch sprint complete

15 lines: what is ready, the six screenshots to look at, the founder's decisions (licence and
repo done, domain open, default github.io), the four launch-day actions in order, and five gaps:
- submissions closed until 3.8;
- the PR workflow not yet run on GitHub;
- the 143 MB site;
- no link back from replay pages;
- the persona result preliminary.

Also fixed from the L15 screenshots: nested Markdown lists now render as sub-lists
(SUBMITTING's "game in one minute"), and submitting.png was re-shot. All 16 sprint items are
done on sprint day 5. Build sessions are restored in cron (paused for the sprint since 06:0x).

### Build session 2026-10-08 (after L16): hygiene
Every in-scope sprint item (L5-L10, L12, L14) is done in LAUNCH_STATUS.md, so hygiene only.
No code changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 79.52 s.
- Tree clean at start, no WIP.md, no untracked files in the root.
- Still open with the founder: ROADMAP.md line 30 still mentions "a paid API" (raised with 3.12).

### Build session 2026-10-08 (second after L16): hygiene
In-scope items L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene
only. No code changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 95.41 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Same recommendation: pause build sessions until 3.4 opens after night 10-11.

### Build session 2026-10-08 (third after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 83.08 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Third empty session today: pausing build sessions until night 10-11 is still recommended.

### Build session 2026-10-08 (fourth after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 75.62 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Fourth empty session today. Each one adds only a commit; pausing build sessions until night
  10-11 (when 3.4 opens) is the founder's call and is recommended again.

### Build session 2026-10-08 (fifth after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 77.82 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Fifth empty session today. Pausing build sessions until night 10-11 is recommended again.

### Build session 2026-10-08 (sixth after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 74.79 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Sixth empty session today. Pausing build sessions until night 10-11 is recommended again.

### Build session 2026-10-08 (seventh after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 69.35 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Seventh empty session today. Pausing build sessions until night 10-11 is recommended again.

### Build session 2026-10-08 (eighth after L16): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 66.96 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Eighth empty session today. Pausing build sessions until night 10-11 is recommended again.

### Build session 2026-10-09 (first of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed; LAUNCH_STATUS.md header moved to sprint day 6.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 236 MB, last-night 2026-10-08 ok, alert none). The out/ snapshot has no night
  10-09 yet; health reports 10-08 as the last night.
- `python3 -m pytest tests -q`: 353 passed in 78.62 s.
- Tree clean at start, no WIP.md, no stray files in the root (`git status --ignored`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.
- Ninth empty session in a row. Pausing build sessions until night 10-11 is recommended again.

### Build session 2026-10-09 (second of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. LAUNCH_STATUS L14 line now says 12 of 28, which matches commit 766f9da.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 84.32 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Night 10-09 (league log): 2 bots accepted, 89,491 tokens (under the 150k trigger),
  tournament 129.3 s, **night 1100.6 s, over the 15-minute runtime line**. The tournament
  was not the cause. The cause was one generator call (contrarian attacker): 889.2 s,
  out=58,858 tokens, and the model field reads `claude-opus-5-5,claude-opus-4-8`. The charter's
  runtime remedy is to cut seeds, and that would not touch the generator call, so I left the
  seeds alone. Changing the generator is outside this sprint's scope, so this is written up,
  not fixed. If it happens again, an interactive session should look at a per-call time cap
  and at why a second model shows up.
- The same night's attacker file is named `2026-10-09_attacker_attacker_blast_isolated_synchronized_rel.py`.
  "attacker" appears twice and the name looks cut off at the end. This is cosmetic and the bot
  was accepted. The naming code is outside scope, so I'm only noting it here.
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (third of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (out/ still ends at night 10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 88.55 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Night 10-09's over-15-minute run (one 889 s generator call) is already written up above;
  nothing new to add.
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (fourth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 72.12 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (fifth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 81.98 s.
- Tree clean at start, no WIP.md, no stray files in the root (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (sixth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 87.97 s.
- Tree clean at start (`git status --short` empty), no WIP.md.
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (seventh of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 74.62 s.
- Tree clean at start, no WIP.md, no out/ALERT.md (`ls`); `git status --ignored` shows only
  caches, out/ and SESSION_ITEM, all ignored.
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (eighth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 159 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 79.61 s.
- Tree clean at start (`git status`), no WIP.md, no ALERT.md in out/ (`ls out`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (ninth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 158 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 72.05 s.
- Tree clean at start (`git status`), no WIP.md, no out/ALERT.md (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-09 (tenth of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. No new night since the second session (health still reports last night 2026-10-09).
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 158 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 66.57 s.
- Tree clean at start (`git status`), no WIP.md at the root, no ALERT.md in out/ (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Build session 2026-10-10 (first of the day): hygiene
L5-L10, L12, L14 are all done in LAUNCH_STATUS.md. No alert, no WIP, so hygiene only. No code
changed. Night 10-10 is not in the snapshot: health still reports last night 2026-10-09.
- `python3 -m colosseum.health`: all six ok (docker, cli-login, cron, disk 23% used / 158 GB
  free / out/ 250 MB, last-night 2026-10-09 ok, alert none).
- `python3 -m pytest tests -q`: 353 passed in 77.87 s.
- Tree clean at start (`git status`), no WIP.md at the root, no ALERT.md in out/ (`ls`).
- Backup restore: still not checked; no allowed command reaches `~/backups`.

### Launch, 2026-10-10: approved, blocked at "the repo exists"

The founder approved the launch in writing. `goel12133/swarm-colosseum` returns 404 (to the
owner's own login) and there is no deploy key on the box, so nothing was pushed. Done anyway:
- **Leak scan of what would be published.** `publish.sh` was run to a local bare remote and
  every commit identity, message and blob on main + gh-pages was scanned for the hostname, the
  personal email, private keys and token shapes. Clean: identities are only the noreply
  address, dev@…invalid and league@localhost; the `sk-ant-` hits are a 22-character test
  fixture and a 12-character placeholder.
- **Nightly republish** (`ops.publish_step`, after the site step): not armed until the deploy
  key exists; refuses and alerts if the public main moved without us. 3 tests on a local bare
  remote; the after-night test now stubs it so a test can never push.
- **Submissions open 2026-10-24** on SUBMITTING, ABOUT, README and the summary; 3.8 is
  scheduled for that evening, and opening depends on it.

### 3.5 Optimiser ablation ✅ — and the preliminary L4 result revised

`scripts/ablation_annealing.py` (3 tests) pairs `annealed_assignment` against
`greedy_value_model` by attacker and seed from the result cache (current engine and rules
only), adds the nightly ladder series, and with `--timing N` times each defender `act()`
round trip in the sandbox. Run on 2026-10-10 after the night (11 nights, 14 attackers, 140
pairs):
- the optimiser is ahead against 9 attackers, greedy against 1, and 4 are level (sign test
  p = 0.02);
- mean paired difference +0.037, 95% bootstrap over attackers −0.038 to +0.106;
- greatest differences: interleaved_shell_ring +0.27 and depth_shell_saturation −0.34 (the
  optimiser was breached 10 of 10 times, greedy 3);
- ladder on 10-10: #4 against #16;
- median time per tick 0.87 against 0.64 ms.

**The four-night L4 cut said "adds no reliable value". That was too strong, and it is
revised** in research/04, the one-page summary (headline 3), the season report line and
LAUNCH_STATUS. The new verdict is a small, uneven gain that isn't robust. Full tables are in
`ANALYSIS_annealing.md`.

### Launch ✅ — 2026-10-10 04:37 UTC, https://pelennor.tech

- **First publish:** the founder created `goel12133/swarm-colosseum` (public, empty) and the
  deploy key. `python3 -m colosseum.ops publish` pushed main `dfa3668` and gh-pages `4ba87cb`
  in 41 s and recorded both in `out/publish.json`.
- **Pages:** it switched itself on with the gh-pages push. Custom domain `pelennor.tech`
  (every build writes `CNAME`); the certificate was approved and HTTPS enforced.
- **Leak rescan of a fresh public clone:** clean (168 commits, 3,491 file versions; the
  personal address is in 0 of them).
- **Test PR #1** (one workshop bot under `bots/submitted/pr/goel12133/`): `static-check`
  green in 9 s, then closed unmerged and its branch deleted.
- **Nightly republish:** armed from tonight.

reports/LAUNCH_DONE.md has the URLs, the first-night checklist and what didn't go to plan.

### Site trim ✅ — 191.0 MB → 20.5 MB

- **The rule** (`site.full_page_stems`): a full replay page for every match first played
  this season week or last, plus each live bot's best and worst match by its own score.
  Every other match is data only, opened on demand by the one shared viewer
  (`replays/viewer.html?r=data/<stem>.json.gz`). `replays.html` links each match to its
  page or the viewer, and to its data file.
- **Packed replays** (`colosseum/replay_pack.py`): positions are stored as per-id deltas in
  0.1 u, then gzipped. A replay is 5.2 KB on average instead of 54 KB, and it unpacks value
  for value. That was checked on all 2,900 replays in Python; the browser's decoder matches
  on 267,062 values; and a node test covers it.
- **Full pages** now carry the site nav (which also closes the LAUNCH_READY gap of replay
  pages having no way back to the site) and load the packed file into the viewer.
- **Size:** today all 2,800 matches are in weeks 1–2, so all have pages (4.2 MB of pages,
  14.7 MB of data). The rule keeps 1,432 of today's matches on 10-12 and 62 from 10-19.
  Projected size at the boundary is ~39 MB. After-night alerts above 60 MB.
- **Tests:** the rule, round-trips, the JS decoder, and every index and `?r=` link
  resolving. 371 pass.

### Fold-back of merged PRs ✅ built, switched off until 3.8

`colosseum/foldback.py` is called by `ops.publish_step` when public main has moved and
`FOLDBACK_ENABLED` is set (it ships `False`). It:
1. fetches public main into a scratch repo;
2. reviews every commit since our last publish, merges included, and rejects the whole
   batch if any path is outside `bots/submitted/pr/<handle>/<NAME>.py` (or is a symlink or
   executable, or the history was rewritten);
3. writes the net change into master on a `foldback-<sha>` branch;
4. runs the full suite, then fast-forwards master.

Then `publish.sh --merge-onto <public main>` publishes a merge commit, so main only grows.
Five tests drive it against a local bare remote with a fake contributor and a fake merge.
They cover:
- the happy path, including a second night;
- a PR that also touches `colosseum/sim.py` (rejected, nothing applied, nothing pushed);
- failing tests (master untouched, branch kept);
- the path rule (8 cases);
- that it ships switched off.

383 tests pass.

### P4 Season boundary: armed for 2026-10-26

- **`colosseum/boundary.py`** runs from `scripts/nightly.sh` before the league, from the
  first night of the next season. It:
  1. writes the final season report;
  2. freezes `seasons/S1/` (ladders, matrix, breaches, BALANCE, SEASON, meta reports and
     clips, the season report, every bot's source and metadata);
  3. merges branch `season2`;
  4. runs the full suite;
  5. fast-forwards master.

  Any failure leaves master alone and skips that night's league with an alert. 6 tests on
  a scratch clone.
- **Branch `season2`** is current master, plus candidate A, plus SEASON = 1 everywhere a
  replay or a ladder records the season, plus season two's dates in season.py and
  SEASON.md. 392 tests pass on it.
- **Rehearsal of season two's first night** (one seed, sandboxed): 280 matches, no
  zero-score bot. Top attacker synchronized_ring (1103), top defender
  class_gated_magazine_keeper (1033).
- **Health check `boundary`:** `season2` still merges cleanly into master (dry
  `git merge-tree`). `colosseum/tournament.py` is now protected from build sessions too,
  since `season2` changes it.
- **Season-generic fixes:** the season report's name and its "what changes next" section
  follow `season.NUMBER`, and three tests no longer assume season one.

### 2026-10-10 build session (post-launch): hygiene

- **Gates:** P5 is not open (no `out/ablation_14/done`). W is not open either: `out/meta/`
  has only WEEK_1, so there is no week-2 meta report yet. 3.13 and 3.14 are not due. That
  leaves hygiene.
- **health:** all six ok. Last night 2026-10-10 ok; disk 24% used, 158 GB free, out/ 274 MB.
- **Night 10-10 (log):** 2 bots accepted, 30,465 tokens, 337.4 s; 2,800 matches, 330 run,
  2,470 from the cache. The top attacker is now `2026-10-04_attacker_interleaved_shell_ring`,
  and the top defender is still `convergence_blast_scheduler`.
- **Tests:** 391 pass in 167.65 s, up from 353 in 77.87 s. A `--durations=8` rerun (391 pass,
  160.27 s) shows the publish/ops/fold-back tests, which use local bare remotes, take most of
  the time. The eight slowest add up to about 97 s, led by
  `test_site.py::test_the_build_writes_the_custom_domain_cname` at 20.08 s. The suite is
  under the 5-minute line, so no tests were marked slow.
- Clean tree, no WIP.md, no alert. No code changed. The backup restore still needs an
  interactive session.

**06:10, lead engineer:** the 06:00 session's rebase conflicted in PROGRESS.md, because
both sides appended (my P4 entries landed while it ran). I resolved it by keeping both,
ran the suite on daily-wip (392 pass) and fast-forwarded master, so the next session
starts fresh. out/ALERT.md, which records it, clears after the next good night.
LAUNCH_STATUS no longer says "Nothing is public".

### 2026-10-10 build session (post-launch, second): hygiene

- **Alert written up:** the session prompt's out/ALERT.md (2026-10-10T06:06:33) records the
  06:00 session's rebase conflict in PROGRESS.md. Cause: the session and the lead engineer
  both appended to PROGRESS.md. It was already resolved on master in 65983ac; nothing left
  to fix in scope. Any lasting fix (e.g. per-session progress files) would be in the
  wrapper, `colosseum/daily.py`, which is protected, so it is not attempted here. The
  snapshot `out/` has no ALERT.md, and `health` printed `alert none`.
- **Gates:** P5 is not open (no `out/ablation_14/`). W is not open (`out/meta/` holds only
  WEEK_1 and SEASON_1). 3.13 and 3.14 are not due.
- **health:** all seven checks ok (docker, cli-login, cron, disk 24% used / 158 GB free /
  out/ 274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 392 pass in 185.39 s. Under 5 minutes, so no tests marked slow; it has risen
  from 167.65 s this morning, so it is worth watching.
- Clean tree, no WIP.md. No code changed. The backup restore still needs an interactive
  session.

### Design pass ✅ — the founder's reference design, built from live data

- **What changed:**
  - `colosseum/site_assets/style.css`: the reference's theme block and components, plus
    rules for rendered Markdown.
  - `site.js`, and the self-hosted fonts in `assets/fonts/`.
  - The page chrome: header with the REPLAY indicator, nav with a More menu on phone,
    footer with a theme button.
- **Pages:**
  - Home: the replay channel in the broadcast frame with its overlays, the numbers strip,
    ladders with movement arrows and "new" tags, last night's recap, result cards, three
    doors, the season strip.
  - Ladders: sortable, with CER, matches, kind and first night.
  - Bot pages: head, figures, head to head, best and worst match, source.
  - Replay pages, the research index and articles, a new changelog, and submit (with
    "Build with us" from CONTRIBUTING).
- **Viewer** (`viewer/template.html`) restyled to the reference: 16:9 stage, overlays,
  scrub marks, a match sheet, key moments, share. It has three modes: full, embed, and
  broadcast (the channel). The clip path is unchanged, and the clip tests pass.
- **Real data everywhere:** rank movement from `out/history`, the recap and changelog from
  `out/nights.jsonl`, research status and dates from the files and git.
- **Light mode** follows the system, or the toggle. **Reduced motion:** nothing animates,
  and the channel waits for a click.
- **Tests:** 7 new site tests (fonts local, no outside requests, light and reduced-motion
  rules, nothing claims LIVE, channel replays exist, movement, recap, changelog); 399
  pass. 25.9 MB. Screenshots: `out/design_pass/before/` (22) and `after/` (25).

### 2026-10-10 build session (post-launch, third): hygiene

- **Alert:** the session prompt's out/ALERT.md is still the 06:06 rebase conflict on
  PROGRESS.md. It was resolved on master in 65983ac and written up by the second session.
  Nothing new to fix, and the lasting fix is in the protected wrapper. `health` printed
  `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14` says no such directory). W is not open
  (`out/meta/` holds only WEEK_1 and SEASON_1, plus clips). 3.13 and 3.14 are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 177.60 s (7 more from the design pass). Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, fourth): hygiene

- **Alert:** the session prompt's out/ALERT.md is still the 06:06 PROGRESS.md rebase
  conflict. It was resolved in 65983ac and written up earlier, so there is nothing new.
  `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14` says no such directory). W is not open
  (`out/meta/` holds WEEK_1 and SEASON_1 plus clips, but no week-2 report). 3.13 and 3.14
  are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 170.24 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, fifth): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 06:06 PROGRESS.md rebase
  conflict. It was resolved in 65983ac and written up earlier, so there is nothing new.
  `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14` says no such directory). W is not open
  (`out/meta/` holds WEEK_1 and SEASON_1 plus clips, but no week-2 report). 3.13 and 3.14
  are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 176.13 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, sixth): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 06:06 PROGRESS.md rebase
  conflict, already resolved in 65983ac and written up; `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14`: no such directory). W is not open
  (`out/meta/` holds WEEK_1 and SEASON_1 plus clips, no week-2 report). 3.13 and 3.14
  are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 177.07 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, seventh): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 06:06 PROGRESS.md rebase
  conflict, already resolved in 65983ac and written up; `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14`: no such directory). W is not open
  (`ls out/meta`: SEASON_1.md, WEEK_1.md, two WEEK_1 clips, clips.json; no week-2 report).
  3.13 and 3.14 are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 157.34 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, eighth): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 06:06 PROGRESS.md rebase
  conflict, already resolved in 65983ac and written up; `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14`: no such directory). W is not open
  (`ls out/meta`: SEASON_1.md, WEEK_1.md, two WEEK_1 clips, clips.json; no week-2 report).
  3.13 and 3.14 are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 156.97 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### 2026-10-10 build session (post-launch, ninth): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 06:06 PROGRESS.md rebase
  conflict, already resolved in 65983ac and written up; `health` printed `alert none`.
- **Gates:** P5 is not open (`ls out/ablation_14`: no such directory). W is not open
  (`ls out/meta`: SEASON_1.md, WEEK_1.md, two WEEK_1 clips, clips.json; no week-2 report).
  3.13 and 3.14 are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 152.38 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session. No in-scope gate can open before night 10-11, so
  the remaining sessions today will also be hygiene only.

### 2026-10-11 build session (post-launch, first): hygiene

- **Alert:** the session prompt's out/ALERT.md still shows the 2026-10-10 06:06 PROGRESS.md
  rebase conflict, already resolved in 65983ac and written up; `health` printed `alert none`.
- **Snapshot:** out/ was copied at 2026-10-11 00:00, before night 10-11 ran; `health`
  reports last-night 2026-10-10 ok.
- **Gates:** P5 is not open (`ls out/ablation_14`: no such directory). W is not open
  (`ls out/meta`: SEASON_1.md, WEEK_1.md, two WEEK_1 clips, clips.json; no week-2 report).
  3.13 and 3.14 are not due.
- **health:** all seven ok (docker, cli-login, cron, disk 24% used / 158 GB free / out/
  274 MB, last-night 2026-10-10 ok, alert none, boundary: season2 merges cleanly).
- **Tests:** 399 pass in 164.29 s. Under 5 minutes.
- The tree was clean at the start, with no WIP.md. No code changed. The backup restore
  still needs an interactive session.

### SPEC-4 — stopped (safety classifier), 2026-10-11

My response to the SPEC-4 brief was stopped by a safety classifier. Under the standing
safety-stop rule, the item is stopped and written up, not rephrased; nothing from it was
built. See DECISIONS.local.md.

### Products brief — stopped (safety classifier), 2026-10-11

My response to the products brief was stopped by a safety classifier. Under the standing
safety-stop rule, the item is stopped and written up, not rephrased; nothing from it was
built. See DECISIONS.local.md.

### 2026-10-11 build session (post-launch, second): W

- **Alert:** out/ALERT.md none. Snapshot includes night 10-11 (league log: ok, 2 bots
  accepted, 33,764 tokens, 347.1 s; 3,150 matches, 350 run, 2,800 from the cache).
- **Gate:** W is open (`ls out/meta` shows WEEK_2.md). P5 is still closed (`ls out/ablation_14`:
  no such directory). 3.13 and 3.14 are not due.
- **W:** wrote `reports/FOUNDER_WEEK_2.md` (10 lines plus the week's safety stops). Sources:
  out/meta/WEEK_2.md (tops, personas verbatim, tokens 283,487 week / 561,412 season, cache
  89%, health), out/BALANCE.md (defenders 2113/3150 = 67%), the league log (ablation calls
  10-11 05:01–05:15, 9 calls, 119,523 tokens summed), DECISIONS.local.md (stops). Build-session
  token totals are not in the snapshot, and the report says so.
- **Finding for the founder:** the S0-3 watch closed as a meta, but the defender lean grew
  from 61.6% to 67%. That's asked as a yes/no in the report. Nothing is acted on.
- **Tests:** 399 pass in 191.68 s. Under 5 minutes.
- No code changed. BACKLOG W line and LAUNCH_STATUS updated.
