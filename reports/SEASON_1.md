# Season one — draft, 7 of 28 nights (2026-09-28 to 2026-10-04)

The season ends 2026-10-26; every number below is from the nights so far and is rewritten when this report is rerun.

## The season in numbers

- Nights: 7 of 28, none failed.
- House bots written: 12 (5 attackers, 7 defenders); 12 still on the ladder, 0 retired. Rejected before the ladder: 4.
- Matches: 5,930 in 7 nightly round-robins; 2,570 distinct results in the cache.
- Tokens: 277,925.

## Top of the ladders

#1 attacker interleaved_shell_ring (h) (Elo 1245); #1 defender convergence_blast_scheduler (h) (Elo 1195).

## The five best ideas

1. **interleaved_shell_ring (h)** (generalist, attacker): “Stage all thirty strikers on a slowly rotating three-shell ring, then release them together so they arrive in one wave in which no two strikers ever come within two blast radii of each other.” #1 attacker, Elo 1245, wins 74%.
   Clip: `out/meta/SEASON_1_2026-10-04_attacker_interleaved_shell_ring.mp4`, its best match against loiter_then_collapse (h) (s9), 0.04 MB at 4x.
2. **convergence_blast_scheduler (h)** (counter_meta, defender): “Hold the interceptor magazine until a synchronized ring has squeezed itself so tight that neighbouring strikers sit inside one blast radius, then fire on an earliest-deadline schedule so each interceptor kills two or three strikers instead of one.” #1 defender, Elo 1195, wins 91%.
   Clip: `out/meta/SEASON_1_2026-10-01_defender_convergence_blast_scheduler.mp4`, its best match against synchronized_ring (h) (s3), 0.03 MB at 4x.
3. **synchronized_ring (h)** (counter_meta, attacker): “Park every striker just outside the defender's identification gate, spread evenly round a ring, then release them together so the launch cap and the magazine run out before the ring does.” #2 attacker, Elo 1197, wins 83%.
   Clip: `out/meta/SEASON_1_2026-09-29_attacker_synchronized_ring.mp4`, its best match against discriminating_ledger (h) (s3), 0.03 MB at 4x.
4. **backscheduled_blast_packer (h)** (generalist, defender): “Plan interceptor launches backwards from the last safe intercept tick, so each blast lands where inbound strikers are packed tightest, and still shoot lone strikers right away so there is time for a second try.” #2 defender, Elo 1087, wins 76%.
   Clip: `out/meta/SEASON_1_2026-10-03_defender_backscheduled_blast_packer.mp4`, its best match against rush (s7), 0.01 MB at 4x.
5. **phase_locked_ring (h)** (generalist, attacker): “Probe the engine's bearing convention with the first four launches, then use per-drone dogleg waypoints so every striker crosses the 150 u identification ring on the same tick, evenly spaced around the circle.” #3 attacker, Elo 1148, wins 76%.
   Clip: `out/meta/SEASON_1_2026-09-30_attacker_phase_locked_ring.mp4`, its best match against gun_only (s2), 0.03 MB at 4x.

## Rules findings

- S0-1 — Decoys are worthless against a defender that ignores them (2026-09-28)
- S0-2 — A spaced, synchronised all-striker wave beats every defender (2026-09-29)
- S0-3 — the answer to S0-2 overshot: defenders lean (2026-10-04)
- Watch: synchronized_ring (h): Verdict: a meta. convergence_blast_scheduler (h) held it under 90% on 2026-10-01.

Details in BALANCE.md.

## Research this season

- 01 · The league found two counters it wasn't told about (`research/01_unaided_discovery.md`)
- 02 · What a self-play league teaches you about your own game (`research/02_balance_findings.md`)
- 03 · Does persona diversity help? Not measurably, yet. (`research/03_persona_ablation.md`)
- 04 · Does an optimiser beat a greedy rule? Not here. (`research/04_annealed_defenders.md`)

## Coverage at the end

- 10 attackers × 14 defenders, 10 seeds a pairing.
- Defenders nobody gets through: none.
- Attackers no defender stops: none.
- Unique coverage: none.

## What season two changes

- candidate A, imperfect identification (dwell 8 ticks, 8% sticky error) (branch s2-a-imperfect-id, kept rebased on master), merging on 2026-10-26, not before.
- S0-2 was answered in play (watch verdict: a meta), so no economy fix is added (charter section 1).
