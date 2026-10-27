# Loop session 2026-10-27 21:00 UTC

**Status:** merged — 3 commit(s) fast-forwarded onto master
**Signal:** 4 (the research is real and corrected when data arrives). The live home page makes a claim that is now false. It still says "the next season begins 26 Oct" (.loop/context.md:98), but 26 Oct has passed and season two has not started. We'll know the fix works when, built from a ledger whose last night is on or after `season.ENDS`, the home page no longer names a start date that has passed, a new test asserts that, and `python3 -m pytest tests -q` exits 0.
**Reviewer:** PASS
**Tokens:** 51,036 (cap 200,000); **time:** 3023 s; exit 0

**Merged:**
- eeb04e8 Signal 4: stale-night recap sentence now depends on status; status ok keeps 'No new bot passed validation, so no tournament ran; the ladders below are still those of {snap}.', any other status says 'The night didn't complete; the ladders below are still those of {snap}.' (changelog wording, site.py:918); test_the_recap_of_a_night_without_a_tournament_names_the_last_snapshot extended with a status error record; full suite 416 passed, exit 0
- ee35c65 Signal 4: recap no longer credits the last snapshot's ladder changes to a later night with no tournament; when the ledger date is after hist[-1][0] it opens 'Night of {date}.' with no number, keeps the wrote/retired clauses, and replaces the took/held clauses with 'No new bot passed validation, so no tournament ran; the ladders below are still those of {snap}.'; equal-date output unchanged (existing test untouched); new test in tests/test_site.py; full suite 416 passed, exit 0
- 1089dd1 Signal 4: home page season line no longer names the passed start date 26 Oct once the last ledger record is on or after season.ENDS; it says the season has passed its scheduled 28 nights and the next season has not started yet; new test in tests/test_launch_docs.py checks ENDS+1 (new wording) and ENDS-1 (old wording); full suite 415 passed, exit 0

Founder items: FOUNDER_TODO.md. Every session: out/daily/sessions.jsonl.
