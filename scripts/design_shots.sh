#!/usr/bin/env bash
# Screenshots of the built site for a design pass (founder, 2026-10-10).
#
#   scripts/design_shots.sh SITE_DIR OUT_DIR
#
# One of each kind of page, at phone (390 px) and desktop (1440 px) width, dark; the home
# page also in light, and with reduced motion (the replay channel waits for a click). Headless Chromium in the colosseum-clip:1 image, with the site served
# on the container's own loopback (--network none: nothing leaves it), because the replay
# pages fetch their packed data and file:// can't.
set -euo pipefail
SITE="$(cd "$1" && pwd)"; OUT="$2"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
cd "$SITE"
first() { for f in "$@"; do [ -f "$f" ] && { echo "$f"; return; }; done; }
bot=$(first bots/*.html)
replay=$(first $(printf '%s\n' replays/*.html | grep -v viewer.html || true))
article=$(printf '%s\n' research/*.html 2>/dev/null | grep -v '00_' | sort | sed -n '$p' || true)
pages="index.html ladders.html $bot $replay replays.html research.html $article changelog.html
       submitting.html library/index.html about.html"
list="$OUT/.pages"; : > "$list"
for p in $pages; do [ -f "$p" ] && echo "$p" >> "$list"; done
chmod -R a+rX "$SITE"; chmod 777 "$OUT"
docker run --rm --network none -v "$SITE:/site:ro" -v "$OUT:/shots" colosseum-clip:1 sh -c '
  cd /site && (python3 -m http.server 8000 --bind 127.0.0.1 >/dev/null 2>&1 &) && sleep 1
  shot() { chromium --headless --no-sandbox --disable-gpu --hide-scrollbars $3 \
             --window-size=$2 --virtual-time-budget=6000 --screenshot=/shots/$1.png \
             "http://127.0.0.1:8000/$4" 2>/dev/null; }
  while read p; do
    n=$(echo "$p" | sed "s|/|__|g; s|\.html$||")
    case "$n" in replays__2*) n=replay;; bots__*) n=bot;; research__*) n=research_article;; esac
    shot "phone_$n" 390,2400 --force-dark-mode "$p"
    shot "desktop_$n" 1440,2000 --force-dark-mode "$p"
  done < /shots/.pages
  shot phone_index_light 390,2400 "" index.html
  shot phone_index_reduced_motion 390,1200 "--force-dark-mode --force-prefers-reduced-motion" index.html
  shot desktop_index_light 1440,2000 "" index.html'
rm -f "$list"
ls "$OUT"/*.png | wc -l
