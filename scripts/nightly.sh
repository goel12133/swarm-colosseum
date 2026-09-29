#!/usr/bin/env bash
# Nightly house league, called from cron. Sources .house_league.env if present so caps and
# the backend choice do not have to live in the crontab.
#
# Default backend is the Claude Code CLI on the subscription login in $HOME/.claude. cron
# gives HOME but a PATH of /usr/bin:/bin, so ~/.local/bin (where the CLI lives) is added
# here. No API key is needed or used on the cli backend -- house_league.py strips
# ANTHROPIC_API_KEY from the child's environment so the subscription is what gets used.
#
# After the league: the weekly meta report (if due), the static site bundle, rotation and
# the backup (python -m colosseum.ops after-night). If Python dies before the league can
# write out/ALERT.md itself, this script writes one.
#
# HOUSE_LEAGUE_DRY_RUN=1 runs everything except the model call and the after-night steps,
# which is how a scratch copy of the repo is checked before a change goes live.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
export HOME="${HOME:-/root}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
[ -f .house_league.env ] && . ./.house_league.env
mkdir -p out
# The engine is standard-library only; the api backend needs the anthropic SDK, which
# lives in .venv because this box's python is Debian-managed.
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=/usr/bin/python3
DRY=""
[ "${HOUSE_LEAGUE_DRY_RUN:-0}" = "1" ] && DRY="--dry-run"

"$PY" -m colosseum.house_league --once $DRY >> out/house_league.cron.log 2>&1
rc=$?
if [ "$rc" -ne 0 ] && [ -z "$DRY" ] && [ ! -f out/ALERT.md ]; then
    "$PY" -m colosseum.ops alert "house league exited with code $rc before it could \
record a reason; see out/house_league.cron.log" >> out/house_league.cron.log 2>&1
fi
if [ -z "$DRY" ]; then
    "$PY" -m colosseum.ops after-night >> out/house_league.cron.log 2>&1
fi
exit "$rc"
