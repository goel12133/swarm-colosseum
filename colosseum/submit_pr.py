"""Submissions by pull request: the CI check and the league-side intake. Prepared, not opened.

A submission is a pull request that adds (or updates) one file:

    bots/submitted/pr/<handle>/<NAME>.py      handle = the PR author's GitHub login, lowercased

    python -m colosseum.submit_pr check --changes changes.txt --author <login>
    python -m colosseum.submit_pr intake

`check` runs in CI (.github/workflows/submission.yml) on `git diff --name-status` output. It
reads the files as text and parses them with `ast`; it never imports or runs a bot, so CI
needs no Docker and executes no submitted code. It fails the PR if anything outside the
author's own folder is touched, so a submission can't also change the checker, the
workflow, the engine or another player's bot. A green CI check is advisory only: under
`pull_request` the workflow comes from the PR itself, so the binding checks are the ones
the league machine runs from master at intake.

`intake` runs on the league machine after a maintainer merges. It sends every file under
bots/submitted/pr/ through `colosseum.submit` (the same static checks again, then the
sandbox smoke test), which copies accepted bots into bots/submitted/<side>/, where the
tournament finds them. bots/submitted/pr/ itself is never searched by the tournament and,
being under bots/submitted/, is untrusted: the host never imports anything there.
"""
import argparse
import re
import sys
from pathlib import Path

from . import content_check
from .submit import HANDLE_RE, MAX_BYTES, NAME_RE, Rejected, check_source
from .tournament import ROOT

PR_DIR = ROOT / "bots" / "submitted" / "pr"
PR_PREFIX = "bots/submitted/pr/"
MAX_FILES_PER_PR = 2                     # one bot per side
_PATH_RE = re.compile(r"^bots/submitted/pr/([^/]+)/([^/]+)\.py$")
_ROLE_RE = re.compile(r'^ROLE\s*=\s*["\'](attacker|defender)["\']', re.M)


def parse_changes(text: str):
    """`git diff --name-status` lines -> [(status letter, [paths])]."""
    out = []
    for line in text.splitlines():
        if line.strip():
            parts = line.split("\t")
            out.append((parts[0][:1], parts[1:]))
    return out


def handle_for(login: str) -> str:
    """The handle a GitHub login submits under, or raise Rejected."""
    handle = (login or "").lower()
    if not HANDLE_RE.match(handle):
        raise Rejected(f"Your GitHub login {login!r} doesn't fit the handle rules (2-24 "
                       "characters: lowercase letters, digits, _ and -). Open an issue and "
                       "a maintainer will sort it out.")
    return handle


def check_file(rel: str, source_bytes: bytes, handle: str) -> str:
    """Raise Rejected or return 'side/NAME'. Text and ast only; never executes."""
    m = _PATH_RE.match(rel)
    if not m:
        raise Rejected(f"{rel}: a bot goes at {PR_PREFIX}<your login>/<NAME>.py.")
    if m.group(1) != handle:
        raise Rejected(f"{rel}: this folder isn't yours. Put your bot in "
                       f"{PR_PREFIX}{handle}/.")
    if len(source_bytes) > MAX_BYTES:
        raise Rejected(f"{rel}: the file is {len(source_bytes):,} bytes; the limit is "
                       f"{MAX_BYTES:,}.")
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise Rejected(f"{rel}: the file is not UTF-8 text.")
    role = _ROLE_RE.search(source)
    if not role:
        raise Rejected(f"{rel}: there is no ROLE = \"attacker\" or ROLE = \"defender\" line.")
    try:
        name = check_source(source, role.group(1))
    except Rejected as exc:
        raise Rejected(f"{rel}: {exc}")
    if name != m.group(2) or not NAME_RE.match(m.group(2)):
        raise Rejected(f"{rel}: the file name must be NAME plus .py, i.e. {name}.py.")
    ok, reason = content_check.check(source)
    if not ok:
        raise Rejected(f"{rel}: game terms only, no {reason} (see CONTRIBUTING.md, rule 1).")
    return f"{role.group(1)}/{name}"


def check_pr(changes, author: str, root: Path = ROOT):
    """(ok, lines). Every changed path must be an added or modified bot in the author's folder."""
    try:
        handle = handle_for(author)
    except Rejected as exc:
        return False, [f"REJECTED: {exc}"]
    if not changes:
        return False, ["REJECTED: the pull request changes no files."]
    lines, ok = [], True
    outside = [p for _, paths in changes for p in paths if not p.startswith(PR_PREFIX)]
    if outside:
        return False, [f"REJECTED: a submission may only add files under "
                       f"{PR_PREFIX}{handle}/. This PR also changes: "
                       f"{', '.join(sorted(set(outside))[:10])}. Send other changes "
                       "as a separate pull request."]
    if len(changes) > MAX_FILES_PER_PR:
        return False, [f"REJECTED: at most {MAX_FILES_PER_PR} bots per pull request "
                       f"(this one has {len(changes)} changes)."]
    sides = []
    for status, paths in changes:
        rel = paths[-1]
        if status not in ("A", "M"):
            ok = False
            lines.append(f"REJECTED: {rel}: only adding or updating a bot is allowed "
                         f"(git status {status}); ask a maintainer to remove or rename one.")
            continue
        try:
            if (root / rel).is_symlink() or not (root / rel).is_file():
                raise Rejected(f"{rel}: must be a plain file (no links).")
            what = check_file(rel, (root / rel).read_bytes(), handle)
        except Rejected as exc:
            ok = False
            lines.append(f"REJECTED: {exc}")
            continue
        sides.append(what.split("/")[0])
        lines.append(f"OK: {rel} ({what}) passes the static checks.")
    if len(sides) != len(set(sides)):
        ok = False
        lines.append("REJECTED: one bot per side per pull request.")
    if ok:
        lines.append("Static checks passed. A maintainer reviews the code; after merge the "
                     "league machine runs the checks again and a test match in the sandbox.")
    return ok, lines


def intake(pr_dir: Path = None, submit_fn=None):
    """Send every merged PR bot through colosseum.submit. Returns [(path, result)]."""
    from . import submit
    pr_dir = PR_DIR if pr_dir is None else pr_dir
    submit_fn = submit_fn or submit.submit
    results = []
    for path in sorted(pr_dir.glob("*/*.py")):
        handle = path.parent.name
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            results.append((path, dict(status="rejected", reason="not a plain file")))
            continue
        m = _ROLE_RE.search(path.read_text(errors="replace"))
        if not HANDLE_RE.match(handle) or not m:
            results.append((path, dict(status="rejected",
                                       reason="bad folder name or no ROLE line")))
            continue
        results.append((path, submit_fn(path, m.group(1), handle)))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="CI: static checks on a PR's changed files")
    c.add_argument("--changes", type=Path, required=True,
                   help="output of git diff --name-status BASE...HEAD")
    c.add_argument("--author", required=True, help="the PR author's GitHub login")
    sub.add_parser("intake", help="league machine: submit every merged PR bot")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        ok, lines = check_pr(parse_changes(args.changes.read_text()), args.author)
        print("\n".join(lines))
        return 0 if ok else 1
    failed = 0
    for path, result in intake():
        status = result["status"]
        failed += status == "rejected"
        detail = result.get("reason") or result.get("message") or result.get("name", "")
        print(f"{status.upper()}: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"
              f" -- {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
