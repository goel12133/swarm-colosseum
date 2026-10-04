# 01 · The league found two counters it wasn't told about

*Swarm Colosseum, season one, nights 2026-09-29 to 2026-10-02. Every number below comes from
the league's own records (`out/breaches.json`, `out/matrix.json`, each bot's `.meta.json`)
and can be regenerated with `make reproduce`.*

**The setup.** Every night the house league asks a language model to write new bots. One
persona, *counter-meta*, is shown the current #1 bot on the other side and told to beat it.
It is not told how. Its evidence is the target's full source, the target's score against
each opponent, and the matches where the target came closest to losing.

## Case 1 — a defender that ignored decoys (beaten on 2026-09-29)

**The target.** `discriminating_ledger` engaged only strikers it had positively identified,
so decoys cost it nothing. No attacker in the field had ever destroyed the asset against it:
0 breaches in 60 matches.

**What the generator was shown.** Its source, and its three closest calls: matches against
`multi_axis` where its interceptor stock reached zero and strikers arriving together got past
the gun.

**What it wrote.** `synchronized_ring`. It holds all 30 strikers just outside the range at
which the ledger starts to engage unknown tracks (a threshold it read off the source), then
releases them all on one tick. The 20 interceptors run out and the survivors arrive
together, faster than one gun can answer. In its own words: *"Stock hit 0 and strikers leaked
… arriving at nearly the same time … multi_axis did that partly by accident … We do it on
purpose."*

**Result.** It breached the ledger in **10 of 10** seeds. It was the first attacker ever to
breach it, and it went straight to #1 on its ladder (98% win rate).
Clip: `out/research/clips/case1_ring_vs_ledger.mp4`.

## Case 2 — an attacker that beat every defender (answered on 2026-10-01 and 10-02)

**The target.** `synchronized_ring` itself, by then breaching every defender in 9 or 10 of
10 seeds. The league's escalation rule gave both of the next two nights' bots to defenders
aimed at it.

**What the generators were shown.** Its source, its per-defender scores, and its closest
calls (its best defender, `identify_then_engage`, had held it in one seed out of ten).

**What they wrote.** Both reasoned from geometry, not tactics. Released together and flying
straight in, the 30 strikers form a circle that shrinks; below a radius of about 48 the gap
between neighbours is smaller than one blast. `convergence_blast_scheduler` holds its
interceptors until then, and `loiter_then_collapse` keeps them waiting over the asset and
fires them all into the closing ring. *"Each blast covers three strikers."*

**Result.** `convergence_blast_scheduler` cut the ring's success against it to **4 of 10**.
`loiter_then_collapse` cut it to **1 of 10** and beat the ring on score (0.647). The ring's
overall win rate fell from 98% to 86%, and the founder's pre-registered test ("can any
defender hold it under 90%?") came back yes on the second of its seven nights.
Clip: `out/research/clips/case2_collapse_vs_ring.mp4`.

## Honest limits

- **This is directed search, not open-ended discovery.** Both counters came from the
  counter-meta persona, which was handed the target's source code and its closest losses.
  The league chose *what* to attack and *what evidence to show*; the model found *how*. In
  case 1 the decisive hint (stock running out against arrivals bunched in time) was already
  in the near-miss matches shown to it. In case 2 the counters came from reading the
  target's source.
- **Two cases, one model family, 10 seeds a pairing.** That's enough to show the mechanism
  works, not to estimate how often it does.
- **Not every attempt produced a bot.** Of the four escalation calls on 10-01 and 10-02, two
  returned no bot (the model declined to write one), so the two answers above came from two
  of four tries.
- **The counters are narrow.** Each beats its target and does well against the field, but
  this is a ladder of specialists, not a solved game.

The arena is an abstract strategy game with made-up units (`u`, ticks, credits). Nothing
here describes or predicts any real system.
