# Launch checklist — founder actions, in order

*Draft: L15 completes it. Nothing here has been run; each line is yours to do.*

1. ~~Move the stray env file out of the repo~~ **done by the founder 2026-10-04**; the working
   tree has no untracked files.
2. ~~Approve the history rewrite~~ **approved 2026-10-04**. Public identity, in
   `scripts/public_identity`: Vikram Goel, GitHub noreply address (no personal email in
   the public history). Nothing to do by hand: the publish step runs `scripts/rewrite_identity.sh`, which
   mirrors the repo into a fresh clone and rewrites `root@<host>` there only (the live repo is
   never rewritten), then `scripts/audit_secrets.py` must print "nothing found" before any push.
   To publish a different identity, edit `scripts/public_identity`.
3. ~~Choose a licence, repo name and visibility~~ **done 2026-10-08:** Apache-2.0 (code) + CC BY 4.0
   (replays, research); `goel12133/swarm-colosseum`, public.
4. **Launch day — create the repo:** on GitHub, *New repository* → owner `goel12133`, name
   `swarm-colosseum`, **Public**, no README, no licence, no .gitignore (the repo brings its own).
   Unlocks a remote to push to.
5. **Create a deploy key for that repo only:** on the VPS,
   `ssh-keygen -t ed25519 -N "" -f ~/.ssh/swarm_colosseum_deploy -C swarm-colosseum-deploy`;
   then on GitHub, repo → *Settings → Deploy keys → Add deploy key*, paste
   `~/.ssh/swarm_colosseum_deploy.pub`, tick **Allow write access**. Unlocks pushing to that one
   repo and nothing else on your account.
6. **Publish:** `cd /root/swarm-colosseum && python3 -m colosseum.ops publish` (the lead
   engineer runs this once you say the repo and key exist). It runs `scripts/publish.sh --live`
   with the deploy key: rewrites identities in a mirror, audits, pushes `main` (fast-forward)
   and the current `out/site` to `gh-pages`, and records both in `out/publish.json`, which is
   what lets every later night republish on its own. Unlocks the code being public.
7. **Turn on Pages:** repo → *Settings → Pages → Source: Deploy from a branch → `gh-pages` /
   root*, custom domain `pelennor.tech` (the build writes the CNAME file). Unlocks the site at
   `https://pelennor.tech`.
8. **Straight after (lead engineer):** clone the public repo fresh and rerun the leak scan
   (hostname, personal email, key shapes, every commit and blob on `main` and `gh-pages`);
   open a test PR that adds `bots/submitted/pr/goel12133/launch_check.py` (a workshop
   solution, renamed), confirm the `submission` check goes green, then close it unmerged and
   delete its branch; load the site at phone width. Results go in `reports/LAUNCH_DONE.md`.
9. **The first night after launch (check the next morning):**
   - `out/ALERT.md` doesn't exist, and `out/house_league.cron.log` shows `"publish":
     "published: main …, gh-pages …"` from after-night;
   - `out/publish.json` matches `git ls-remote` on the public repo (main and gh-pages);
   - the public `main` has the night's results commit, and the site's ladders show the new
     night;
   - GitHub's Actions tab: "pages build and deployment" green, and no `submission` run (it
     runs only on PRs that touch `bots/submitted/pr/`);
   - the leak scan on a fresh public clone is still clean.
