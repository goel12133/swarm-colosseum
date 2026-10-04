# 03 · Does persona diversity help? Not measurably, yet.

*PRELIMINARY: five nights (2026-09-29 to 10-03), ten generator slots per arm, 10 seeds per
pairing. From real night 14 a 14-night run is generated in its own session, a few slots a
night within the nightly token cap, and replaces this page automatically when complete.*

**The question.** The house league writes each night's bots through one of four personas,
each shown different evidence: *exploiter*, *counter-meta*, *generalist* and *contrarian*.
Does that mix find more distinct tactics than writing every bot as a generalist?

**The test.** For each of the five nights, every slot the real league filled (same side,
including the two extra slots on escalation nights) was refilled by the *generalist*
persona. It used the same evidence snapshot and the same generator, and each bot passed the
same validation and sandbox smoke test. Both sets of bots were then added to the same base
field (baselines plus the house bots from before 09-29) and played full tournaments in the
sandbox. Reproduce with `scripts/ablation_personas.py`.

## Results

| | persona mix (what the league wrote) | all-generalist |
|---|---|---|
| bots written / generator calls | 8 / 10 | 9 / 10 |
| mean score of the arm's bots | 0.654 | 0.651 |
| places in the two top fives | 7 | 8 |
| unique coverage, ≥ 1 of 10 seeds | 0 | 0 |
| unique coverage, ≥ 5 of 10 seeds | 0 | 1 |
| unique coverage, ≥ 8 of 10 seeds | 2 | 0 |

*Unique coverage* is the number of opponents that only this arm's bots can beat (an
attacker that breaches a defender nobody else breaches, or a defender that holds out against
an attacker nobody else holds). At "≥ 1 seed" almost every opponent is beaten by someone, so
the measure needs a stricter cut to say anything; at the stricter cuts the counts are too
small to separate the arms.

**The striking case.** On 09-29 the generalist attacker, shown only the win-rate matrix and
the top three defenders' self-descriptions, independently wrote the same headline idea as
that night's counter-meta bot (`01_unaided_discovery.md`, case 1). Its own words: *"Park
the whole force just outside radar range, then release every striker at once from evenly
spread bearings."* Two personas, with different evidence, found the same counter on the
same night.

## What this says, honestly

- **No measurable advantage for the persona mix** on five nights: equal mean score, a similar
  share of top-five places, and coverage differences of one or two opponents either way.
- **The arms aren't fully independent.** The generalist's evidence includes the top three
  opponents' docstrings, and from 09-30 on those include bots the persona mix wrote. Some of
  the generalist arm's later ideas may be borrowed rather than found. The 09-29 case is clean:
  the bots it could have borrowed from didn't exist yet.
- **Generation success was similar:** 9 of 10 generalist calls and 8 of 10 real persona calls
  produced a bot. The one failed generalist call returned no code; the response wasn't kept.
- **Five nights is a small sample** and retirement can't be measured yet (it needs three
  nights at the bottom). The 14-night run will report retirement too.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits).
