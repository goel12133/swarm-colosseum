# Season one — draft, 21 of 28 nights (2026-09-28 to 2026-10-18)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 21 of 28, none failed.
- House bots written: 30 (13 attackers, 17 defenders); 30 still on the ladder, 0 retired. Rejected before the ladder: 14.
- Matches: 44,630 in 20 nightly round-robins; 5,490 distinct results in the cache.
- Tokens: 833,043.

## Top of the ladders

#1 attacker blast_proof_depth_interleave (h) (Elo 1346); #1 defender parked_hover_ring_doublecover (h) (Elo 1176).

## The five best ideas

1. **blast_proof_depth_interleave (h)** (counter_meta, attacker): “Park all 30 strikers motionless on a far staging ring where the scheduler ignores them, then dive in two interleaved shells offset 12 units in depth, so the ring converges with every pair of strikers more than one blast radius apart yet all of them arrive within a three-tick window.” #1 attacker, Elo 1346, wins 88%.
2. **parked_hover_ring_doublecover (h)** (exploiter, defender): “Park interceptors in a jittering hover next to the asset, then fire the whole magazine together at the collapsing ring once its spacing falls inside one blast width, so every striker is covered by two blasts.” #1 defender, Elo 1176, wins 84%.
3. **hidden_orbit_screen_then_interleaved_dro (h)** (generalist, attacker): “Park the whole swarm on a hidden orbit just outside radar range, send a decoy screen in first, then drop the strikers in two angle-interleaved shells that cross the ID ring together.” #2 attacker, Elo 1259, wins 78%.
4. **convergent_deadline_packer (h)** (generalist, defender): “Launches are held back until a capacity-aware deadline forces them, and the delay is spent hunting for intercept moments where one blast covers several identified strikers.” #2 defender, Elo 1174, wins 81%.
5. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #3 attacker, Elo 1202, wins 70%.

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

- 18 attackers × 24 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
