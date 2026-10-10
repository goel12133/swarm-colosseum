# Season one — draft, 13 of 28 nights (2026-09-28 to 2026-10-10)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 13 of 28, none failed.
- House bots written: 22 (9 attackers, 13 defenders); 22 still on the ladder, 0 retired. Rejected before the ladder: 6.
- Matches: 18,490 in 13 nightly round-robins; 3,970 distinct results in the cache.
- Tokens: 527,648.

## Top of the ladders

#1 attacker interleaved_shell_ring (h) (Elo 1240); #1 defender convergence_blast_scheduler (h) (Elo 1199).

## The five best ideas

1. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #1 attacker, Elo 1240, wins 72%.
2. **convergence_blast_scheduler (h)** (counter_meta, defender): “Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.” #1 defender, Elo 1199, wins 93%.
3. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #2 attacker, Elo 1162, wins 74%.
4. **deadline_cluster_ledger (h)** (generalist, defender): “Earliest-deadline backscheduling on a worst-case "rush now" clock, filling each forced launch with the confirmed striker whose predicted blast point catches the most other uncovered strikers, and ignoring every unidentified track outside id range.” #2 defender, Elo 1108, wins 82%.
5. **depth_shell_saturation (h)** (counter_meta, attacker): “Park all 30 strikers just outside gun range in three interleaved depth shells, then release them on one tick so that no two strikers ever share a blast radius and every interceptor kills at most one.” #3 attacker, Elo 1106, wins 41%.

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

- 14 attackers × 20 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
