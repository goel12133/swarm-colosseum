# Daily — 2026-10-03 (build session, 3.11)

**Night:** 10-03 ok. 1,170 matches in 352.8 s, 54,667 tokens. Two bots accepted, none
rejected. Tops: synchronized_ring (attacker), convergence_blast_scheduler (defender).
**Alert:** none.
**Done:** 3.11 workshop kit in `workshop/`: a 90-min lesson plan, a one-page facilitator
guide, 3 starter bots per side, and 5 exercises from "turn the gun on" to "beat
identify_then_engage on every seed". It runs offline with no Docker and only loads the
student's own file, checked against the arena's rules. `make workshop` confirms that
every exercise can be solved. That check ran through the test suite (the session can't
run `make`). 293 tests pass.
**Not checked yet:** a run on a real Python 3.11 / Windows laptop. Do one before the day.
**Heads-up:** the engine changed with 3.9, so tonight's tournament runs cold.
**Next:** 3.12 scoping (2 pages, game only). 3.5 opens after night 10-05.
**Open stops:** G (generator prompt) is waiting on your text. 3.8 is held for an
interactive run with you.
