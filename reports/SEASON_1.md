# Season one — draft, 18 of 28 nights (2026-09-28 to 2026-10-15)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 18 of 28, none failed.
- House bots written: 27 (12 attackers, 15 defenders); 27 still on the ladder, 0 retired. Rejected before the ladder: 11.
- Matches: 32,260 in 17 nightly round-robins; 4,910 distinct results in the cache.
- Tokens: 726,544.

## Top of the ladders

#1 attacker blast_proof_depth_interleave (h) (Elo 1334); #1 defender convergent_deadline_packer (h) (Elo 1200).

## The five best ideas

1. **blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.” #1 attacker, Elo 1334, wins 87%.
2. **convergent_deadline_packer (h)** (generalist, defender): “Launches are held back until a capacity-aware deadline forces them, and the delay is spent hunting for intercept moments where one blast covers several identified strikers.” #1 defender, Elo 1200, wins 84%.
3. **deadline_cluster_ledger (h)** (generalist, defender): “Earliest-deadline backscheduling on a worst-case "rush now" clock, filling each forced launch with the confirmed striker whose predicted blast point catches the most other uncovered strikers, and ignoring every unidentified track outside id range.” #2 defender, Elo 1200, wins 80%.
4. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #2 attacker, Elo 1140, wins 68%.
5. **convergence_blast_scheduler (h)** (counter_meta, defender): “Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.” #3 defender, Elo 1192, wins 89%.

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
- 03 · Does persona diversity help? (13-night run) (`research/03_persona_ablation.md`)
- 04 · Does an optimiser beat a greedy rule? A little, unevenly. (`research/04_annealed_defenders.md`)

## Coverage at the end

- 17 attackers × 22 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
