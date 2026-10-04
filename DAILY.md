# Daily — 2026-10-04 (third build session: L9, L12)

**Night:** 10-04 ok. 2 bots written, 0 rejected, 835.8 s. #1 attacker:
interleaved_shell_ring (Elo 1245).
**Alert:** none.
**Done:**
- L9: submissions by pull request, prepared but still closed.
  - A PR adds `bots/submitted/pr/<login>/<NAME>.py`.
  - CI (`.github/workflows/submission.yml`) runs static checks only and never runs the bot.
    It's read-only, with no secrets.
  - After merge, `python -m colosseum.submit_pr intake` re-checks each bot and runs the
    sandbox test match.
  - The workflow has never run on GitHub; there's no remote yet.
- L12: `workshop/TEACHERS.md`, the teacher's first page, linked from the README.
- 346 tests pass in 66 s.

**Next:** L10, the dry publish pipeline. It was skipped this session because the licence,
repo name and visibility are still yours to decide. Then L14.
**For you, when the repo is created:** turn on "require approval for first-time
contributors" for workflows.
**Your yes/no (still open):** licence (Apache-2.0 + CC BY 4.0 recommended); ROADMAP's
"paid API for a company" line: remove or rewrite?
**Open stops:** G prompt text is waiting on you. 3.8 is held for an interactive run.
