# 04 · Does an optimiser beat a greedy rule? A little, unevenly.

*Swarm Colosseum, season one, nights 2026-09-30 to 10-10 (eleven nights). This replaces an
earlier four-night cut that said "not here"; with the full field, that was too strong.
The full tables are in `ANALYSIS_annealing.md`, made by `scripts/ablation_annealing.py`.*

**The question.** Every tick a defender decides which threats to send interceptors at and
where to point its gun. The `annealed_assignment` defenders write that decision as a small
optimisation problem (a QUBO: launch or not, gun or not, under the launch cap, the stock and
the gun's limits) and solve it by simulated annealing. Is the joint optimiser better than
just taking the best options one at a time?

**The control.** `greedy_value_model` uses the *same* value model (identical code, enforced
by a test) and replaces the annealer with a greedy pick: the best-valued threats in turn, up
to the cap, skipping any inside the blast radius of one already chosen. The only difference
between the two bots is the search.

## Results

Each attacker played both bots on the same ten seeds, giving 140 paired matches. The score
is the defender's, from 0 to 1, higher is better; the difference is optimiser minus greedy.

| | optimiser | greedy |
|---|---|---|
| attackers it beats the other on (of 14) | **9** | 1 (4 level) |
| mean paired difference | **+0.037** | |
| 95% interval on that difference | −0.038 to +0.106 | |
| ladder on 10-10 (of 20 defenders) | **#4**, Elo 1087 | #16, Elo 1020 |
| nights with the higher mean score (of 11) | **10** | 1 |
| median / p99 time per tick | 0.87 / 4.99 ms | 0.64 / 4.19 ms |

The biggest differences:
- **interleaved_shell_ring +0.27**, staggered_trishell_blast_denial +0.25, shadow_pair_ring
  +0.11, trickle +0.10;
- **depth_shell_saturation −0.34**: the optimiser lost the asset in 10 of 10 matches,
  greedy in 3.

## What this says

- **The value model still does most of the work.** Against the baseline greedy defender
  `layered`, the value model gained about +0.30 in mean score. The search adds about a tenth
  of that on average.
- **The optimiser is usually ahead, but not by a dependable amount.** It is ahead against 9
  attackers and behind against 1 (a sign test gives p = 0.02), yet the average lead's
  interval includes zero. Its largest wins are against three league-written wave attacks and
  plain trickle; why those in particular hasn't been tested.
- **It isn't robust.** One attacker breaks it completely while greedy mostly holds. A
  defender that is better on average but has a catastrophic case is a real trade-off, not a
  free improvement.
- **It costs almost nothing.** The search adds about 0.2 ms a tick, against a 2 s limit.

**Bottom line:** on this game, joint optimisation gives a small, uneven gain over a greedy
pick with the same model. It is more often ahead than behind, it is not reliably large, and
one attack breaks it. The four-night version of this page said it added no reliable value;
more data moved that, and this page says so. The comparison is rerun at the end of the
season.

**Limits.** The 14 attackers are the league's own field, not a random sample, and several
were written against defenders already on the ladder. There is one value model, one game and
ten seeds per pairing.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits).
