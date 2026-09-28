#!/usr/bin/env bash
# Nightly house league, called from cron. Sources .house_league.env if present so caps and
# the backend choice do not have to live in the crontab.
#
# Default backend is the Claude Code CLI on the subscription login in $HOME/.claude. cron
# gives HOME but a PATH of /usr/bin:/bin, so ~/.local/bin (where the CLI lives) is added
# here. No API key is needed or used on the cli backend -- house_league.py strips
# ANTHROPIC_API_KEY from the child's environment so the subscription is what gets used.
set -uo pipefail
cd /root/swarm-colosseum || exit 1
export HOME="${HOME:-/root}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
[ -f .house_league.env ] && . ./.house_league.env
mkdir -p out
# The engine is standard-library only; the api backend needs the anthropic SDK, which
# lives in .venv because this box's python is Debian-managed.
PY=/root/swarm-colosseum/.venv/bin/python
[ -x "$PY" ] || PY=/usr/bin/python3
exec "$PY" -m colosseum.house_league --once >> out/house_league.cron.log 2>&1
