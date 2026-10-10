# Decisions taken alone (charter section 1), with the reason

- **2026-10-03 — cache key uses the rules actually in force, not `rules.py`'s bytes.** Key =
  (attacker sha256, defender sha256, seed, sha256 of the canonical JSON of the Rules object
  passed to the match, engine version). Season-two candidates pass tuned Rules objects that
  never touch `rules.py`, so a file hash would serve season-one results to a candidate run.
  Engine version = sha256 over sim.py, policy.py, sandbox.py and sandbox_runner.py.
- **2026-10-03 — the daily session's allow-list has no raw `docker`.** `docker run -v /:/host`
  is root on the box, which would make the "never touch /etc" guardrail meaningless. The
  project's own commands (tournament, submit, clip) still use the sandbox internally.
- **2026-10-03 — rotation keeps every replay of the current roster.** With a cache, a pairing
  that doesn't rerun never rewrites its replay, so a 14-day mtime rule would delete the only
  replay of a live matchup.
- **2026-10-03 — contrarian's "number one" is its target, the opposing #1.** Charter 3.2 says the contrarian sees "the number one's source and nothing else"; its target was already the opposing #1, so that's the source it gets. Its goal no longer says "unlike the bots described above", since it sees none.
- **2026-10-03 — what the daily session's 200k token cap counts.** New input + cache writes + output, the same things a league call consists of. An agentic session re-reads its own context every turn; counting those cache reads would put a 2-hour session in the millions and trip the cap on day one for arithmetic, not use. They are recorded (`tokens_incl_cache_reads`), not capped. `--max-budget-usd 5` (notional, not billed) is the in-session runaway backstop.
- **2026-10-03 (daily session) — the tactic library is written to `out/library/`, not a
  tracked `library/`.** It is derived from league data (ladders, breach tables, replays) and
  goes stale every night, and its replay links point into `out/replays/`. It sits beside
  `out/site/` and is rebuilt the same way, never committed. `--out` takes any path.
- **2026-10-03 (daily session) — who gets a tactic card.** Top five of its ladder on any
  night in `out/history/` or on the current ladder, or unique coverage (`unique_coverage`)
  in the latest breach table. "Beats" means it wins more than half the seeds against that
  opponent on the last night it played; "beaten by" means it wins fewer than half. Best and
  worst replay come only from pairings in the current roster, so dry-run and retired
  opponents never appear.
- **2026-10-03 (daily session) — tactic families, from what season one actually produced.**
  Attackers: saturation, synchronised arrival, decoy screening, trickle. Defenders: identify
  first, patient defence (blast packing), budgeted defence, value-model optimisation,
  controls. They're a hand-kept table in `colosseum/library.py`. A new bot goes to
  "Unsorted" until someone places it there; the index says so. A test checks that every
  member is a real bot on its own side and sits in only one family.
- **2026-10-03 (daily session) — 3.9 uses a seeded standard-library fuzzer, not
  `hypothesis`.** The charter allows either. Each trajectory comes from one integer, so a
  failure replays with `python3 -m colosseum.fuzz --start <n> --n 1`. Nothing new gets
  installed, and the daily session's allow-list already had `python3 -m colosseum.fuzz*`.
  What it gives up is shrinking. A failing trajectory is short enough to read anyway.
- **2026-10-03 (daily session) — the fuzzer also sends malformed actions** (about 1 in 8:
  NaN, ±Infinity, integers too large for a float, wrong types, unknown ids). The charter asks
  for "random valid action streams". The bug it found is in the invalid ones. Everything
  json.loads accepts can come back from the container, and policy.py promises that a bot
  can never crash a match.
