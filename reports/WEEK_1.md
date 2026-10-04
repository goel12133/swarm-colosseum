# Week 1 — 2026-09-28 to 2026-10-04

Swarm Colosseum weekly meta report, real nights 1–7.

## Ladders

| # | attacker | Elo (Δ) | defender | Elo (Δ) |
|---|---|---|---|---|
| 1 | interleaved_shell_ring (h) | 1245 (new) | convergence_blast_scheduler (h) | 1195 (new) |
| 2 | synchronized_ring (h) | 1197 (new) | backscheduled_blast_packer (h) | 1087 (new) |
| 3 | phase_locked_ring (h) | 1148 (new) | loiter_then_collapse (h) | 1079 (new) |
| 4 | depth_shell_saturation (h) | 1132 (new) | dither_parked_magazine (h) | 1073 (new) |
| 5 | staggered_screen_trickle (h) | 952 (-157) | nearest_first | 1016 (+138) |

(h) house bot, (s) outside submission. Δ is Elo change since the first night of the week (2026-09-28).

Attackers: entered the top five: interleaved_shell_ring (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h); left it: trickle, multi_axis, flanker, decoy_screen.
Defenders: entered the top five: convergence_blast_scheduler (h), backscheduled_blast_packer (h), loiter_then_collapse (h), dither_parked_magazine (h); left it: discriminating_ledger (h), identify_then_engage, layered, gun_only.

## Which personas produced winners

- **exploiter**: 2 written, 0 beat their target, 2 still alive, best finish #1 attacker.
- **counter_meta**: 4 written, 3 beat their target, 4 still alive, best finish #1 attacker.
- **generalist**: 3 written, 1 beat their target, 3 still alive, best finish #1 attacker.
- **contrarian**: 3 written, 1 beat their target, 3 still alive, best finish #1 defender.

## Best new idea

**interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.”

Result: #1 attacker, Elo 1245, wins 74% of its matches, did not beat its target.

Clip: `out/meta/WEEK_1_2026-10-04_attacker_interleaved_shell_ring.mp4`, its best match against loiter_then_collapse (h) (s9), 0.04 MB at 4x.

## Coverage

Who gets through each defender (at least one seed of 10):

- discriminating_ledger (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- miss_budget_scheduler (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- reveal_timed_prelaunch (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), multi_axis
- convergence_blast_scheduler (h): synchronized_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- loiter_then_collapse (h): staggered_screen_trickle (h), synchronized_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), trickle
- backscheduled_blast_packer (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), multi_axis
- dither_parked_magazine (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- annealed_assignment: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- annealed_assignment_eager: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- greedy_value_model: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h)
- gun_only: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), decoy_screen, flanker, multi_axis, rush, trickle
- identify_then_engage: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), trickle
- layered: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), flanker, multi_axis, trickle
- nearest_first: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), decoy_screen, flanker, multi_axis, rush, trickle

Which defenders each attacker never gets through:

- staggered_screen_trickle (h): discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), backscheduled_blast_packer (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model
- synchronized_ring (h): none
- phase_locked_ring (h): convergence_blast_scheduler (h), loiter_then_collapse (h)
- depth_shell_saturation (h): nearest_first
- interleaved_shell_ring (h): nearest_first
- decoy_screen: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage, layered
- flanker: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage
- multi_axis: discriminating_ledger (h), miss_budget_scheduler (h), convergence_blast_scheduler (h), loiter_then_collapse (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage
- rush: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage, layered
- trickle: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), backscheduled_blast_packer (h), dither_parked_magazine (h), annealed_assignment, annealed_assignment_eager, greedy_value_model

**Flags:** none.

## Rules findings

- S0-1 — Decoys are worthless against a defender that ignores them
- S0-2 — A spaced, synchronised all-striker wave beats every defender

Details in root BALANCE.md.

## Watch

Watch: 2026-09-29_attacker_synchronized_ring.

- 2026-09-29 (before): it won 98% of its matches; best defender identify_then_engage at 90%.
- 2026-09-30: it won 99% of its matches; best defender identify_then_engage at 90%.
- 2026-10-01: it won 94% of its matches; best defender convergence_blast_scheduler (h) at 40%.
- 2026-10-02: it won 87% of its matches; best defender loiter_then_collapse (h) at 10%.
- 2026-10-03: it won 86% of its matches; best defender loiter_then_collapse (h) at 10%.
- 2026-10-04: it won 83% of its matches; best defender loiter_then_collapse (h) at 10%.

**Verdict: a meta.** 2026-10-01_defender_convergence_blast_scheduler held it under 90% on 2026-10-01.

## Health

- Nights run: 7 (8 runs in all).
- Nights failed: none.
- Bots rejected: 4 — attacker: model returned too few code blocks; defender: model returned too few code blocks; defender: model returned no code block; defender: model returned no code block.
- Retired: none.
- Tokens: 277,925 this week, 277,925 this season.
- Result cache: 2,570 entries; this week 0 of 1,400 matches came from it (0% hit rate), 1,400 were played.
- Mean tournament time: 281 s over 7 tournaments.
- Phase times doubled since last week: none.
- Disk: out/ is 220 MB (replays 78 MB, house_raw 0 MB, history 0 MB, meta 0 MB).

Health check:

    ok  docker     server 29.1.3
    ok  cli-login  logged in via claude.ai
    ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
    ok  disk       22% used, 160 GB free, out/ is 220 MB
    ok  last-night 2026-10-04: ok
    ok  alert      none
