# Roadmap

Stage 1 is done: deterministic engine, nine baseline bots, round-robin tournament with two Elo
ladders, replays, a viewer, and a balance pass. **Stage 2 is not started.**

## Stage 2 — outside submissions and a nightly league

Nothing here should be built until the sandbox exists, because every other item on the list
assumes it.

1. **Docker sandbox.** The blocking item. Untrusted code must never run on a public path
   unsandboxed: no network, a CPU and memory cap, a per-tick timeout, a read-only filesystem
   except a scratch directory, and no access to the host clock beyond what the engine passes
   in. The engine already treats a policy as hostile in the sense that it cannot crash a match;
   the sandbox is what stops it being hostile to the machine.
2. **Nightly house league.** Headless Claude reads the leaderboard, the matrix and a sample of
   replays, writes new bots into `bots/house/`, and the tournament reruns. Needs: a spend cap
   per night, a hard limit on how many bots it may add, and the same determinism guarantee, so
   a house bot that wins can be reproduced exactly. House bots go through the same sandbox as
   anyone else's.
3. **Weekly meta report.** What beat what, which tactics appeared, which rule is currently
   doing the most work. Generated from the matrix and replays, not written by hand.
4. **Replay clips to video.** Render a replay to mp4 headlessly so a match can be posted
   without asking anyone to open a viewer.
5. **Public site — only after the founder approves.** No ports opened, nothing deployed, and no
   submission endpoint before the sandbox is done and reviewed.

## Stage 3

3D physics, richer sensor models (false tracks, dropouts, clutter), and a paid API for a
company to test its own defence logic against the accumulated attack library.

## Known open questions from Stage 1

- **`flanker` wins 0% of its matches.** Spreading out to survive blasts costs more saturation
  than it saves, because the blast radius is 10 u against a 490 u approach. Either the bot
  needs a better idea or the blast rules need to make clumping more dangerous — worth deciding
  deliberately rather than by tuning.
- **The gun is the strongest single rule.** The balance pass cut ammunition from 400 to 120
  precisely because an effectively unlimited magazine made identification risk-free. Gun range
  and rate of fire have not been tuned and are the obvious next levers.
- **Two decoy strategies are not enough** to tell whether decoys are priced correctly at 0.5.
  A bot that mixes decoys adaptively, rather than in a fixed opening screen, would test it.
