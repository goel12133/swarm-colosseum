# Loop session 2026-10-25 21:00 UTC

**Status:** merged — 1 commit(s) fast-forwarded onto master
**Signal:** Number 4, honesty (rule 8), which also protects number 1. Since 2026-10-24 the public pages have claimed something false. The site's home page says "0 outside submissions · open 24 Oct", and SUBMITTING.md, ABOUT.md, README.md and research/00_summary.md all say submissions open on 2026-10-24 after a sandbox review. That review, the 3.8 session, never ran: there is no SECURITY.md, no tests/test_hardening.py, and colosseum/ops.py:350 still has `FOLDBACK_ENABLED = False`. So anyone who believes the pages and sends a bot tonight gets nothing back. We will know it is fixed when `grep -rn "open 24 Oct\|Opens Saturday\|open on 2026-10-24\|open on Saturday 2026-10-24\|open through pull requests on 2026-10-24\|from the 24th" README.md SUBMITTING.md ABOUT.md research/00_summary.md colosseum/site.py` finds nothing, and the next nightly republish shows "outside submissions · not open yet" on the home page.
**Reviewer:** PASS
**Tokens:** 32,527 (cap 200,000); **time:** 1259 s; exit 0

**Merged:**
- e92e0c9 Signal 4: public pages say submissions are not open yet and that the 2026-10-24 sandbox review (3.8) has not happened, with no new date: SUBMITTING.md banner, ABOUT.md, README.md, research/00_summary.md, home label 'outside submissions · not open yet' (colosseum/site.py:724); FOUNDER_TODO 3.8 item records it did not run (no SECURITY.md, no tests/test_hardening.py, colosseum/ops.py:350 FOLDBACK_ENABLED = False) and asks for a new date. Evidence: the signal's grep over README.md SUBMITTING.md ABOUT.md research/00_summary.md colosseum/site.py finds nothing; tests/test_launch_docs.py asserts README lacks 'open on 2026-10-24' and the built home page reads 'not open yet'; python3 -m pytest tests -q: 414 passed, exit 0.

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