- **2026-10-03 (daily session) — engine fix: the sanitiser rejects non-finite numbers.** A
  bearing or waypoint has to be a finite number. An id that is infinite or overflows counts
  as invalid. Finite actions are cleaned exactly as before (there's a test for it), and bool
  is still accepted as a number. Engine version changes, so the cache goes cold for one night.
  That is expected.
- **2026-10-03 (daily session) — 500 fuzz trajectories a night, as an after-night step**
  (`ops.nightly_fuzz`, ~35 s). Numbered from the date (YYYYMMDD × 10000), so every night
  covers new ones. One line a night goes to `out/fuzz.jsonl`. A failure writes ALERT.md
  through the existing after-night path. It doesn't touch the league result. The test suite
  runs 60 (a few seconds).
- **2026-10-03 (build session) — workshop bots run in-process, like the baselines.** The
  starters and solutions in `workshop/` are written and reviewed in the repository, the
  same as `bots/attackers` and `bots/defenders`. They are not league or submitted output,
  so `load_policy` runs them on the host and the tests use them directly. A student's own
  file runs in-process only on the student's own laptop (3.11: no Docker there). It
  passes `submit.check_source` first, and `kit.py` refuses `bots/house` and `bots/submitted`.
  Untrusted bots still never take this path.
- **2026-10-03 (founder) — scope.** The project's scope is the open benchmark, the tactic
  library and the student workshop. It is not the evaluation of real defence systems. Any
  item that points the other way is raised with the founder before work starts.
- **2026-10-03 (founder) — safety stops are walls, not obstacles.** An item or a generated
  output that trips a safety stop is stopped, written up with its flag (CONTENT: or
  SECURITY:), and left; never rephrased to get past the stop.
- **2026-10-04 — S0-2 verdict not executed mechanically.** At real night 7 the watch test passed (4 defenders hold synchronized_ring under 90%) but the role test failed on the *defender* side (61.6%). The charter's literal branch (A + gun-rate fix) would widen that imbalance. Nothing is due before 2026-10-26, so the season-two content is put to the founder as a yes/no instead of being picked silently.
- **2026-10-04 (founder) — season two is candidate A only.** S0-2 was answered in play; no
  economy fix. The 62% / 91% defender lean is logged as S0-3, with a 7-night watch on
  convergence_blast_scheduler from 2026-10-05 under the S0-2 rule. The pre-decided role test
  now reads "inside 40–60 in either direction".
- **2026-10-04 (founder) — item G scrapped as a prompt rewrite.** The current prompts stay for
  the rest of season one. Only the content-check filter remains, as a wiring item; if it
  trips a stop it's dropped.
- **2026-10-04 (founder) — public commit identity:** Vikram Goel, GitHub noreply address (`scripts/public_identity`), applied only in the publish mirror by `scripts/rewrite_identity.sh`; the live repo keeps its history.
- **2026-10-04 — L9 PR submissions: the inbox is `bots/submitted/pr/<login>/<NAME>.py`.** It's
  under `bots/submitted/`, so `is_untrusted` already covers it, and `policy.py` (part of the
  engine version) didn't have to change. The tournament doesn't search it. CI is static only
  (`pull_request`, read-only, no secrets, no Docker, PR text only via env). Its verdict is
  advisory, because a PR can edit its own workflow. The binding checks are `submit_pr intake`,
  run from master on the league machine. The handle is the PR author's login, so nobody can
  submit into someone else's folder.
- **2026-10-08 — build sessions paused for the final sprint run.** The founder asked for L10 and L13–L16 to be worked continuously in one session by 03:00 UTC 10-09. The 2-hourly sessions (hygiene only since 10-07) would race these commits to master, so their cron entry is commented out until L16 is written, then restored. The league and the ablation session keep running.
- **2026-10-08 (founder) — licences:** Apache-2.0 for code (`LICENSE`, the official text, sha256 cfc7749b…), CC BY 4.0 for replays, results and research (`LICENSE-CC-BY-4.0`, the official legal code). Folder split in `LICENSING.md`; submitted bots are contributed under Apache-2.0. Repo: `goel12133/swarm-colosseum`, public, created by the founder on launch day.
- **2026-10-08 — L15 screenshots cover every page except the replay pages, plus three of those.** The bundle has 2,160 replay pages that are one viewer page with different data; screenshotting all of them adds ~40 minutes and shows nothing new. Every other page (home, ladders, every bot page, library cards, research, seasons, submit, about) is captured at 390 px in dark mode.

- 2026-10-08 07:0x (lead engineer): build-session cron restored after L16, as logged when it
  was paused. Left as a gap, not fixed: replay pages have no link back to the site, because
  viewer/template.html is also the clip renderer's page and a header change would change the
  clips. The default domain stays goel12133.github.io/swarm-colosseum until the founder says
  otherwise.

- 2026-10-10 03:0x (lead engineer), launch: the founder said the repo exists and the deploy
  key is installed; neither checks out (repo 404 to the owner's own gh login, no key file on
  the box). Default: do not create the repo or a key myself (both are founder actions on his
  account, and he may have made them somewhere else), push nowhere, finish everything that
  doesn't need the remote, write it up. The gh login (goel12133, scopes gist/read:org/repo)
  was used only for read-only lookups; I never read its token file.
- Submissions-open date (founder: "<your date>"): **Sat 2026-10-24**, with 3.8 that evening
  (default 19:00 founder's time). Saturday because he has limited weekday time; two days before
  the boundary so outside bots join on the first night of season two (2026-10-26) and don't
  touch season one's final standings. They open only if 3.8 passes; otherwise the page moves
  the date.
- Nightly republish ("pull main and republish"): after-night fetches the public main and
  republishes only if it is still what we last pushed (out/publish.json), else it alerts and
  pushes nothing. Merged submission PRs can't be pulled back into master yet: the public
  history is a rewrite of master, so a GitHub merge on top of it can't fast-forward back.
  That fold-back is built with 3.8, before 2026-10-24; until then nobody merges on GitHub.

- 2026-10-10 04:4x (lead engineer), custom domain: README, CITATION.cff, the summary and
  the site held no absolute URLs (the site links are all relative, which is right under a
  custom domain), so "update every absolute URL" became adding them: CITATION url +
  repository-code, one line in README and in the summary. Historical records (PROGRESS,
  DECISIONS, LAUNCH_READY, DAILY) keep the old github.io mention as written. GitHub Pages
  was not enabled on the repo (has_pages false); I enable it through the API with
  source gh-pages / root and cname pelennor.tech, as part of the approved publish.
