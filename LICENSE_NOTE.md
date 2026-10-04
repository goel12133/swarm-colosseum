# Licence: not chosen yet

There is no `LICENSE` file, so no licence is granted: the default is all rights reserved.
The founder chooses the licence (LAUNCH_CHECKLIST.md, step 3). This note is the
recommendation that step points to. It is not a licence.

## Recommendation

| what | licence | why |
|---|---|---|
| code: `colosseum/`, `viewer/`, `scripts/`, `tests/`, `workshop/`, baseline bots | **Apache-2.0** | permissive, so researchers and schools can use and change it; explicit patent grant; standard for benchmarks |
| written work: `research/`, `ABOUT.md`, the tactic library text, the site copy | **CC BY 4.0** | anyone may quote and republish the write-ups with credit |
| results and replays: `results/`, `out/replays/` | **CC BY 4.0** | the same; a benchmark's numbers should be freely citable |
| house bots (`bots/house/`) | same as the code | written by the league's generator for this project |
| submitted bots, once submissions open | same as the code, stated at submission | "inbound = outbound": submitters license their bot on the project's terms, so it can be shown, replayed and put in the library |

**Simpler alternative:** MIT for the code, same CC BY 4.0 for the rest. It is shorter, but
has no explicit patent grant.

## What happens once it's chosen

1. Add `LICENSE` (the code licence's full text) and, if CC BY is used, a short
   `LICENSE-docs` naming which folders it covers.
2. Add `license:` to `CITATION.cff` and replace this note's link in `README.md` and
   `CONTRIBUTING.md`.
3. Add one line to `SUBMITTING.md` saying which licence a submitted bot is under.
4. Delete this file.
