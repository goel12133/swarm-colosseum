"""Fold merged submission PRs back into master (post-launch, founder, 2026-10-10).

The public main is a rewrite of master (scripts/rewrite_identity.sh), so a PR merged on
GitHub lands on a history the live repo doesn't have. Before the nightly republish, this
looks at what public main has gained since the last publish and brings it into master:

  1. fetch public main into a scratch bare repo (never into the live repo)
  2. new commits = everything reachable from public main and not from the sha we last
     published (out/publish.json). Ancestry, not authorship: a contributor can write any
     author name on a commit, so who it claims to be from decides nothing
  3. every new commit, merges included (against their first parent), may only add, change
     or delete regular files at bots/submitted/pr/<handle>/<NAME>.py -- the one shape a
     submission PR may have (colosseum/submit_pr.py). Any other path, a symlink, a
     submodule, or a public main that no longer contains our last publish: the whole batch
     is rejected, nothing is applied, and the night alerts (publish_step raises)
  4. otherwise the net change is applied to master on a branch, as files written from
     public main (the bot is never imported or run here; intake does that, in the sandbox),
     the full test suite runs, and master fast-forwards to it
The publish that follows merges onto public main (scripts/publish.sh --merge-onto), so main
only ever grows. Off until 3.8 passes: ops.FOLDBACK_ENABLED.
"""
import subprocess
import tempfile
from pathlib import Path

from .submit_pr import _PATH_RE

LEAGUE = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]


class Rejected(RuntimeError):
    pass


def _git(repo, *args, env=None, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=env, check=check).stdout


def allowed(status: str, mode: str, path: str) -> bool:
    """One changed path of a new public commit, from `git diff-tree --raw`."""
    if not _PATH_RE.match(path):
        return False
    return status == "D" or mode == "100644"


def review(scratch: Path, last: str, public: str):
    """[(sha, author, [(status, path)])] for the new commits; raises Rejected on any
    commit that may not be folded back."""
    ok = subprocess.run(["git", "-C", str(scratch), "merge-base", "--is-ancestor", last,
                         public], capture_output=True).returncode == 0
    if not ok:
        raise Rejected(f"public main {public[:7]} no longer contains our last publish "
                       f"{last[:7]}: its history was rewritten on GitHub")
    commits, bad = [], []
    for sha in _git(scratch, "rev-list", "--reverse", f"{last}..{public}").split():
        parents = _git(scratch, "rev-list", "--parents", "-n1", sha).split()[1:]
        author = _git(scratch, "show", "-s", "--format=%an <%ae>", sha).strip()
        raw = _git(scratch, "diff-tree", "-r", "--no-renames", "--raw", parents[0], sha)
        changes = []
        for line in raw.splitlines():
            meta, path = line.split("\t", 1)
            _, new_mode, _, _, status = meta.lstrip(":").split()
            changes.append((status, path))
            if not allowed(status, new_mode, path):
                bad.append(f"{sha[:7]} ({author}) {status} {path} (mode {new_mode})")
        commits.append((sha, author, changes))
    if bad:
        raise Rejected("public main has commits that may not be folded back, so none were "
                       "applied: " + "; ".join(bad[:10]) + (" ..." if len(bad) > 10 else ""))
    return commits


def run(root: Path, remote: str, env: dict, last: str, public: str, verify) -> str:
    """Fold public main's new commits (last..public) into root's master. verify(root) runs
    the test suite on the fold-back branch and returns True if it passed."""
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("live repo has uncommitted changes: not folding back")
    if _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() != "master":
        raise RuntimeError("live repo is not on master: not folding back")
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "public.git"
        subprocess.run(["git", "init", "-q", "--bare", str(scratch)], check=True)
        subprocess.run(["git", "-C", str(scratch), "fetch", "-q", remote,
                        "refs/heads/main:refs/heads/main"], env=env, check=True,
                       capture_output=True, timeout=600)
        if _git(scratch, "rev-parse", "main").strip() != public:
            raise RuntimeError("public main moved while folding back; retry tomorrow")
        commits = review(scratch, last, public)
        net = _git(scratch, "diff", "--no-renames", "--name-status", last, public).split("\n")
        changes = [tuple(l.split("\t", 1)) for l in net if l.strip()]
        branch = f"foldback-{public[:7]}"
        _git(root, "checkout", "-q", "-b", branch, "master")
        try:
            for status, path in changes:
                dest = root / path
                if status == "D":
                    if dest.exists():
                        _git(root, "rm", "-q", "--", path)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(subprocess.run(
                    ["git", "-C", str(scratch), "cat-file", "blob", f"{public}:{path}"],
                    capture_output=True, check=True).stdout)
                _git(root, "add", "--", path)
            lines = [f"Fold-back: {len(commits)} commit(s) from public main "
                     f"{last[:7]}..{public[:7]}", ""]
            lines += [f"{sha[:7]} {author}: " + ", ".join(f"{s} {p}" for s, p in ch)
                      for sha, author, ch in commits]
            _git(root, *LEAGUE, "commit", "-q", "--allow-empty", "-m", "\n".join(lines))
            if not verify(root):
                raise RuntimeError(f"tests failed on {branch}; master unchanged, branch kept")
        except Exception:
            _git(root, "checkout", "-q", "-f", "master", check=False)
            raise
        _git(root, "checkout", "-q", "master")
        _git(root, "merge", "-q", "--ff-only", branch)
        _git(root, "branch", "-q", "-d", branch)
    paths = sorted({p for _, _, ch in commits for _, p in ch})
    return f"folded {len(commits)} commit(s): {', '.join(paths) or 'no file changes'}"


def full_suite(root: Path) -> bool:
    import sys
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x"], cwd=root,
                          capture_output=True, timeout=1800).returncode == 0
