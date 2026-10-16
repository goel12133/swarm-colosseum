#!/usr/bin/env bash
# Install scripts/crontab.txt as this user's crontab (CLAUDE.md rule 3: scheduled jobs change
# only here, run interactively, with the founder's written yes).
#
#   scripts/cron_install.sh                       show the difference and exit
#   scripts/cron_install.sh --apply "<the yes>"   back up the current table to out/cron/,
#                                                 install, and log the change
# "<the yes>" names where the founder said yes (a message, a date); it goes in the log.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEW="$ROOT/scripts/crontab.txt"
CUR="$(mktemp)"; trap 'rm -f "$CUR"' EXIT
crontab -l > "$CUR" 2>/dev/null || true
if diff -u "$CUR" "$NEW" >/dev/null; then echo "crontab already matches scripts/crontab.txt"; exit 0; fi
diff -u --label installed --label scripts/crontab.txt "$CUR" "$NEW" || true
[ "${1:-}" = "--apply" ] || { echo "(dry run: nothing installed)"; exit 0; }
YES="${2:?--apply needs a note of where the founder said yes}"
mkdir -p "$ROOT/out/cron"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cp "$CUR" "$ROOT/out/cron/crontab.$stamp.bak"
crontab "$NEW"
echo "$stamp installed scripts/crontab.txt (backup crontab.$stamp.bak); yes: $YES" >> "$ROOT/out/cron/installs.log"
echo "installed; previous table saved as out/cron/crontab.$stamp.bak"
