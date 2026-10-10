# Backlog

Standing rule (2026-10-03): an item or output that trips a safety stop is stopped, written up
with its flag, and left; it is never rephrased to get past the stop.

**Launch sprint: done (launched 2026-10-10, LAUNCH_STATUS.md).** Since launch every merge to
master is public the next night. Build sessions (every 2 h) may take only the items marked
(s) below, in this order, each once its gate has passed, plus hygiene; they may not touch
the protected files in `colosseum/daily.py` (publishing, the audit, the sandbox, intake,
fold-back, the rules). G, 3.8 and switching fold-back on are human-gated. An item with two
sessions in a row that don't merge is frozen and written up.

**Post-launch (founder, 2026-10-10), in order:**

| # | item | gate | status | note |
|---|---|---|---|---|
| P1 | Site trim (<60 MB) | — | done | 191.0 → 20.5 MB; rule in `site.full_page_stems`; packed replays |
| P2 | Fold-back of merged PRs | — | done, **off** | `colosseum/foldback.py`; on only after 3.8 passes |
| P3 | 3.8 runbook | — | done | `reports/RUNBOOK_3.8.md`; intake wired behind the fold-back switch (done) |
| P4 | Season boundary | 2026-10-26, before that night's league | **armed** | `colosseum/boundary.py` from nightly.sh: final season report, freeze `seasons/S1/`, merge branch `season2` (candidate A + SEASON = 1 + season two dates), full suite; on failure master is untouched and that night's league is skipped with an alert. Health check `boundary` warns daily if `season2` stops merging cleanly. Not a session item |
| P5 (s) | 14-night persona ablation → research/03, superseding the preliminary | `out/ablation_14/done` exists | waiting | the ablation session runs on its own from 10-11 |
| W (s) | Weekly founder report, `reports/FOUNDER_WEEK_<n>.md` (charter "Reporting") | the week's meta report is written | next: week 2 after night 10-11 | |
| 3.13 (s) | `seasons/S2/WEEK1.md` | seven nights of season two (night 2026-11-01 committed) | waiting | |
| 3.14 (s) | Submission dry run | 3.8 passed and the boundary done | waiting | |

From the operating charter, section 3, in order. Status: todo / doing / done / blocked.

| # | item | status | note |
|---|---|---|---|
| G | Content-check filter on generated bots | done | generic vocabulary + designation shape, before validation, CONTENT: log; no false positives on 50 files |
| 3.1 | Match result cache | done | cold 372 s → warm 0.0 s; nightly 65 s with two new bots |
| 3.2 | Generator token discipline | done | prompts −15..−73%; budgets in .meta.json |
| 3.3 | Daily engineering session (manual run first, then cron) | done | first run watched 2026-10-03; cron 05:00 UTC from 2026-10-04 |
| 3.4 | Persona ablation (after 14 real nights) | waiting | not before night 2026-10-11 |
| 3.5 | Optimiser ablation (after 7 nights of greedy_value_model) | done | `ANALYSIS_annealing.md` + research/04 revised: small, uneven gain (9 of 14 attackers, mean +0.037, CI −0.04..+0.11), one attacker breaks it; +0.2 ms/tick |
| 3.6 | Season report | waiting | at the boundary, 2026-10-26 |
| 3.7 | Tactic library export | done | 20 cards, 9 families; writes out/library/; nightly rebuild comes with 3.10 |
| 3.8 | Sandbox hardening and validator testing (defensive, inert inputs) + SECURITY.md | **scheduled** | interactive with the founder, evening of Sat 2026-10-24 (default 19:00 his time); submissions open only if it passes -- human-gated, the build session must not touch this |
| 3.9 | Engine fuzzing and invariants | done | stdlib fuzzer; 10,000 trajectories, 0 failures; 500 nightly in after-night; found + fixed a non-finite-number crash (SECURITY, PROGRESS) |
| 3.10 | Site bundle kept current + about page | done | library rebuilt nightly before the site; library, seasons archive and ABOUT.md pages linked from every page; still unserved |
| 3.11 | Workshop kit | done | workshop/: 90-min lesson, facilitator page, 3 starters per side, 5 exercises with solutions; `make workshop` checks all solvable (via test, 293 pass); offline, no Docker |
| 3.12 | Higher-fidelity engine scoping, for the game (2 pages, abstract, no transfer claims) | done | `ENGINE_SCOPING.md`: sensor dropouts/false tracks, classification confusion, turn rates, altitude bands; neutral defaults, order 2→3→1, bands need founder; ROADMAP paid-API line raised with founder |
| 3.13 | Season two first week | todo | after 2026-10-26 (post-launch table above) |
| 3.14 | Submission dry run | todo | after 3.8 and the boundary (post-launch table above) |
