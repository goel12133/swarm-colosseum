#!/usr/bin/env bash
# Launch rehearsal (sprint L15), end to end on a fresh scratch clone, no manual fixes.
#
#   scripts/rehearse.sh SCRATCH_DIR [SCREENS_DIR]
#
# Every step is logged as ok/FAIL with its time in SCRATCH_DIR/rehearsal.log, and a failed
# step doesn't stop the later ones, so one run shows everything that would break. Nothing is
# pushed anywhere: the publish step targets a bare repo inside SCRATCH_DIR.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$1"; SCREENS="${2:-$ROOT/out/launch_screens}"
[ -e "$S" ] && { echo "refusing: $S exists" >&2; exit 2; }
mkdir -p "$S" "$SCREENS"; LOG="$S/rehearsal.log"; C="$S/clone"; FAILS=0
step() {   # step NAME COMMAND...
  local name="$1"; shift; local t0=$SECONDS
  if "$@" > "$S/$name.out" 2>&1; then echo "ok   $name $((SECONDS - t0))s" | tee -a "$LOG"
  else echo "FAIL $name $((SECONDS - t0))s (see $S/$name.out)" | tee -a "$LOG"; FAILS=$((FAILS + 1)); fi
}

step clone git clone -q "$ROOT" "$C"
step reproduce make -C "$C" reproduce
step tournament bash -c "cd '$C' && python3 -m colosseum.tournament --sandbox --seeds 10 --quiet"
step library bash -c "cd '$C' && python3 -m colosseum.library"
step site bash -c "cd '$C' && python3 -m colosseum.site"

# a sample good PR (one new bot in the author's own folder) and a bad one (touches the engine)
step pr_good bash -c "cd '$C' && git checkout -q -b pr-good && mkdir -p bots/submitted/pr/rehearsal &&
  sed 's/^NAME = .*/NAME = \"rehearsal_closest\"/' workshop/solutions/ex1_closest_first.py > bots/submitted/pr/rehearsal/rehearsal_closest.py &&
  git add -A && git -c user.name=r -c user.email=r@r commit -q -m pr && git diff --name-status master...pr-good > ../good.txt &&
  python3 -m colosseum.submit_pr check --changes ../good.txt --author rehearsal"
step pr_bad_is_refused bash -c "cd '$C' && git checkout -q -b pr-bad master && echo '# x' >> colosseum/sim.py &&
  git add -A && git -c user.name=r -c user.email=r@r commit -q -m bad && git diff --name-status master...pr-bad > ../bad.txt &&
  ! python3 -m colosseum.submit_pr check --changes ../bad.txt --author rehearsal"
step intake bash -c "cd '$C' && git checkout -q pr-good && python3 -m colosseum.submit_pr intake && ls bots/submitted/*/rehearsal__*.py"

step publish bash -c "git init -q --bare '$S/remote.git' && cd '$C' && git checkout -q master &&
  scripts/publish.sh --site '$C/out/site' '$S/remote.git' && git -C '$S/remote.git' rev-parse main gh-pages"

# phone-width screenshots: every page except the replay pages (one viewer, different data),
# plus three of those. Full replay pages fetch their packed data, which file:// can't, so the
# pages are served on the container's own loopback (--network none: nothing leaves it)
step screenshots bash -c "cd '$C/out/site' && { find . -name '*.html' ! -path './replays/*' | sort; find ./replays -name '*.html' | sort | head -3; } > '$S/pages.txt' &&
  chmod -R a+rX '$C/out/site' && chmod 777 '$SCREENS' &&
  docker run --rm --network none -v '$C/out/site:/site:ro' -v '$SCREENS:/shots' -v '$S/pages.txt:/pages.txt:ro' colosseum-clip:1 sh -c '
    cd /site && (python3 -m http.server 8000 --bind 127.0.0.1 >/dev/null 2>&1 &) && sleep 1
    while read p; do n=\$(echo \"\$p\" | sed \"s|^\\./||; s|/|__|g; s|\\.html\$||\");
      chromium --headless --no-sandbox --disable-gpu --hide-scrollbars --force-dark-mode \
        --window-size=390,2200 --virtual-time-budget=4000 --screenshot=/shots/\$n.png \"http://127.0.0.1:8000/\$p\" 2>/dev/null; done < /pages.txt' &&
  test \$(ls '$SCREENS'/*.png | wc -l) -ge \$(wc -l < '$S/pages.txt')"

echo "rehearsal: $FAILS failed step(s)" | tee -a "$LOG"
exit $FAILS
