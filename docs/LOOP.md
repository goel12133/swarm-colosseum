# The loop

Swarm Colosseum improves itself on a schedule. Every three hours a fresh, headless Claude Code
session reads the repository, decides on the single most valuable thing to do for the goal
in `CLAUDE.md` (often nothing), does it on a branch, and exits. A wrapper, not the model,
decides whether the result reaches `master`. This page is for someone who has never seen it.

## When it runs

`scripts/crontab.txt` is the whole schedule, installed only by `scripts/cron_install.sh`,
which is run by hand with the founder's written yes:

| time (UTC) | job |
|---|---|
| 03:30 | the nightly league, then after-night (results, reports, site, republish) |
| 05:00 | the persona-ablation session |
| 00, 06, 09, 12, 15, 18, 21 | the loop (`scripts/daily.sh`); 03:00 is skipped because the league runs at 03:30 |

## One session

`scripts/daily.sh` runs `python -m colosseum.daily` (`run_day`). In order:

1. **Refuse to start** if the tool allow-list (`scripts/daily_allowlist.txt`) differs from its
   approved checksum, if the last session went over the token cap (200,000 new tokens), or
   if another session holds the lock (`out/daily/lock`).
2. **Prepare** the worktree `/srv/swarm-daily` on branch `daily-wip`, starting from `master`
   (or continuing unmerged work). Copy in the live data the tests read. Write
   `.loop/context.md`, covering:
   - the git log;
   - health;
   - last night's league log and ledger line;
   - the last publish;
   - the live site's home page as text;
   - `FOUNDER_TODO.md`, recent decisions and the last five sessions.

   Also generate `.loop/agents.json` and `.loop/plugin/` from `.claude/`.
3. **Run** `claude -p` with only the founder's prompt, inside the Ralph loop plugin, capped at
   two passes:

   > Read CLAUDE.md. Look at the repository, the git log, the live site and last night's
   > league log as if for the first time. Do the single most valuable thing for the goal,
   > or nothing. Commit. Exit without asking anything.

   The session is headless and restricted:
   - its file tools are confined to the worktree;
   - permissions are the allow-list, under `dontAsk`, so anything not listed is refused
     without asking;
   - no MCP servers, and none of the user's own plugins or hooks;
   - it has a 2-hour wall clock and a notional $5 runaway stop.

   `--restricted` ignores settings files, so the project's setup is passed explicitly:
   `--settings`, `--agents` and two `--plugin-dir`s.
4. **Inside the session**, `CLAUDE.md`'s "Each session" runs four agents (`.claude/agents/`):

   | agent | tools | job |
   |---|---|---|
   | architect | Read, Grep, Glob | reads, picks one action or none, writes the SIGNAL line |
   | builder | Read, Write, Edit, Glob, Grep, Bash | does that action on the branch, commits |
   | test runner | Bash, Read, Grep, Glob | runs the full suite and the site build test; never edits |
   | reviewer | Read, Grep, Glob | PASS or BLOCK against the signal line, the rules and the diff |

   Two hooks (`.claude/settings.json`) run during the session:
   - after every edit, `scripts/fmt.py` strips trailing whitespace;
   - at every stop, `scripts/stop_check.sh` runs the suite and the site build test, and
     blocks the stop once if either is red.

   The Ralph loop plugin is vendored in `.claude/plugins/ralph-loop/` (Apache-2.0; its stop
   hook was changed to use python3 instead of jq, see its NOTICE).
5. **Merge or not.** The wrapper fast-forwards `master` only if all of these hold:
   - the reviewer's verdict, read from its Agent result in the transcript, is PASS;
   - nothing is left uncommitted, and no commit carries a trailer;
   - no protected file is touched (publishing, the audit, the sandbox, intake, rules,
     season, the loop's own setup, `DAILY.md`);
   - `CLAUDE.md` changed only by lines added to its Lessons section;
   - it rebased cleanly, and the full suite is green.

   Otherwise the branch waits, and a failure writes `out/ALERT.md`.
6. **Record.** One line in `out/daily/sessions.jsonl`, the full transcript in
   `out/daily/<date>T<hhmm>.jsonl`, and `DAILY.md` on master, written by the wrapper.

## Statuses

`merged` and `nothing` are healthy. `wip` waits for the next session. The rest need a look:
`unreviewed`, `blocked`, `trailer`, `protected`, `claude-md`, `dirty`, `red`, `conflict`,
`refused`.

## Doing things by hand

- Run one session now: `scripts/daily.sh` (it takes the lock like cron does).
- Check without running: `python -m colosseum.daily --check`.
- Read the last session: `tail -1 out/daily/sessions.jsonl`, then its transcript.
- Pause the loop: remove its line from `scripts/crontab.txt`, then
  `scripts/cron_install.sh --apply "<the yes>"`.
- In an interactive session in the repo, `.claude/commands/` gives `/health`,
  `/run-tests-and-merge`, `/publish`, `/weekly-report` and `/season-boundary-dry-run`. Each
  pre-computes its context with inline bash.

## What it may never do

`CLAUDE.md` holds the hard rules and the Lessons. Among them:
- no real-world content;
- untrusted bots never imported on the host;
- nothing new made public, and no new network paths;
- rules change only at a season boundary;
- no destructive git, no credentials;
- the league and its republish are never touched;
- a safety stop is final.

The items named on its SAFETY line are never started, in any wording. Anything only the
founder can do goes to `FOUNDER_TODO.md`, with the steps prepared. `CLAUDE.md`,
`FOUNDER_TODO.md`, `DECISIONS.local.md` and `.claude/` are kept out of the public repository
by the publish step.
