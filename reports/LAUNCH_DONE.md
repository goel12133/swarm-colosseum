# Launch done — 2026-10-10

**Live:**
- Site: <https://pelennor.tech> (HTTPS enforced; `www` redirects to the apex)
- Code: <https://github.com/goel12133/swarm-colosseum>, public; `main` and `gh-pages`
- First publish: 04:37 UTC, main `dfa3668`, gh-pages `4ba87cb` (`out/publish.json`)

**Checked after the publish:**
- **Leak rescan of a fresh public clone:** `scripts/audit_secrets.py`, now with
  personal-email and identity checks, covered all 168 commits and 3,491 file versions on
  `main` and `gh-pages`. Nothing found. The only identities are the noreply address, the
  league's and the dev one, and the personal address is in 0 commits.
- **Test PR [#1](https://github.com/goel12133/swarm-colosseum/pull/1):** it added
  `bots/submitted/pr/goel12133/launch_check.py`. The `submission` static check went green
  in 9 s. The PR was then closed unmerged and its branch deleted.
- **Pages:** "pages build and deployment" succeeded; the certificate was approved and
  HTTPS enforced. `CNAME` (exactly `pelennor.tech`) is written by every site build, so every
  publish keeps it.
- **Nightly republish is armed:** after-night runs `publish` after the site step. It pushes
  only if the public `main` is still what `out/publish.json` says we pushed.

**First night (check on the morning of 2026-10-11):** LAUNCH_CHECKLIST step 9.
- No `out/ALERT.md`; `out/house_league.cron.log` shows `"publish": "published: …"`.
- `out/publish.json` matches `git ls-remote` for main and gh-pages.
- Public `main` has the "Night 2026-10-11" commit; the ladders on pelennor.tech show 10-11.
- Actions: pages build green, no `submission` run.
- The fresh-clone audit is still clean.

**What didn't go to plan:**
- **The first attempt, at 03:05, stopped before step 1.** The repo didn't exist yet and
  there was no deploy key on the box. Nothing was pushed until the founder had created both
  (04:33).
- **Pages turned itself on** when gh-pages arrived, so the API's "enable" returned 409. The
  domain and HTTPS were set through the API instead.
- **README, CITATION.cff, the summary and the site held no absolute URLs to change.** The site
  links are relative, which suits a custom domain, so the site and repo URLs were added to the
  first three instead.
- **The new audit caught a false positive before anything went public:** gmail-shaped
  strings in its own test file. They were rewritten on the unmerged branch, so they never
  reached master or the public history.
- **A published claim was corrected before launch.** research/04's four-night "the
  optimiser adds no reliable value" was revised by the 11-night ablation (3.5), and the
  public site went out with the corrected version.

**Not yet:**
- **Merging a PR on GitHub stops the nightly republish.** Public `main` would then differ
  from what we pushed, so the night alerts and pushes nothing. Folding merged PRs back into
  master is built with 3.8, before submissions open (Sat 2026-10-24; 3.8 that evening).
  Until then: don't merge on GitHub.
- **The site is 191 MB** (2,800 replay pages), and it grows with the roster. Trim before
  season two.
- **GitHub keeps PR #1's head ref** (`refs/pull/1/head`, the test bot). It can't be deleted
  and is harmless.
