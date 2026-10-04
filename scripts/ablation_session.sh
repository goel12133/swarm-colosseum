#!/usr/bin/env bash
# The 14-night persona ablation (sprint L3) as its own session, run by cron after the league
# and never inside the nightly run. Each run spends at most what the nightly token cap
# leaves after that night's league, stops cleanly before a call that could cross it, and
# continues on the next run. See colosseum/ops.py: ablation_session.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
export HOME="${HOME:-/root}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p out/ablation_14
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=/usr/bin/python3
"$PY" -m colosseum.ops ablation-session >> out/ablation_14/session.log 2>&1
