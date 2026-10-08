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
6. **Publish:** `cd /root/swarm-colosseum && scripts/publish.sh --live
   git@github.com:goel12133/swarm-colosseum.git ~/.ssh/swarm_colosseum_deploy`. It rewrites
   identities in a mirror, audits, builds the site, pushes `main` (fast-forward) and
   `gh-pages`. Unlocks the code being public.
7. **Turn on Pages:** repo → *Settings → Pages → Source: Deploy from a branch → `gh-pages` /
   root*. Unlocks the site at `https://goel12133.github.io/swarm-colosseum/`.
