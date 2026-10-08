# Contributing to Swarm Colosseum

Thanks for looking. This is an abstract strategy game and research benchmark. These are the
rules every contribution follows, then what we can accept right now.

## The rules

1. **Abstract only.** Made-up units (`u`, `ticks`, `credits`) on a blank plane. No real
   weapons, vehicles, units, places, armies or companies, and nothing from non-public
   information, anywhere: code, bots, docstrings, issues, docs. A contribution that breaks
   this is closed without review. Bot names and docstrings describe the idea in game terms
   ("hold the swarm outside identification range, then release it on one tick").
2. **Untrusted code never runs outside the sandbox.** Bots that aren't part of the
   baselines are read with `ast` and never imported on the host. Tests follow the same rule:
   a test may run a bot in-process only if it is a fixture or baseline from this repo.
3. **Determinism.** The same attacker, defender, seed, rules and engine give byte-identical
   results and replays: in-process, sandboxed, in parallel and from the cache. The tests
   that prove this stay green.
4. **The rules are frozen for a season.** `colosseum/rules.py` changes only at a season
   boundary ([SEASON.md](SEASON.md)). Balance ideas for next season are welcome as issues.
5. **Tests before claims.** A change says what it does, and comes with a test that shows it.

## What we accept now

- **Bug reports.** Include the command you ran, what it printed, and (for match bugs) the
  attacker, defender and seed: that is enough to replay the match exactly.
- **Bug fixes and tests.** `python -m pytest tests -q` must pass. An engine fix changes the
  engine version and invalidates the result cache; that is expected. Please say so in the
  pull request.
- **Docs, the workshop, the viewer.** Plain language, readable by a sixteen-year-old.
- **Bots: not yet.** Outside submissions are closed. [SUBMITTING.md](SUBMITTING.md) explains
  the interface and the checks, so you can get a bot ready and test it on your own machine.
  When they open, a bot arrives as a pull request that adds only
  `bots/submitted/pr/<your login>/<NAME>.py`. The workflow in
  [.github/workflows/submission.yml](.github/workflows/submission.yml) runs
  `python -m colosseum.submit_pr check` on it, which reads the file and never runs it. After
  merge, `python -m colosseum.submit_pr intake` on the league machine repeats the checks and
  runs the test match in the sandbox.

## Security

If you find a way for a bot to get out of the sandbox or past the checks, please don't post
the details in a public issue. Open an issue that says only that you have a security report,
and a maintainer will contact you.

## Licence

Code contributions, including bots, are accepted under the [Apache License 2.0](LICENSE).
Written research and replays are under [CC BY 4.0](LICENSE-CC-BY-4.0). The folder-by-folder
split is in [LICENSING.md](LICENSING.md).
