# Loop session 2026-10-22 06:00 UTC

**Status:** blocked — the reviewer blocked the change; not merged
**Signal:** Numbers 5 and 4. For four nights the league's escalation rule has used every bot slot on one target and has never beaten it, and nothing in the code stops it. The ledger shows 7 counter_meta defenders aimed at hidden_orbit_screen_then_interleaved_dro from 10-19 to 10-22, all with `"beat_target": false`, and no new attacker since 10-19. The fix stops escalation once it has failed 3 nights in a row on the same target. We will know on the 10-23 night: the `plan:` line in the league log should list one attacker and one defender with no `(escalation)`, and `written` in `out/nights.jsonl` should hold an attacker again.
**Reviewer:** BLOCK
**Tokens:** 31,834 (cap 200,000); **time:** 1239 s; exit 0

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
