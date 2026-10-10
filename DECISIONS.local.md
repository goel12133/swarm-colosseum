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

- 2026-10-10 05:xx (lead engineer), site trim: the rule is as specified (full pages for
  matches first played this week or last, plus each live bot's best and worst; a match is
  dated by the later of its two bots' first nights). Two deviations, because the rule alone
  can't reach 60 MB: (1) the "raw JSON" served for the rest is the replay packed
  (positions as per-id deltas in 0.1 u, gzipped; colosseum/replay_pack.py, unpack command
  documented on the replays page): the plain JSON alone is 151 MB; (2) full pages no longer
  embed the replay, they load the same packed file in the shared viewer (an iframe), else
  this week's and last week's pages alone (all 2,800 today) are 190 MB. Before 191.0 MB,
  after 20.5 MB; projected ~39 MB at the boundary. after-night alerts above 60 MB but still
  publishes. The rehearsal's screenshots now go through a loopback server inside the
  --network none container (no host port).

- 2026-10-10 05:xx (lead engineer), fold-back, three departures from the sketch:
  (1) new commits are found by ancestry (public main minus our last publish), not by "not
  authored by the publish identity": a contributor can put any author on a commit, and the
  founder's own GitHub merges carry the publish identity; (2) the allowed shape is
  bots/submitted/pr/<handle>/<NAME>.py, regular files only, not all of bots/submitted/:
  writing straight into bots/submitted/<role>/ would skip intake's sandbox test; (3) once a
  PR is merged on GitHub, public main can't fast-forward to the rewritten master again, so
  every later publish is a merge commit (our tree, parents: public main and master) via
  publish.sh --merge-onto. No force push, ever. A rejected batch alerts and blocks the
  republish until a person reverts it on GitHub. Ships with ops.FOLDBACK_ENABLED = False.

- 2026-10-10 05:xx (lead engineer), post-launch build sessions: BUILD_ITEMS are now P5, W,
  3.13, 3.14 and hygiene, and the wrapper refuses to merge a session branch that touches a
  protected file (publish, audit, identity, allow-list, daily, ops, fold-back, sandbox,
  submit, policy, rules, sim, .github, CHARTER), because every merge is public the next
  night. P1-P3 were done interactively today. P4 (the boundary) is a scripted after-night
  step, not a session item: it needs a branch merge, which sessions may not make, and a
  rules change should come from a branch that was reviewed and tested in advance.

- 2026-10-10 06:xx (lead engineer), the boundary runs at the start of the 2026-10-26 night,
  not after the 10-25 night: SEASON.md says candidate A merges "on 2026-10-26, not before".
  The prepared branch is `season2` (current master + `s2-a-imperfect-id` + the bumps: rules
  SEASON = 1, sim and tournament write `season: 1`, season.py and SEASON.md for 10-26 to
  11-22); not `season2-candidates`, which has the write-ups but not A's code, and not
  `s2-a-economy` (the gun-rate lever the founder declined). "Reset Elo" needs no step: Elo
  is rebuilt from 1000 each night and every match replays under the new rules. If the
  boundary fails, that night's league is skipped rather than playing a 29th season-one
  night. A one-seed rehearsal of season two's first night on today's roster: 280 matches,
  no bot scoring zero, so no baseline needs re-tuning.

- 2026-10-10 08:xx (lead engineer), design pass from goel12133/swarm-design-ref. Notes:
  - There was no zip in the repo: the plain HTML and CSS were in
    swarm-colosseum-source/public/site/ (next to a React scaffold), so that folder is
    design_ref/, gitignored.
  - "Live": nothing in Swarm Colosseum is live (the league plays at 03:30 UTC, sandboxed),
    and there was no live channel in the code. The header indicator and the broadcast
    frame are therefore a replay channel of last night's featured matches (#1 v #1, each
    new bot's best match, the night's upset), played on a clock every visitor shares and
    labelled REPLAY, with a line saying it is not a live feed.
  - Fonts are self-hosted (OFL), not Google Fonts: no outside request from any page, as
    before.
  - One small site.js (theme, sorting, frame height, header line); every page works
    without it.
  - Theme follows the system until the visitor picks one (the reference defaulted to
    dark).
  - Kept from the founder's earlier instructions over the mock-up's wording: the licence
    footer text, and the abstract-only sentence on the home page.
  - "Counters found unaided" has no data source here, so the figure is "house bots that
    beat the bot they were written to beat" (from the ledger).
