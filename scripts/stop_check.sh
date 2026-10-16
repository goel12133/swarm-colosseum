#!/usr/bin/env bash
# Stop hook: no session ends red. Runs the full suite and the site build test; if either
# fails, exit 2 blocks the stop and tells the session why. Blocks once: if the session was
# already continued by this hook (stop_hook_active) and is still red, it may stop, and the
# loop's wrapper will refuse to merge it. Skips the run when nothing changed since the last
# green one (same HEAD, same diff, same untracked files), so a turn that edited nothing
# doesn't wait four minutes.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 0
input="$(cat)"
active="$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(str(json.load(sys.stdin).get("stop_hook_active", False)).lower())
except Exception: print("false")')"
state="$( { git rev-parse HEAD; git diff HEAD; git status --porcelain; } 2>/dev/null | sha256sum | cut -c1-16)"
mkdir -p .loop
[ -f .loop/last_green ] && [ "$(cat .loop/last_green)" = "$state" ] && exit 0
out="$(python3 -m pytest tests -q -x 2>&1 | tail -15)"; full=$?
site="$(python3 -m pytest tests/test_site.py -q 2>&1 | tail -5)"; sb=$?
if [ $full -eq 0 ] && [ $sb -eq 0 ]; then
  echo "$state" > .loop/last_green; exit 0
fi
if [ "$active" = "true" ]; then
  echo "stop_check: still red after one retry; stopping, and the wrapper will not merge." >&2
  exit 0
fi
printf 'The suite or the site build test is red; fix it before stopping.\n%s\n%s\n' "$out" "$site" >&2
exit 2
