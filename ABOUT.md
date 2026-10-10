# About Swarm Colosseum

## What this is

Swarm Colosseum is a strategy game played by computer programs. One side, the
**attacker**, sends a swarm of small drones at something in the middle of the map. The
other side, the **defender**, tries to protect it. Both sides are short Python programs
called **bots**. Nobody steers anything by hand: each bot looks at the map every turn and
decides what to do on its own.

Every night every attacker plays every defender, and the results go on two ladders, one
per side. Swarm Colosseum is built by Pelennor.

## Why it exists

Some games are interesting because there is no single best move, only moves that are good
against what the other side is doing. This is one of them. Sending everything at once
beats some defenders and loses badly to others. Holding fire looks wasteful until it
suddenly isn't.

We want to find out which ideas actually work, and keep a record of them. That record is
the **tactic library**: one page per idea that earned a place, with what it beats, what
beats it, and the code. Some of the bots are written by people, and many are written every
night by an AI model that reads the ladder and tries to beat the current leaders. Seeing
what the AI comes up with, and what people come up with, is part of the experiment.

## How a match works

- The map is a flat, empty square. In the middle is the **asset**, with **30 HP**.
- The attacker has **60 credits** to spend. A **striker** costs 2 and does 10 damage if it
  reaches the asset. A **decoy** costs 0.5 and does no damage. Both fly at the same speed
  and look the same on radar until they get close, so the defender has to guess.
- The defender has **20 interceptors** (fast, they explode near a drone), a short-range
  **gun** with 120 rounds, and a **radar** that sees far but can only tell a striker from a
  decoy inside 150 u.
- Time moves in **ticks**. On each tick both bots see the map and answer with their moves.
  A match lasts at most **600 ticks**.
- The attacker wins a match if enough strikers get through to bring the asset down to
  0 HP (we call that a **breach**; three strikers do it). The defender wins if the asset
  still has any HP left when the match ends.
- The defender is also scored on **cost**. An interceptor costs 4 credits. Spending one on a
  0.5-credit decoy is a bad trade, even if it hits.

The same two bots with the same **seed** (a number that fixes the random parts, like
whether an interceptor hits) always play exactly the same match. So any result can be
checked by anyone, and every match is saved as a **replay** you can watch.

## How to read the ladder

Each side has its own ladder, best at the top.

- **Elo** is the rating. Everyone starts at 1000. Beat a strong bot and you go up a lot;
  lose to a weak one and you go down a lot. Only the order matters, not the exact number.
- **Wins** is how often the bot won its matches in the latest tournament.
- **Mean score** is the average match score, from 0 to 1. A defender's score counts both
  how much of the asset survived and whether it spent less than it shot down, so a
  defender can win the match and still score badly by wasting interceptors.
- The tag after the name says where the bot came from: **baseline** (hand-written by us, to
  anchor the ladder), **house** (written by the AI league), or **submitted** (sent in by
  someone).

Click a bot's name to see what it says it does, how it does against every opponent, and
links to its matches.

## How to submit

Not yet. Submissions open on Saturday 2026-10-24, after the sandbox has been reviewed
that evening. When they open, you will write one Python file with a
function called `act` that gets the map and returns your moves. The
[Submit a bot](SUBMITTING.md) page already explains the whole thing, including a complete first bot you can copy, so you can
get one ready now and test it on your own computer.

## Abstract only, and why

A swarm attacking something sounds military, and we won't pretend it doesn't. So here is
the rule we hold ourselves to: **everything in the game is made up.** Distances are in
`u`, time in `ticks`, money in `credits`. No real weapons, vehicles, places, armies or
companies appear anywhere, in the code, the bots, the reports or this site, and nothing
in it comes from secret or private information.

The numbers were chosen to make a good game, not to copy anything real. A tactic that
works here works in this game; we make no claim that it says anything about the real
world, and you shouldn't read it that way. Think of it like chess: the pieces are called
knights and bishops, but nobody learns to fight from playing it.

If a bot written by the AI ever mentions a real system, it is thrown out and never
published.
