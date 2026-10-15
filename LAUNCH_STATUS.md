# Launch status — sprint complete (16 of 16, 2026-10-08); launched 2026-10-10

Public since 2026-10-10: <https://pelennor.tech>. (s) = unattended build session; (h) = lead engineer, interactive.

| # | item | status | left |
|---|---|---|---|
| L1 | unaided-discovery write-up (h) | done | research/01; clips in out/research/clips |
| L2 | balance-findings write-up (h) | done | night-7 status written: answered in play; defenders now 62% |
| L3 | persona ablation, early cut (h) | done | final (P5, 10-14): 13 persona nights, 26 slots per arm: mean score 0.574 vs 0.578, top fives 10 vs 10, narrow unique coverage 3 vs 0 (research/03) |
| L4 | annealing ablation (h) | done | superseded by 3.5 (11 nights, 2026-10-10): optimiser ahead vs 9 of 14 attackers, mean +0.037 (CI includes 0), one attacker breaks it |
| L5 | `make reproduce` (h) | done | fresh clone: REPRODUCED in 364 s |
| L6 | site redesign (s) | done | superseded 2026-10-11 by the founder's reference design (replay channel, ladders with movement, recap, changelog), live on pelennor.tech |
| L7 | five clips, mp4 + gif (s) | done | `colosseum.clip --showcase`: 5 captioned clips, 1x, each ≤0.21 MB; render on live out/ once |
| L8 | README, CITATION, CONTRIBUTING, licences (s) | done | Apache-2.0 (code) + CC BY 4.0 (replays, research): LICENSE, LICENSE-CC-BY-4.0, LICENSING.md, CITATION, site footer |
| L9 | submissions via PR + workflow (s) | done | PR adds `bots/submitted/pr/<login>/<NAME>.py`; CI check is static only (never runs the bot); `submit_pr intake` = sandbox gate after merge; not run on GitHub yet |
| L10 | publish pipeline, dry (s) | done | `scripts/publish.sh`: rewrite, audit, site, main (ff) + gh-pages; tested on a local bare remote; `--live` is yours |
| L11 | secret and history audit (h) | done | no secrets; hostname rewritten in the publish clone (approved), live repo untouched |
| L12 | workshop README for teachers (s) | done | `workshop/TEACHERS.md`: who it's for, needs, files in order, 3-step setup, safety; linked from README |
| L13 | one-page summary (h) | done | research/00_summary.md, 520 words; on the site as research/00_summary.html |
| L14 | season report draft (h) | done | rewritten and committed every night by after-night; draft until night 28, then final with clips (the nights so far: first line of reports/SEASON_1.md) |
| L15 | full rehearsal on a scratch clone (h) | done | `scripts/rehearse.sh`: 10 of 10 steps ok, 36 min; 56 screenshots in out/launch_screens/ |
| L16 | LAUNCH_READY.md (h) | done | reports/LAUNCH_READY.md: what is ready, screenshots, launch-day order, 5 gaps |

**Launched 2026-10-10 04:37 UTC:** <https://pelennor.tech>, code at
<https://github.com/goel12133/swarm-colosseum>. Leak rescan clean, test PR green, nightly
republish armed; details and gaps in reports/LAUNCH_DONE.md.

**Build session (post-launch, 10-14, later):** P5 done. The ablation finished
(`out/ablation_14/done`, 10-14) and committed research/03. I checked it: the persona-arm
numbers match the league record (22 bots + 4 rejected = 26 slots, 0 retired). I removed
"preliminary" (the site was labelling the final run with it), added a bottom line and a
reading, and updated research/00. Night 10-14 ok: 1 defender accepted (rank 3); the contrarian
attacker returned no code block. Later sessions (to 10-15) ran hygiene only: health all ok, 401
tests pass (latest 214.03 s, 10-15, eighth). Night 10-15 ok (1 attacker accepted, rank 7; defender
returned no code block). W week 3 after night 10-18.

**Waiting on the founder:** nothing for launch. **3.8** is interactive-only and scheduled for
the evening of Sat 2026-10-24; submissions stay closed until it passes. Item G was scrapped as
a prompt rewrite; its content-check half is done and the prompt stays 2026-10-03.1.

**Stopped or held (DECISIONS.local.md, 10-11):** SPEC-4 (Lab arena) and the products brief
were stopped by a safety classifier and are not started; the re-theme is held. Yours to decide.
