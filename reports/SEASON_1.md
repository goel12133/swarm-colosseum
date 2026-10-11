# Season one — draft, 14 of 28 nights (2026-09-28 to 2026-10-11)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 14 of 28, none failed.
- House bots written: 24 (10 attackers, 14 defenders); 24 still on the ladder, 0 retired. Rejected before the ladder: 6.
- Matches: 21,640 in 14 nightly round-robins; 4,320 distinct results in the cache.
- Tokens: 561,412.

## Top of the ladders

#1 attacker blast_proof_depth_interleave (h) (Elo 1332); #1 defender convergence_blast_scheduler (h) (Elo 1158).

## The five best ideas

1. **blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.” #1 attacker, Elo 1332, wins 88%.
2. **convergence_blast_scheduler (h)** (counter_meta, defender): “Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.” #1 defender, Elo 1158, wins 88%.
3. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #2 attacker, Elo 1187, wins 75%.
4. **cluster_blast_column_breaker (h)** (exploiter, defender): “Treat a single-bearing stream as one target, and spend each interceptor on whichever track has the most uncovered threat inside its blast radius.” #2 defender, Elo 1151, wins 78%.
5. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #3 attacker, Elo 1186, wins 70%.

## Rules findings

- S0-1 — Decoys are worthless against a defender that ignores them (2026-09-28)
- S0-2 — A spaced, synchronised all-striker wave beats every defender (2026-09-29)
- S0-3 — the answer to S0-2 overshot: defenders lean (2026-10-04)
- Watch: synchronized_ring (h): Verdict: a meta. convergence_blast_scheduler (h) held it under 90% on 2026-10-01.
- Watch: convergence_blast_scheduler (h): Verdict: a meta. synchronized_ring (h) held it under 90% on 2026-10-05.

Details in BALANCE.md.

## Research this season

- Swarm Colosseum in one page (`research/00_summary.md`)
- 01 · The league found two counters it wasn't told about (`research/01_unaided_discovery.md`)
- 02 · What a self-play league teaches you about your own game (`research/02_balance_findings.md`)
- 03 · Does persona diversity help? Not measurably, yet. (`research/03_persona_ablation.md`)
- 04 · Does an optimiser beat a greedy rule? A little, unevenly. (`research/04_annealed_defenders.md`)

## Coverage at the end

- 15 attackers × 21 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
