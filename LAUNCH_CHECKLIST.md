# Launch checklist — founder actions, in order

*Draft: L15 completes it. Nothing here has been run; each line is yours to do.*

1. **Move the stray env file out of the repo** (hard rule 7 stops me touching it):
   `mv /root/swarm-colosseum/.house_league.env.save /root/` — unlocks a clean working tree.
2. ~~Approve the history rewrite~~ **approved 2026-10-04**. Public identity, in
   `scripts/public_identity`: Vikram Goel, GitHub noreply address (no personal email in
   the public history). Nothing to do by hand: the publish step runs `scripts/rewrite_identity.sh`, which
   mirrors the repo into a fresh clone and rewrites `root@<host>` there only (the live repo is
   never rewritten), then `scripts/audit_secrets.py` must print "nothing found" before any push.
   To publish a different identity, edit `scripts/public_identity`.
3. Choose a license (L8 has the recommendation), the repo name and visibility, and the domain.
