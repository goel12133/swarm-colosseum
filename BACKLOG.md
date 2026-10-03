# Backlog

Standing rule (2026-10-03): an item or output that trips a safety stop is stopped, written up
with its flag, and left; it is never rephrased to get past the stop.

From the operating charter, section 3, in order. Status: todo / doing / done / blocked.

| # | item | status | note |
|---|---|---|---|
| 3.1 | Match result cache | done | cold 372 s → warm 0.0 s; nightly 65 s with two new bots |
| 3.2 | Generator token discipline | done | prompts −15..−73%; budgets in .meta.json |
| 3.3 | Daily engineering session (manual run first, then cron) | done | first run watched 2026-10-03; cron 05:00 UTC from 2026-10-04 |
| 3.4 | Persona ablation (after 14 real nights) | waiting | not before night 2026-10-11 |
| 3.5 | Optimiser ablation (after 7 nights of greedy_value_model) | waiting | not before night 2026-10-05 |
| 3.6 | Season report | waiting | at the boundary, 2026-10-26 |
| 3.7 | Tactic library export | done | 20 cards, 9 families; writes out/library/; nightly rebuild comes with 3.10 |
| 3.8 | Sandbox hardening and validator testing (defensive, inert inputs) + SECURITY.md | doing | rewritten 2026-10-03; lead engineer -- the daily session must not pick this |
| 3.9 | Engine fuzzing and invariants | done | stdlib fuzzer; 10,000 trajectories, 0 failures; 500 nightly in after-night; found + fixed a non-finite-number crash (SECURITY, PROGRESS) |
| 3.10 | Site bundle kept current + about page | todo | |
| 3.11 | Workshop kit | todo | |
| 3.12 | Higher-fidelity engine scoping, for the game (2 pages, abstract, no transfer claims) | todo | rewritten 2026-10-03 |
| 3.13 | Season two first week | todo | after 2026-10-26 |
| 3.14 | Submission dry run | todo | after 3.8 and the boundary |
