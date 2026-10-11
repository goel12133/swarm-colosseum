# Week 2 — 2026-10-05 to 2026-10-11

Swarm Colosseum weekly meta report, real nights 8–14.

## Ladders

| # | attacker | Elo (Δ) | defender | Elo (Δ) |
|---|---|---|---|---|
| 1 | blast_proof_depth_interleave (h) | 1332 (new) | convergence_blast_scheduler (h) | 1158 (-37) |
| 2 | synchronized_ring (h) | 1187 (-10) | cluster_blast_column_breaker (h) | 1151 (new) |
| 3 | interleaved_shell_ring (h) | 1186 (-59) | convergent_deadline_packer (h) | 1137 (new) |
| 4 | phase_locked_ring (h) | 1135 (-13) | deadline_cluster_ledger (h) | 1093 (new) |
| 5 | depth_shell_saturation (h) | 1069 (-63) | backscheduled_blast_packer (h) | 1079 (-8) |

(h) house bot, (s) outside submission. Δ is Elo change since 2026-10-04.

Attackers: entered the top five: blast_proof_depth_interleave (h); left it: staggered_screen_trickle (h).
Defenders: entered the top five: cluster_blast_column_breaker (h), convergent_deadline_packer (h), deadline_cluster_ledger (h); left it: loiter_then_collapse (h), dither_parked_magazine (h), nearest_first.

## Which personas produced winners

- **exploiter**: 4 written, 4 beat their target, 4 still alive, best finish #2 defender.
- **counter_meta**: 3 written, 2 beat their target, 3 still alive, best finish #1 attacker.
- **generalist**: 3 written, 0 beat their target, 3 still alive, best finish #2 defender.
- **contrarian**: 2 written, 0 beat their target, 2 still alive, best finish #2 defender.

## Best new idea

**blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one bla...”

Result: #1 attacker, Elo 1332, wins 88% of its matches, beat its target.

Clip: `out/meta/WEEK_2_2026-10-11_attacker_blast_proof_depth_interleave.mp4`, its best match against convergence_blast_scheduler (h) (s3), 0.04 MB at 4x.

## Coverage

Who gets through each defender (at least one seed of 10):

- discriminating_ledger (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- miss_budget_scheduler (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- reveal_timed_prelaunch (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), multi_axis
- convergence_blast_scheduler (h): synchronized_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- loiter_then_collapse (h): staggered_screen_trickle (h), synchronized_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), trickle
- backscheduled_blast_packer (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), multi_axis
- dither_parked_magazine (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- cluster_blast_column_breaker (h): staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), trickle
- contracting_ring_blaster (h): staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), blast_proof_depth_interleave (h), trickle
- deadline_cluster_ledger (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- hover_bank_late_binder (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), shadow_pair_ring (h), blast_proof_depth_interleave (h)
- class_gated_magazine_keeper (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), multi_axis
- hover_bank_double_lattice (h): staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), trickle
- convergent_deadline_packer (h): synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), blast_proof_depth_interleave (h)
- annealed_assignment: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h)
- annealed_assignment_eager: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), shadow_pair_ring (h), blast_proof_depth_interleave (h)
- greedy_value_model: synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), shadow_pair_ring (h), blast_proof_depth_interleave (h)
- gun_only: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), parked_ring_magazine_drain (h), staggered_trishell_blast_denial (h), attacker_blast_isolated_synchronized_rel (h), shadow_pair_ring (h), blast_proof_depth_interleave (h), decoy_screen, flanker, multi_axis, rush, trickle
- identify_then_engage: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), trickle
- layered: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), depth_shell_saturation (h), interleaved_shell_ring (h), parked_ring_magazine_drain (h), staggered_trishell_blast_denial (h), blast_proof_depth_interleave (h), flanker, multi_axis, trickle
- nearest_first: staggered_screen_trickle (h), synchronized_ring (h), phase_locked_ring (h), parked_ring_magazine_drain (h), staggered_trishell_blast_denial (h), attacker_blast_isolated_synchronized_rel (h), shadow_pair_ring (h), blast_proof_depth_interleave (h), decoy_screen, flanker, multi_axis, rush, trickle

