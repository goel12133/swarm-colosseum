# Season one — 2026-09-28 to 2026-10-25

## The season in numbers

- Nights: 28 of 28, none failed.
- House bots written: 40 (14 attackers, 26 defenders); 40 still on the ladder, 0 retired. Rejected before the ladder: 18.
- Matches: 83,030 in 27 nightly round-robins; 7,440 distinct results in the cache.
- Tokens: 1,099,094.

## Top of the ladders

#1 attacker blast_proof_depth_interleave (h) (Elo 1314); #1 defender convergent_deadline_packer (h) (Elo 1186).

## The five best ideas

1. **blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.” #1 attacker, Elo 1314, wins 90%.
   Clip: `out/meta/SEASON_1_2026-10-11_attacker_blast_proof_depth_interleave.mp4`, its best match against convergence_blast_scheduler (h) (s3), 0.04 MB at 4x.
2. **convergent_deadline_packer (h)** (generalist, defender): “Launches are held back until a capacity-aware deadline forces them, and the delay is spent hunting for intercept moments where one blast covers several identified strikers.” #1 defender, Elo 1186, wins 78%.
   Clip: `out/meta/SEASON_1_2026-10-11_defender_convergent_deadline_packer.mp4`, its best match against parked_ring_magazine_drain (h) (s7), 0.02 MB at 4x.
3. **bait_count_then_clear_sky_wave (h)** (exploiter, attacker): “Count the defender's interceptor launches from the attacker's own view of the sky and hold every striker on the pad until the bait-drawn magazine is seen to be spent or aged out, then send one interleaved striker wave.” #2 attacker, Elo 1312, wins 89%.
   Clip: `out/meta/SEASON_1_2026-10-23_attacker_bait_count_then_clear_sky_wave.mp4`, its best match against contracting_ring_blaster (h) (s7), 0.06 MB at 4x.
4. **parked_hover_ring_doublecover (h)** (exploiter, defender): “Park interceptors in a jittering hover next to the asset, then fire the whole magazine together at the collapsing ring once its spacing falls inside one blast width, so every striker is covered by two blasts.” #2 defender, Elo 1162, wins 81%.
   Clip: `out/meta/SEASON_1_2026-10-14_defender_parked_hover_ring_doublecover.mp4`, its best match against attacker_blast_isolated_synchronized_rel (h) (s6), 0.02 MB at 4x.
5. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #3 attacker, Elo 1276, wins 78%.
   Clip: `out/meta/SEASON_1_2026-09-29_attacker_synchronized_ring.mp4`, its best match against discriminating_ledger (h) (s3), 0.04 MB at 4x.

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

- 19 attackers × 33 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
