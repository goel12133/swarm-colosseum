# Loop session 2026-10-18 21:00 UTC

**Status:** merged — 1 commit(s) fast-forwarded onto master
**Signal:** Number 4 (the research is real). The public home page and research index label R-04 "preliminary", but R-04 is the final eleven-night write-up that replaced the preliminary cut. So the site is understating a finished result. The cause is in `paper_info` (`/srv/swarm-daily/colosseum/site.py` line 438), which marks a paper preliminary if that word appears anywhere in its first 600 characters:
**Reviewer:** PASS
**Tokens:** 26,761 (cap 200,000); **time:** 1092 s; exit 0

**Merged:**
- bd68a2a Signal 4: R-04 subtitle says 'an earlier four-night cut' instead of 'a four-night preliminary cut' (research/04_annealed_defenders.md lines 3-4), so paper_info (colosseum/site.py:438) labels it final, as R-03 was on 10-14. New test_the_committed_annealing_page_is_final in tests/test_ops.py failed before the edit ('preliminary' in the first 600 chars) and passes after; full suite 411 passed, exit 0. diff --stat master touches only the page, tests/test_ops.py and DECISIONS.local.md.

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
