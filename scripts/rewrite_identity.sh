#!/usr/bin/env bash
# Founder-approved (2026-10-04) history rewrite for publishing. Never touches the live repo:
# it mirrors SOURCE into a fresh bare clone at DEST and, there only, replaces every
# root@<host> author/committer identity with the public one. The publish step pushes from
# DEST, so whatever goes public is always rewritten, and the live master is never rewritten
# (hard rule 9).
#
#   scripts/rewrite_identity.sh SOURCE_REPO DEST_MIRROR "Public Name" "public@email"
#
# Founder (2026-10-16): CLAUDE.md, FOUNDER_TODO.md and DECISIONS.local.md stay private. They
# are dropped from every commit after scripts/public_private_since (the last commit
# published before the rule); earlier commits keep what was already public, so the
# rewritten history of those commits, and so the public main, is unchanged and still
# fast-forwards.
set -euo pipefail
SRC="$1"; DEST="$2"; NAME="$3"; EMAIL="$4"
SINCE="$(cat "$(cd "$(dirname "$0")" && pwd)/public_private_since")"
[ -e "$DEST" ] && { echo "refusing: $DEST exists" >&2; exit 2; }
git clone -q --mirror "$SRC" "$DEST"
cd "$DEST"
export PUB_NAME="$NAME" PUB_EMAIL="$EMAIL" FILTER_BRANCH_SQUELCH_WARNING=1 PRIVATE_SINCE="$SINCE"
git filter-branch -f --index-filter '
  git merge-base --is-ancestor "$GIT_COMMIT" "$PRIVATE_SINCE" 2>/dev/null ||
    git rm -q --cached --ignore-unmatch -- CLAUDE.md FOUNDER_TODO.md DECISIONS.local.md
' --env-filter '
  case "$GIT_AUTHOR_EMAIL" in root@*) GIT_AUTHOR_NAME="$PUB_NAME"; GIT_AUTHOR_EMAIL="$PUB_EMAIL";; esac
  case "$GIT_COMMITTER_EMAIL" in root@*) GIT_COMMITTER_NAME="$PUB_NAME"; GIT_COMMITTER_EMAIL="$PUB_EMAIL";; esac
' -- --all >/dev/null
# drop filter-branch's backup refs so the old identities are really gone from DEST
git for-each-ref --format='%(refname)' refs/original/ | xargs -r -n1 git update-ref -d
git reflog expire --expire=now --all && git gc -q --prune=now
echo "rewritten: $(git rev-list --all | wc -l) commits in $DEST"
