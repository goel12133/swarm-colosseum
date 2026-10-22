# Loop session 2026-10-22 12:00 UTC

**Status:** merged — 1 commit(s) fast-forwarded onto master
**Signal:** Numbers 5 and 4. Commit 2e9c963, which stops the escalation stall, is on daily-wip but is not on master. The 10-22T09 session crashed before any review (exit 1, 0 tokens, 9 s, status "unreviewed"), so tonight's league would aim both bot slots at hidden_orbit_screen_then_interleaved_dro for a fifth night. If it merges before 03:30 UTC, we will know from the 10-23 night. The league log should log "escalation stalled: 3 nights with no bot beating 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_dro; rotation instead". The `plan:` line should list one attacker and one defender with no "(escalation)". The 10-23 record in out/nights.jsonl should have an attacker in `written`.
**Reviewer:** PASS
**Tokens:** 23,512 (cap 200,000); **time:** 840 s; exit 0

**Merged:**
- 2e9c963 Signals 5 and 4: escalation stops after 3 straight failed nights on the same target (personas.stalled; plan_night recent_nights; _run_night passes the last 3 out/nights.jsonl records and logs 'escalation stalled'). Evidence: out/nights.jsonl 10-19 to 10-22 holds 7 counter_meta defenders aimed at 2026-10-17_attacker_hidden_orbit_screen_then_interleaved_dro, all beat_target false, no attacker written since 10-19. New test_escalation_stops_after_three_failed_nights_on_the_same_target; python3 -m pytest tests -q: 412 passed, exit 0. Check on 10-23: plan line lists one attacker and one defender with no (escalation), and written holds an attacker.

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
