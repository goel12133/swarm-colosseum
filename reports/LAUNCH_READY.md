# Launch ready — 2026-10-08 (sprint L16)
**Ready:** L1–L15 done; 353 tests pass; the rehearsal on a fresh clone passed 10 of 10 steps (`make reproduce` identical in 999 s, publish to a local bare remote ok). Nothing has been pushed or served yet.
**Look at** (phone width, dark mode, `out/launch_screens/`): `index.png`, `research__00_summary.png`, `ladders.png`, `submitting.png`, `library__index.png`, `about.png`; the other 50 are there if you want them.
**Your decisions:** licence (done: Apache-2.0 code, CC BY 4.0 replays and research), repo (done: `goel12133/swarm-colosseum`, public). Still open: **domain**. The default is `goel12133.github.io/swarm-colosseum`, which needs nothing from you.
**Launch day, in order** (details in LAUNCH_CHECKLIST 4–7), any day after the 03:30 night has committed (~05:00 UTC):
1. GitHub → New repository `goel12133/swarm-colosseum`, Public, empty (no README, no licence, no .gitignore).
2. `ssh-keygen -t ed25519 -N "" -f ~/.ssh/swarm_colosseum_deploy -C swarm-colosseum-deploy`; add the `.pub` as a deploy key with write access.
3. `cd /root/swarm-colosseum && scripts/publish.sh --live git@github.com:goel12133/swarm-colosseum.git ~/.ssh/swarm_colosseum_deploy`
4. Settings → Pages → Deploy from branch `gh-pages` / root. Then open the site on your phone and check the Actions tab.
**Not ready, and why:**
- Outside submissions stay closed until 3.8 (sandbox hardening, interactive-only) is reviewed. The pages already say "not open yet".
- The PR check workflow has never run on GitHub; there is no repo for it to run on yet.
- The site is 143 MB (2,160 replay pages). That is under the GitHub Pages limits, but the first push is slow.
- Replay pages have no link back to the site (use the back button). The viewer is shared with the clip renderer, so I left it alone.
- The persona result is preliminary: the 14-night run starts 2026-10-11.
