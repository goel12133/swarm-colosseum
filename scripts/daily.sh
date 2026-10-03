#!/usr/bin/env bash
# Daily engineering session (charter section 2), run by cron at 05:00 UTC after the league.
#
# All the logic is in colosseum/daily.py so it can be tested; this only sets the environment
# cron lacks. The session's tool allow-list is scripts/daily_allowlist.txt, and daily.py
# refuses to start unless that file's sha256 matches scripts/daily_allowlist.sha256 (the
# approved one). The wrapper, not the agent, merges: master moves only by fast-forward,
# only when the full test suite is green.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
export HOME="${HOME:-/root}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p out/daily
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=/usr/bin/python3
"$PY" -m colosseum.daily >> out/daily/daily.log 2>&1