Which defenders each attacker never gets through:

- staggered_screen_trickle (h): discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), backscheduled_blast_packer (h), dither_parked_magazine (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model
- synchronized_ring (h): none
- phase_locked_ring (h): convergence_blast_scheduler (h), loiter_then_collapse (h)
- depth_shell_saturation (h): cluster_blast_column_breaker (h), nearest_first
- interleaved_shell_ring (h): cluster_blast_column_breaker (h), nearest_first
- parked_ring_magazine_drain (h): discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage
- staggered_trishell_blast_denial (h): contracting_ring_blaster (h), hover_bank_late_binder (h), convergent_deadline_packer (h)
- attacker_blast_isolated_synchronized_rel (h): discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage, layered
- shadow_pair_ring (h): discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, identify_then_engage, layered
- blast_proof_depth_interleave (h): none
- decoy_screen: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage, layered
- flanker: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage
- multi_axis: discriminating_ledger (h), miss_budget_scheduler (h), convergence_blast_scheduler (h), loiter_then_collapse (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage
- rush: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), loiter_then_collapse (h), backscheduled_blast_packer (h), dither_parked_magazine (h), cluster_blast_column_breaker (h), contracting_ring_blaster (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), hover_bank_double_lattice (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model, identify_then_engage, layered
- trickle: discriminating_ledger (h), miss_budget_scheduler (h), reveal_timed_prelaunch (h), convergence_blast_scheduler (h), backscheduled_blast_packer (h), dither_parked_magazine (h), deadline_cluster_ledger (h), hover_bank_late_binder (h), class_gated_magazine_keeper (h), convergent_deadline_packer (h), annealed_assignment, annealed_assignment_eager, greedy_value_model

**Flags:** none.

## Rules findings

Nothing new in BALANCE.md this week.

## Watch

Watch: 2026-09-29_attacker_synchronized_ring.

- 2026-09-29 (before): it won 98% of its matches; best opponent identify_then_engage at 90%.
- 2026-09-30: it won 99% of its matches; best opponent identify_then_engage at 90%.
- 2026-10-01: it won 94% of its matches; best opponent convergence_blast_scheduler (h) at 40%.
- 2026-10-02: it won 87% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-03: it won 86% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-04: it won 83% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-05: it won 84% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-06: it won 79% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-07: it won 78% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-08: it won 76% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-09: it won 77% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-10: it won 74% of its matches; best opponent loiter_then_collapse (h) at 10%.
- 2026-10-11: it won 75% of its matches; best opponent loiter_then_collapse (h) at 10%.

**Verdict: a meta.** 2026-10-01_defender_convergence_blast_scheduler held it under 90% on 2026-10-01.

Watch: 2026-10-01_defender_convergence_blast_scheduler.

- 2026-10-05: it won 91% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-06: it won 92% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-07: it won 92% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-08: it won 92% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-09: it won 92% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-10: it won 93% of its matches; best opponent synchronized_ring (h) at 60%.
- 2026-10-11: it won 88% of its matches; best opponent blast_proof_depth_interleave (h) at 20%.

**Verdict: a meta.** 2026-09-29_attacker_synchronized_ring held it under 90% on 2026-10-05.

## Health

- Nights run: 7 (7 runs in all).
- Nights failed: none.
- Bots rejected: 2 — attacker: model returned no code block; attacker: model returned no code block.
- Retired: none.
- Tokens: 283,487 this week, 561,412 this season.
- Result cache: 4,320 entries; this week 13,960 of 15,710 matches came from it (89% hit rate), 1,750 were played.
- Mean tournament time: 97 s over 7 tournaments.
- Phase times doubled since last week: reports 10 s → 50 s.
- Disk: out/ is 304 MB (replays 186 MB, house_raw 0 MB, history 0 MB, meta 0 MB).

Health check:

    ok  docker     server 29.1.3
    ok  cli-login  logged in via claude.ai
    ok  cron       30 3 * * * /root/swarm-colosseum/scripts/nightly.sh
    ok  disk       23% used, 159 GB free, out/ is 304 MB
    ok  last-night 2026-10-11: ok
    ok  alert      none
    ok  boundary   season2 merges cleanly into master
