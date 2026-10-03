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
