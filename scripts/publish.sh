#!/usr/bin/env bash
# Publish (sprint L10): push the rewritten history to REMOTE's main and the built site to
# REMOTE's gh-pages. Dry by default: it refuses any remote that is not a local path unless
# --live is given, and only the founder passes --live, on launch day.
#
#   scripts/publish.sh [--live] [--site DIR] [--merge-onto SHA] REMOTE [DEPLOY_KEY]
#
# Steps, each one a gate for the next:
#   1. rewrite_identity.sh: a fresh mirror of this repo with root@<host> replaced by the
#      identity in scripts/public_identity (the live repo is never rewritten)
#   2. audit_secrets.py on a checkout of that mirror: anything found aborts
#   3. the site: --site DIR, or python3 -m colosseum.site into a temporary directory
#   4. push the mirror's master to REMOTE main, fast-forward only (never forced). With
#      --merge-onto SHA (ops.publish_step, after a fold-back has brought public main's new
#      commits into master): if REMOTE main is exactly SHA and the rewritten master doesn't
#      contain it, push instead a merge commit with master's tree and parents SHA and
#      master, so main still only grows (colosseum/foldback.py)
#   5. the site as one commit on an orphan branch, force-pushed to REMOTE gh-pages. This is
#      the one force push in the project: a generated branch, never master (PROGRESS L10)
# DEPLOY_KEY (an ssh private key with write access to that one repo) is used for ssh remotes.
set -euo pipefail
LIVE=0; SITE=""; ONTO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --live) LIVE=1; shift;;
    --site) SITE="$2"; shift 2;;
    --merge-onto) ONTO="$2"; shift 2;;
    *) break;;
  esac
done
REMOTE="${1:?usage: publish.sh [--live] [--site DIR] [--merge-onto SHA] REMOTE [DEPLOY_KEY]}"; KEY="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$REMOTE" in
  /*|./*|../*|file://*) ;;
  *) if [ "$LIVE" != 1 ]; then
       echo "refusing: $REMOTE is not a local path; a real publish needs --live (founder only)" >&2
       exit 2
     fi;;
esac
if [ -n "$KEY" ]; then
  export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
NAME="$(sed -n 1p "$ROOT/scripts/public_identity")"; EMAIL="$(sed -n 2p "$ROOT/scripts/public_identity")"

echo "1/5 rewriting identities in a fresh mirror"
"$ROOT/scripts/rewrite_identity.sh" "$ROOT" "$WORK/mirror.git" "$NAME" "$EMAIL" >/dev/null

echo "2/5 auditing the rewritten history"
git clone -q "$WORK/mirror.git" "$WORK/check"
(cd "$WORK/check" && python3 scripts/audit_secrets.py) || { echo "audit failed: not publishing" >&2; exit 3; }

echo "3/5 site"
if [ -z "$SITE" ]; then
  SITE="$WORK/site"
  (cd "$ROOT" && python3 -c "
from pathlib import Path; from colosseum import site
site.build(Path('$SITE'))" >/dev/null)
fi
[ -f "$SITE/index.html" ] || { echo "no index.html in $SITE: not publishing" >&2; exit 4; }

echo "4/5 pushing master to $REMOTE main (fast-forward only)"
M="$WORK/mirror.git"; PUSH="$(git -C "$M" rev-parse master)"
if [ -n "$ONTO" ]; then
  git -C "$M" fetch -q "$REMOTE" "refs/heads/main:refs/public/main"
  [ "$(git -C "$M" rev-parse refs/public/main)" = "$ONTO" ] || {
    echo "public main is not $ONTO: not publishing" >&2; exit 5; }
  if ! git -C "$M" merge-base --is-ancestor "$ONTO" master; then
    PUSH="$(GIT_AUTHOR_NAME="$NAME" GIT_AUTHOR_EMAIL="$EMAIL" GIT_COMMITTER_NAME="$NAME" \
      GIT_COMMITTER_EMAIL="$EMAIL" git -C "$M" commit-tree "master^{tree}" -p "$ONTO" \
      -p master -m "Publish master $(git -C "$M" rev-parse --short master) onto main")"
  fi
fi
git -C "$M" push -q "$REMOTE" "$PUSH:refs/heads/main"

echo "5/5 pushing the site to $REMOTE gh-pages"
git init -q "$WORK/pages" && cd "$WORK/pages"
cp -R "$SITE"/. . && touch .nojekyll
git add -A
git -c user.name="$NAME" -c user.email="$EMAIL" commit -q \
  -m "Site build from main $(git -C "$WORK/mirror.git" rev-parse --short master)"
git push -q --force "$REMOTE" "HEAD:refs/heads/gh-pages"
echo "published: main $(git -C "$M" rev-parse --short "$PUSH"), gh-pages $(git rev-parse --short HEAD)"
