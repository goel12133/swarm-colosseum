# Decisions taken alone (charter section 1), with the reason

- **2026-10-03 — cache key uses the rules actually in force, not `rules.py`'s bytes.** Key =
  (attacker sha256, defender sha256, seed, sha256 of the canonical JSON of the Rules object
  passed to the match, engine version). Season-two candidates pass tuned Rules objects that
  never touch `rules.py`, so a file hash would serve season-one results to a candidate run.
  Engine version = sha256 over sim.py, policy.py, sandbox.py and sandbox_runner.py.
- **2026-10-03 — the daily session's allow-list has no raw `docker`.** `docker run -v /:/host`
  is root on the box, which would make the "never touch /etc" guardrail meaningless. The
  project's own commands (tournament, submit, clip) still use the sandbox internally.
- **2026-10-03 — rotation keeps every replay of the current roster.** With a cache, a pairing
  that doesn't rerun never rewrites its replay, so a 14-day mtime rule would delete the only
  replay of a live matchup.
- **2026-10-03 — contrarian's "number one" is its target, the opposing #1.** Charter 3.2 says the contrarian sees "the number one's source and nothing else"; its target was already the opposing #1, so that's the source it gets. Its goal no longer says "unlike the bots described above", since it sees none.
- **2026-10-03 — what the daily session's 200k token cap counts.** New input + cache writes + output, the same things a league call consists of. An agentic session re-reads its own context every turn; counting those cache reads would put a 2-hour session in the millions and trip the cap on day one for arithmetic, not use. They are recorded (`tokens_incl_cache_reads`), not capped. `--max-budget-usd 5` (notional, not billed) is the in-session runaway backstop.
- **2026-10-03 (daily session) — the tactic library is written to `out/library/`, not a
  tracked `library/`.** It is derived from league data (ladders, breach tables, replays) and
  goes stale every night, and its replay links point into `out/replays/`. It sits beside
  `out/site/` and is rebuilt the same way, never committed. `--out` takes any path.
- **2026-10-03 (daily session) — who gets a tactic card.** Top five of its ladder on any
  night in `out/history/` or on the current ladder, or unique coverage (`unique_coverage`)
  in the latest breach table. "Beats" means it wins more than half the seeds against that
  opponent on the last night it played; "beaten by" means it wins fewer than half. Best and
  worst replay come only from pairings in the current roster, so dry-run and retired
  opponents never appear.
- **2026-10-03 (daily session) — tactic families, from what season one actually produced.**
  Attackers: saturation, synchronised arrival, decoy screening, trickle. Defenders: identify
  first, patient defence (blast packing), budgeted defence, value-model optimisation,
  controls. They're a hand-kept table in `colosseum/library.py`. A new bot goes to
  "Unsorted" until someone places it there; the index says so. A test checks that every
  member is a real bot on its own side and sits in only one family.
