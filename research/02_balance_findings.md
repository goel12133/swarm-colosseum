# 02 · What a self-play league teaches you about your own game

*Swarm Colosseum, season one. Rules are frozen for a season; findings are logged in
`BALANCE.md` and acted on only between seasons. Numbers are from the league's records and
the season-two test branches.*

A designer can't play their own game thousands of times a night. A league of bots can, and
it finds the degenerate strategy long before human players would. Season one produced four
findings, each the kind of thing that only shows up once something is optimising against
the rules.

## S0 — a free backstop made waiting free (fixed before the season)

With 400 gun rounds against a match of at most 600 ticks, the gun was effectively
unlimited, so a defender lost nothing by waiting to identify every unit before reacting.
`identify_then_engage` won **100%**. Cutting the magazine to 120 made rounds a resource to
budget, and the ladder opened up. *Lesson: an unlimited fallback removes the trade-off it sits
behind.*

## S0-1 — decoys were worthless against a patient defender

`discriminating_ledger` ignored everything it hadn't identified as a striker and was never
breached in 60 matches. Decoys bought attackers nothing: attackers that used none did as
well against it as those that used dozens. The cause wasn't the cost of decoys but the
timing. A unit is identified with about 31 ticks left, and an interceptor needs about 9, so
waiting cost the defender nothing. A leakage test confirmed the defender wasn't seeing
anything it shouldn't. *Lesson: if certainty arrives in time, deception has no value; the fix
belongs to identification, not to prices.*

## The winner that spent more than it saved

The same defender sat at #1 while spending more credits than it destroyed: its cost
exchange ratio was 0.49–0.75 against every attacker. That is exactly the outcome the game
exists to penalise. Two season-two candidates were tested, one at a time, against the full
field:
- **A, imperfect identification.** Identification takes 8 ticks of dwell and is wrong 8% of
  the time. No bot over 90%, roles near even, and the patient defender drops from 100% to 90%.
- **B, rescoring.** Score = survival × trade quality. It punished the patient defender but
  handed the game to attackers (61%) and created a new 98% bot.

**A was chosen for season two**, and B was rejected for creating the very imbalance it was
meant to cure. *Lesson: fix the mechanic the degenerate strategy exploits, not the
scoreboard that reports it.*

## S0-2 — the league broke the splash, then repaired it

A counter-meta bot learned to deny blast splash: 30 strikers spaced so no blast catches two,
released on one tick, so the 20 interceptors run out and the survivors arrive together. It
beat every defender (98%). Rather than change the rules at once, the founder gave the
league seven nights to answer, with a test registered in advance: does any defender hold it
under 90%? On the second night, two defenders found that a synchronised release contracts
into a tight circle and timed their blasts for it (see `01_unaided_discovery.md`).

The economy fixes were tested in parallel and none was needed. Only a faster gun (1.75
rounds a tick) passed all three balance tests, and adding ammunition did nothing because
ammunition was never the binding constraint. *Lesson: some apparent rules flaws are a meta
the league hasn't answered yet. Give it time before changing the game.*

**Status at real night 7 (2026-10-04):** answered in play. Four defenders hold the
synchronised wave under 90%, and its win rate is down to 83%. But the role share has swung
the other way: defenders now win 62% of matches, and one of the new defenders wins 91%. The
league answered the flaw and overshot. That is itself the next finding, and it gets the same
treatment: it's logged, and the league gets time to answer it.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits). These are
findings about a game's design, not about any real system.
