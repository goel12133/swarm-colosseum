# 3.8 runbook — sandbox hardening, Sat 2026-10-24 19:00 SGT (11:00 UTC), with the founder

**Goal, under an hour:** show that the static checks and the sandbox refuse or contain every
unsafe kind of submission in charter 3.8, using inert inputs only; agree SECURITY.md; then
decide go / no-go for opening submissions. No test contains a working exploit or attempts
a real container escape, host-filesystem access or network access. We test the fence; we
don't try to get through it.

## Before the session (lead engineer, by Fri 10-23)
- The full suite is green on master; the night of 10-24 (03:30 UTC) and its publish went
  cleanly; `ops.FOLDBACK_ENABLED` is `False`.
- Intake is wired behind the same switch (done 2026-10-10): a fold-back runs
  `submit_pr intake` on its branch, and accepted bots are committed and play from the next
  night (`tests/test_foldback.py`).
- Note the sandbox image's local id (today `python:3.12-slim`, `sha256:f77ac9e44ae9…`) for
  SECURITY.md. Pinning it by digest edits `sandbox.py`, which changes the engine version and
  replays every match, so it waits for the season boundary, when everything replays anyway.
- Have this file open. The session itself writes `tests/test_hardening.py` and
  `SECURITY.md`; neither is drafted in advance (3.8 is interactive-only).

## Agenda (60 min)
| min | what | command |
|---|---|---|
| 0–5 | state check: master, the suite, the switch off | `git log --oneline -3; python3 -m pytest -q` |
| 5–30 | write and run the inert cases below, one class at a time | `python3 -m pytest -q tests/test_hardening.py` |
| 30–40 | fix anything prepared below that failed, then rerun | the same, then the full suite |
| 40–50 | read SECURITY.md together (written while the cases ran) | — |
| 50–55 | go / no-go (below) | — |
| 55–60 | if go: the switch and the pages, through a branch and the suite | `python3 -m pytest -q` |

## The cases (all inert), and what passing looks like
| class | inert input | pass = | already covered? |
|---|---|---|---|
| forbidden imports and calls | `import socket`, `open`, `exec`, `eval`, `subprocess`, `__import__` | static check refuses, with line and reason; nothing kept | yes: `test_submit` (forbidden constructs) |
| dunder traversal | `().__class__`, `"__class__"`, `getattr` | refused statically | yes, same |
| network at runtime | a bot that would open a socket if it could | the call fails inside, the match finishes | yes: `test_sandbox` |
| CPU / memory | a busy loop; a bot allocating past 128 MB | cut at 2 s per tick / killed by OOM; the match finishes | yes: `test_sandbox` |
| non-finite numbers in actions | `float("nan")`/`inf` in launch and steer | dropped as invalid, the match finishes (3.9 guard, made permanent) | partly: `policy._finite`; add the case |
| deeply nested action | `act` returns a list nested 10,000 deep | "unserialisable action" in the container, the tick is a no-op | no: add |
| malformed output | the bot `print`s `{` or a fake reply line | that tick is an error, and **later replies are not shifted** | no: **expected to fail**, see fix A |
| oversized output | the bot writes 10 MB with no newline, then waits | the host gives up at the 2 s tick limit and the match finishes | no: **expected to fail**, see fix B |
| injection strings | `</script><img src=x onerror=1>` in the docstring; odd handles | escaped on every site page; handle refused | partly: site escape test; add bot page and card |
| oversized / odd files | >64 KB, non-UTF-8, symlink in PR | refused | yes: `test_submit`, `test_submit_pr` |

**Pass overall:**
- every row passes;
- the full suite passes twice in a row (determinism);
- SECURITY.md is agreed;
- no case needed anything beyond the two prepared fixes.

## Prepared fixes (in the session, only if a case fails)
- **A, a bot's own output on the reply channel** (`sandbox_runner.py`). Keep the real stdout
  for replies, and point `sys.stdout` at stderr while bot code runs (load, reset, act). A
  bot that prints then only writes to the container's log.
- **B, an unbounded read on the host** (`sandbox.py _read_line`). Read with `os.read` on the
  pipe after `select`, so a missing newline can't block past the deadline, and cap a reply
  at 1 MB. A longer reply ends that tick as an error and restarts the container.

Each fix is small. If either takes more than 15 minutes, stop: that is a no-go for 10-24.

**Both fixes change the engine version, so every cached match replays.** To keep the last
night of season one (10-25 03:30) warm, they are merged after that night. The first night of
season two replays everything regardless, and outside bots don't play before then.

## If something fails
- **A static check misses a construct.** Add it to the validator plus a test, if that fits in
  15 minutes; otherwise no-go.
- **Containment fails beyond A and B** (the host stalls, a limit doesn't hold, a write lands
  outside the container's /tmp). Stop and no-go. Write it up in SECURITY.md and PROGRESS;
  no workaround tonight.
- **A safety-classifier stop on a case.** Per the standing rule: stop that case, log it with
  the flag, don't rephrase it, and carry on with the rest. We decide together whether the
  gap blocks go.
- **Infrastructure trouble** (Docker, the image): retry once, else reschedule.
- **Past 60 minutes:** stop at the decision with whatever is done. Submissions don't open
  until every row passes.

## Go / no-go
- **Go:**
  - set `ops.FOLDBACK_ENABLED = True` (with intake);
  - SUBMITTING, ABOUT and README say "open";
  - merge after the 10-25 night (see above), and that night's publish carries it;
  - check LAUNCH_CHECKLIST 9 on the morning of 10-26.
  - From then on the founder merges only PRs whose `submission` check is green. After a
    fold-back, the public-clone audit will report contributors' identities as
    `unknown-identity`; that is expected for merged PRs, and the audit gets an allowance
    for them in the go commit.
- **No-go:** the submissions date moves a week. The pages say so (the same commit), and the
  failing rows go to the top of the backlog.
