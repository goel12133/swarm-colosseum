# 03 · Does persona diversity help? (13-night run)

*Generated automatically from `out/ablation_14/result.json` after real night 14. Nights
2026-09-29 to 2026-10-11, 26 generator slots per arm, 10 seeds per pairing. The
five-night preliminary write-up, with its worked example, is in this file's git history.*

**The test.** Every slot the real league filled was refilled by the *generalist* persona
from the same evidence snapshot, through the same generator, validation and sandbox smoke
test. Both arms were added to the same base field and played full sandboxed tournaments.
Reproduce with `scripts/ablation_personas.py`.

| | persona mix (what the league wrote) | all-generalist |
|---|---|---|
| bots written / generator calls | 22 / 26 | 26 / 26 |
| mean score of the arm's bots | 0.574 | 0.578 |
| places in the two top fives | 10 | 10 |
| unique coverage, ≥ 1 of 10 seeds | 0 | 0 |
| unique coverage, ≥ 5 of 10 seeds | 1 | 1 |
| unique coverage, ≥ 8 of 10 seeds | 3 | 0 |
| retired by the real league so far | 0 of 22 | not simulated |

**Caveats that always apply.** The generalist's evidence includes the top three opponents'
self-descriptions, which after the first night include bots the persona mix wrote, so the
arms are not fully independent. The generalist arm is played against the base field once,
not run night by night, so its retirement can't be measured. Coverage differences of one or
two opponents are within what a single bot changes.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits).
