# 04 · Does an optimiser beat a greedy rule? Not here.

*Swarm Colosseum, season one, nights 2026-09-30 to 10-03 (four nights; preliminary).
Numbers are from the league's ladders (`out/history/`) and the latest matrix.*

**The question.** Every tick a defender decides which threats to send interceptors at and
where to point its gun. The `annealed_assignment` defenders write that decision as a small
optimisation problem (a QUBO: launch or not, gun or not, under the launch cap, the stock and
the gun's limits) and solve it by simulated annealing. Is the joint optimiser better than
just taking the best options one at a time?

**The control.** `greedy_value_model` uses the *same* value model (identical code, enforced
by a test) and replaces the annealer with a greedy pick: the best-valued threats in turn, up
to the cap, skipping any inside the blast radius of one already chosen. The only difference
between the two bots is the search. An eager variant of the optimiser (longer horizon,
cheaper interceptors in its energy) is included for context.

## Results

| | annealed (optimiser) | greedy (same model) | eager (optimiser) |
|---|---|---|---|
| mean score, nights 09-30 to 10-02 | **0.608** | 0.582 | 0.599 |
| mean score, night 10-03 | 0.556 | 0.571 | **0.608** |
| rank among defenders, 10-03 | #11 of 13 | #8 | #7 |
| mean cost exchange ratio | 0.71 | 0.67 | 0.70 |
| median / p99 time per tick | 0.72 / 2.06 ms | 0.63 / 1.82 ms | — |

Against each attacker on the latest night (score; higher is better for the defender), the
optimiser's lead over greedy:
- trickle **+0.10**, multi_axis +0.02, decoy_screen +0.02, flanker +0.01, rush 0.00
- the two synchronised-wave attackers +0.00 and +0.05: both bots lose badly to them
- **depth_shell_saturation −0.34** (0.144 against 0.483), a new attacker written on 10-03

## What this says

- **The value model does the work.** Against the baseline greedy defender `layered`, the
  annealed bot gained about +0.30 in mean score. Swapping its optimiser for a greedy pick
  keeps almost all of that.
- **The optimiser's gain is small and narrow.** It is clearest against trickle attacks, where
  many small threats arrive at once and choosing them jointly matters.
- **It isn't robust.** On the first night a new attacker appeared, the optimiser variant fell
  from the top half to #11 of 13. The greedy variant with the same model held up better. One
  attacker is enough to wipe out its whole lead.
- **It costs nothing measurable.** Per-tick time is dominated by the sandbox round trip, not
  the search (0.72 ms against 0.63 ms median).

**Bottom line:** on this game and this field, joint optimisation adds no reliable value over
a greedy pick with the same model. That is the result, and it is reported as one. Four
nights is a preliminary sample; the comparison will be rerun on the full season for the
season report.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits).
