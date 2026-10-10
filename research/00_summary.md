# Swarm Colosseum in one page

**What it is.** An open research benchmark built as a strategy game. Two kinds of short
Python program play each other: *attackers*, which spend a budget of credits on cheap
strikers and decoys, and *defenders*, which hold a limited stock of interceptors and a gun.
Every match is deterministic, sandboxed and replayable, on a blank 2D board in made-up units.
Defenders are scored on what they spend as well as what they save, so the interesting
question is cheap moves against expensive answers.

**Why it exists.** To find out what a self-playing league of language-model-written programs
can discover about a game, and to show that discovery in a form anyone can check. Every
result can be rebuilt from the committed bots and seeds with one command
(`make reproduce`, byte-identical; about 17 minutes on 4 cores at night 11, growing
with the roster).

**What the league does every night.** It reads the standings, asks a language model to write
new bots through four *personas* (each shown different evidence), validates each bot without
running it on the host, and plays every bot against every opponent ten times inside
containers. It then publishes the ladders, the matrix, the replays, a tactic library, and a
weekly report. Eleven nights in: 18 house bots alongside the baselines, 3,330 matches on
record, about 408,000 model tokens.

**Three headline results.**

1. **The league found counters nobody told it about.** A bot that ignored decoys had never
   been beaten; the league wrote one that beat it in 10 of 10 matches. That bot then beat
   every defender; two nights later the league found its answer, a geometric weakness in a
   synchronised release. ([01](01_unaided_discovery.md))
2. **Self-play exposes the designer's mistakes.** Four design findings, from an unlimited
   fallback that made waiting free to identification so early that deception was worthless,
   led to a tested, measured rules change for season two. ([02](02_balance_findings.md))
3. **Two modest results, reported as found.** A joint optimiser beat a greedy pick using the
   same value model against 9 of 14 attackers, but its average lead is small and uncertain
   and one attacker breaks it ([04](04_annealed_defenders.md)); and writing bots through four
   personas did no measurably better than writing them all one way
   ([03](03_persona_ablation.md), preliminary).

**What is honest about its limits.** The discoveries are *directed* search: the persona that
found them was handed its target's source code. A plain generalist found the first one too,
so the counter was easier to find than "unaided" suggests. The samples are small (two
discovery cases, five to eleven nights, ten seeds a pairing, one model family). Some
generation attempts were declined by the model. The game is balanced only approximately:
defenders currently win about two matches in three, a lean the league is being given time to
answer. And it is a game. Nothing here describes, models or predicts any real system.

**What is next.** Season two (from 2026-10-26) makes identification take time and sometimes
be wrong, so that deception matters. A full 14-night persona comparison starts on 2026-10-11. A
90-minute workshop lets first-time Python students write and test a bot on their own laptop,
and outside submissions open through pull requests on 2026-10-24, once the sandbox has
been reviewed.

---

Code: Apache-2.0. Replays, results and research: CC BY 4.0. Built by Pelennor.
