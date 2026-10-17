# Loop session 2026-10-17 06:00 UTC

**Status:** merged — 2 commit(s) fast-forwarded onto master
**Signal:** Number 4 (honest published numbers). The live home page contradicts itself and the season report. It says "19 nights run", "Ladders after night 19" and "Night 19 (2026-10-17)". On the same page the footer says "day 20 of 28", and reports/SEASON_1.md says "20 of 28 nights (2026-09-28 to 2026-10-17)". The ledger out/nights.jsonl has a 2026-09-28 record marked `"backfilled": true, "status": "ok"`, so 20 nights have run. After the fix, the rebuilt out/site/index.html will say 20 in all four places, and a new test will hold it there.
**Reviewer:** PASS
**Tokens:** 48,226 (cap 200,000); **time:** 2181 s; exit 0

**Merged:**
- ceca6c4 Signal 4: number changelog entries from the ledger like nights_run, not by snapshot; rebuilt out/site/changelog.html greps '2026-10-17 · night 20' (line 15) and '2026-09-28 · night 1' (lines 34-35); full suite 410 passed, exit 0
- 5953d1e Signal 4: count nights from the ledger, not snapshots; rebuilt home reads 20 nights run, after night 20, Night 20 (2026-10-17), day 20 of 28; full suite 409 passed, exit 0

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
