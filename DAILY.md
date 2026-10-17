# Loop session 2026-10-17 12:00 UTC

**Status:** merged — 3 commit(s) fast-forwarded onto master
**Signal:** Number 1 (outside bots on the ladder). SUBMITTING.md has never been tried on a clean machine. The loop can't do that itself: the clone was refused, and a clone on this host wouldn't count as clean. So the step goes to the founder as a 10-minute walkthrough, and it becomes a gate on the outreach item. We'll know it worked when FOUNDER_TODO.md has the item with exact commands and the exact expected output. Later, the founder ticks it as pass or fail before 24 Oct, and if it fails, that is a specific SUBMITTING.md defect to fix before anyone outside hits it.
**Reviewer:** PASS
**Tokens:** 29,759 (cap 200,000); **time:** 1194 s; exit 0

**Merged:**
- 9304b7d Signal 1: FOUNDER_TODO.md gains 'Walk SUBMITTING.md on a clean machine, before Sat 2026-10-24' (7 steps, commands copied from SUBMITTING.md) and the outreach Gate gains 'and the clean-machine walk above passed.'; expected output is colosseum/submit.py line 275 print(f"ACCEPTED as {result['name']} ({result['validation']['smoke']})") with the smoke summary from lines 192-193 and opponent layered (line 63); diff --stat touches only FOUNDER_TODO.md and DECISIONS.local.md; full suite 410 passed, exit 0
- 2f674c3 Signal 1: SUBMITTING.md gains 'Before you start' (clone, Python 3.9+, no pip install, Docker + python:3.12-slim pull, save even_trickle as my_bot.py), pinned by test_submitting_md_matches_the_code; full suite 410 passed, exit 0. Fresh-clone run NOT done: git clone into out/clean_clone_check was refused by permissions, so no accepted/ticks/outcome result and no clean-machine evidence yet (a same-host clone would not be a clean machine anyway). Host check: 'python' exits 127 here, only python3 3.12.3, hence the python3 hint.
- 1f488bd Signal 1: FOUNDER_TODO.md gains a complete outreach item (gate on 3.8 and SUBMITTING.md's 24 Oct, five named audiences, ~150-word draft); its figures 20 nights run, 4,140 matches, 41 bots, 0 outside submissions match out/site/index.html line 17 (20 nights also reports/SEASON_1.md line 7); diff touches only FOUNDER_TODO.md and DECISIONS.local.md

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
