# Season one — draft, 11 of 28 nights (2026-09-28 to 2026-10-08)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 11 of 28, none failed.
- House bots written: 18 (7 attackers, 11 defenders); 18 still on the ladder, 0 retired. Rejected before the ladder: 6.
- Matches: 13,220 in 11 nightly round-robins; 3,330 distinct results in the cache.
- Tokens: 407,692.

## Top of the ladders

#1 attacker synchronized_ring (h) (Elo 1185); #1 defender convergence_blast_scheduler (h) (Elo 1213).

## The five best ideas

1. **convergence_blast_scheduler (h)** (counter_meta, defender): “Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.” #1 defender, Elo 1213, wins 92%.
2. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #1 attacker, Elo 1185, wins 76%.
3. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #2 attacker, Elo 1169, wins 69%.
4. **hover_bank_late_binder (h)** (contrarian, defender): “Bank interceptor flight time by hovering the whole magazine over the asset with alternating retargets, then bind every interceptor to a cluster at the last safe tick so overlapping blasts cover each converging striker twice.” #2 defender, Elo 1097, wins 82%.
5. **depth_shell_saturation (h)** (counter_meta, attacker): “Park all 30 strikers just outside gun range in three interleaved depth shells, then release them on one tick so that no two strikers ever share a blast radius and every interceptor kills at most one.” #3 attacker, Elo 1151, wins 43%.

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
- 04 · Does an optimiser beat a greedy rule? Not here. (`research/04_annealed_defenders.md`)

## Coverage at the end

- 12 attackers × 18 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
