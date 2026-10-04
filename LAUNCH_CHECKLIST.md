# Launch checklist — founder actions, in order

*Draft: L15 completes it. Nothing here has been run; each line is yours to do.*

1. **Move the stray env file out of the repo** (hard rule 7 stops me touching it):
   `mv /root/swarm-colosseum/.house_league.env.save /root/` — unlocks a clean working tree.
2. **Approve the history rewrite (SECURITY, L11).** 84 commits are authored
   `root@<this server's hostname>`. On a *fresh clone*, never the live repo, replace that
   identity with the one you want public, then push only from the clone:
   ```
   git clone --mirror /root/swarm-colosseum /tmp/sc-public.git && cd /tmp/sc-public.git
   git filter-branch --env-filter '
     case "$GIT_AUTHOR_EMAIL" in root@*) GIT_AUTHOR_NAME="<your name>"; GIT_AUTHOR_EMAIL="<public email>";; esac
     case "$GIT_COMMITTER_EMAIL" in root@*) GIT_COMMITTER_NAME="<your name>"; GIT_COMMITTER_EMAIL="<public email>";; esac
   ' -- --all
   python3 /root/swarm-colosseum/scripts/audit_secrets.py   # run from a checkout of the rewritten clone: must print "nothing found"
   ```
   Unlocks a public push. (The live repo now commits as `Swarm Colosseum <dev@swarm-colosseum.invalid>`;
   change it with `git config user.name/user.email` if you want yours.)
3. Choose a license (L8 has the recommendation), the repo name and visibility, and the domain.
