# Optimiser ablation (charter 3.5): annealing against a greedy pick, same value model

*Season one, nights 2026-09-30 to 2026-10-10 (11 nights with both bots on the ladder).
Engine 65ab01c2dc7db9f7, rules 2b7e5c64c6002a5b. Every number below comes from
`python3 scripts/ablation_annealing.py --timing 3`, which reads the result cache and
`out/history/` and plays nothing except the timing matches. It replaces the four-night cut
in research/04, whose conclusion it revises.*

**The two bots.** `annealed_assignment` writes each tick's choice (which threats get an
interceptor, where the gun points) as a small QUBO and solves it by simulated annealing.
`greedy_value_model` has the same value model, enforced identical by a test, and picks
greedily: the best-valued threats in turn, up to the launch cap. Only the search differs.
`annealed_assignment_eager` (an optimiser with different knobs) is shown for context.

## Paired matches: same attacker, same seed

140 pairs, from 14 attackers × 10 seeds. The difference is the optimiser's defender score
minus greedy's (scores run 0 to 1; higher is better for the defender). "Breached" counts
the matches out of 10 in which the asset was lost.

| attacker | optimiser | greedy | difference | CER opt / greedy | breached opt / greedy |
|---|---|---|---|---|---|
| depth_shell_saturation | 0.144 | 0.483 | **−0.339** | 0.57 / 0.69 | 10 / 3 |
| staggered_screen_trickle | 0.721 | 0.722 | −0.001 | 0.54 / 0.55 | 0 / 0 |
| blast_isolated_synchr… | 0.790 | 0.790 | −0.001 | 0.91 / 0.91 | 0 / 0 |
| synchronized_ring | 0.140 | 0.138 | +0.001 | 0.54 / 0.53 | 10 / 10 |
| rush | 0.800 | 0.796 | +0.004 | 1.01 / 0.97 | 0 / 0 |
| flanker | 0.799 | 0.788 | +0.011 | 1.01 / 0.90 | 0 / 0 |
| decoy_screen | 0.788 | 0.771 | +0.017 | 0.89 / 0.75 | 0 / 0 |
| multi_axis | 0.704 | 0.682 | +0.022 | 0.70 / 0.68 | 0 / 0 |
| parked_ring_magazine_drain | 0.826 | 0.794 | +0.032 | 1.30 / 0.95 | 0 / 0 |
| phase_locked_ring | 0.166 | 0.115 | +0.051 | 0.57 / 0.40 | 9 / 10 |
| trickle | 0.747 | 0.645 | +0.101 | 0.58 / 0.57 | 0 / 0 |
| shadow_pair_ring | 0.727 | 0.622 | +0.106 | 0.72 / 0.68 | 0 / 1 |
| staggered_trishell_blast_denial | 0.582 | 0.336 | **+0.246** | 0.68 / 0.64 | 2 / 5 |
| interleaved_shell_ring | 0.417 | 0.144 | **+0.273** | 0.65 / 0.56 | 4 / 10 |

- **Who is ahead:** the optimiser against 9 attackers, greedy against 1, and level
  (within 0.005) against 4. An exact sign test on that split gives p = 0.02.
- **By how much:** the mean difference across attackers is **+0.037**. The 95% interval, from
  a bootstrap over whole attackers, is **−0.038 to +0.106**, so it includes zero.
- **CER** (value destroyed per credit spent; higher is better for the defender): the
  optimiser's is higher against 11 of 14 attackers.

## The ladder, night by night

| night | defenders | Elo opt (rank) | Elo greedy (rank) | Elo eager (rank) | score opt | score greedy | CER opt | CER greedy |
|---|---|---|---|---|---|---|---|---|
| 09-30 | 10 | 976 (#6) | 1004 (#4) | 997 (#5) | 0.608 | 0.582 | 0.73 | 0.67 |
| 10-01 | 11 | 976 (#7) | 1004 (#5) | 997 (#6) | 0.608 | 0.582 | 0.73 | 0.67 |
| 10-02 | 12 | 976 (#8) | 1004 (#6) | 997 (#7) | 0.608 | 0.582 | 0.73 | 0.67 |
| 10-03 | 13 | 919 (#11) | 1010 (#8) | 1042 (#7) | 0.556 | 0.571 | 0.71 | 0.67 |
| 10-04 | 14 | 920 (#12) | 961 (#10) | 973 (#9) | 0.543 | 0.528 | 0.71 | 0.66 |
| 10-05 | 15 | 920 (#13) | 961 (#11) | 973 (#10) | 0.543 | 0.528 | 0.71 | 0.66 |
| 10-06 | 16 | 998 (#11) | 994 (#12) | 1012 (#10) | 0.568 | 0.553 | 0.76 | 0.69 |
| 10-07 | 17 | 998 (#12) | 994 (#13) | 1012 (#11) | 0.568 | 0.553 | 0.76 | 0.69 |
| 10-08 | 18 | 1017 (#10) | 969 (#14) | 981 (#13) | 0.569 | 0.534 | 0.75 | 0.68 |
| 10-09 | 19 | 1065 (#7) | 1006 (#14) | 1025 (#11) | 0.586 | 0.554 | 0.77 | 0.70 |
| 10-10 | 20 | 1087 (#4) | 1020 (#16) | 1034 (#15) | 0.596 | 0.559 | 0.76 | 0.70 |

The optimiser's mean score is higher on 10 of 11 nights, and its CER on all 11. On Elo,
greedy led until 10-05 and the optimiser has led since 10-06. The nights aren't independent
samples: each night's ladder is the cumulative field plus one or two new bots.

## Time per tick

These are host-side round trips for one defender `act()`, sandbox included: 3 seeds against
each of the 14 attackers, all three bots interleaved in one pool on an otherwise idle machine
(2026-10-10, after the night).

| | ticks | median | p99 | worst |
|---|---|---|---|---|
| optimiser | 9,839 | 0.87 ms | 4.99 ms | 29.8 ms |
| greedy | 9,618 | 0.64 ms | 4.19 ms | 37.0 ms |
| eager optimiser | 9,630 | 0.84 ms | 4.57 ms | 17.5 ms |

The search costs about +0.2 ms a tick at the median, against a 2 s limit. Neither bot ever
came close to the limit.

## Verdict

**The optimiser adds something, but it is small, uneven and not robust.**

- It beats the greedy pick against most attackers.
- Its average lead is too uncertain to rule out zero.
- The lead is concentrated against three structured, league-written attacks
  (interleaved_shell_ring, staggered_trishell_blast_denial and shadow_pair_ring) and against
  trickle.
- One attacker, depth_shell_saturation, breaks it outright (10 of 10 breached, against
  greedy's 3).

**The preliminary result is revised.** The four-night cut said joint optimisation "adds no
reliable value". With seven more nights and five more attackers, that is too strong: the
optimiser is more often ahead than behind, and on the current ladder it ranks #4 against
greedy's #16. It is still fair to say that the value model does most of the work. Against
the baseline `layered`, the value model's gain was about +0.30 (research/04); the search adds
about a tenth of that on average.

**Limits.**
- The 14 attackers are the league's actual field, not a random sample. Several were written
  to beat the defenders already on the ladder, so the sign test and the bootstrap both treat
  them as more interchangeable than they are.
- There is one value model and one game.
- Ten seeds per pairing.
