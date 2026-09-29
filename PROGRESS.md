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
