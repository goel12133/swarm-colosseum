# Daily — 2026-10-10 (post-launch build session: hygiene)

**Night 10-10:** ok. 2 bots accepted, 30,465 tokens, 337.4 s (2,470 of 2,800 matches
from the cache). New top attacker: `interleaved_shell_ring`. Top defender is still
`convergence_blast_scheduler`.
**Alert:** none.
**Done:** hygiene only. No code changed.
- health: all six ok; disk 24% used, out/ 274 MB.
- 391 tests pass in 167.65 s (yesterday 77.87 s). The publish/fold-back tests account for
  most of the rise. Still under 5 min, so no tests marked slow.

**Next:** W once the week-2 meta report is written (after night 10-11). P5 once
`out/ablation_14/done` exists. 3.13 after night 11-01. 3.14 after 3.8 and the boundary.
**Waiting on you:** ROADMAP line 30 ("a paid API"); a per-call time cap for slow generator
calls (889 s on 10-09); the cut-off "attacker_attacker" bot name. The last two are out of scope.
**Open stops:** 3.8 is held for the interactive run on 10-24, so submissions stay closed.
The backup restore needs an interactive session.
