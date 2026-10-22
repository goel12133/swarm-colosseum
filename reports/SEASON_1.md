# Season one — draft, 25 of 28 nights (2026-09-28 to 2026-10-22)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 25 of 28, none failed.
- House bots written: 37 (13 attackers, 24 defenders); 37 still on the ladder, 0 retired. Rejected before the ladder: 15.
- Matches: 64,790 in 24 nightly round-robins; 6,750 distinct results in the cache.
- Tokens: 988,994.

## Top of the ladders

#1 attacker blast_proof_depth_interleave (h) (Elo 1313); #1 defender parked_hover_ring_doublecover (h) (Elo 1176).

## The five best ideas

1. **blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.” #1 attacker, Elo 1313, wins 90%.
2. **parked_hover_ring_doublecover (h)** (exploiter, defender): “Park interceptors in a jittering hover next to the asset, then fire the whole magazine together at the collapsing ring once its spacing falls inside one blast width, so every striker is covered by two blasts.” #1 defender, Elo 1176, wins 84%.
3. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #2 attacker, Elo 1254, wins 76%.
4. **convergent_deadline_packer (h)** (generalist, defender): “Launches are held back until a capacity-aware deadline forces them, and the delay is spent hunting for intercept moments where one blast covers several identified strikers.” #2 defender, Elo 1174, wins 81%.
5. **phase_locked_ring (h)** (generalist, attacker): “Probe the engine's bearing convention with the first four launches, then use per-drone dogleg waypoints so every striker crosses the 150 u identification ring on the same tick, evenly spaced around the circle.” #3 attacker, Elo 1250, wins 71%.

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

- 18 attackers × 31 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
