#!/usr/bin/env bash
# Nightly house league, called from cron. Sources .house_league.env if present so the API
# key and the spend caps do not have to live in the crontab.
set -uo pipefail
cd /root/swarm-colosseum || exit 1
[ -f .house_league.env ] && . ./.house_league.env
mkdir -p out
# The engine is standard-library only; the house league needs the anthropic SDK, which
# lives in .venv because this box's python is Debian-managed.
PY=/root/swarm-colosseum/.venv/bin/python
[ -x "$PY" ] || PY=/usr/bin/python3
exec "$PY" -m colosseum.house_league --once >> out/house_league.cron.log 2>&1
