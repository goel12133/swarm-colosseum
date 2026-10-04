"""Secret and identity audit of the whole git history (sprint L11). Prints where, never what.

    python3 scripts/audit_secrets.py

Scans every commit on every branch -- each file version's content, each commit message,
and each author/committer identity -- for:
  * key and token shapes (API keys, cloud keys, platform tokens, private-key blocks,
    hard-coded password/secret/token assignments)
  * files that must never have been committed (.house_league.env*, anything under
    out/, ~/.claude material)
  * anything identifying this machine (its hostname, IPv4 addresses, home-directory paths
    beyond the repo's own /root/swarm-colosseum)
Output lists commit, path and pattern name only; a matched value is never printed.
Exit 1 if anything is found.
"""
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = {
    "anthropic-key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\b(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{40,}"),
    "slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer-token": re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._\-]{20,}"),
    "assigned-secret": re.compile(
        r"(?i)\b(password|passwd|secret|api_?key|access_?token|auth_?token)\b\s*[:=]\s*"
        r"['\"][^'\"\s]{12,}['\"]"),
}
FORBIDDEN_PATHS = re.compile(r"(^|/)\.house_league\.env(?!\.example$)|^out/|(^|/)\.claude/|"
                             r"credentials\.json$")


def identity_patterns():
    host = socket.gethostname()
    fqdn = socket.getfqdn()
    pats = {"hostname": re.compile(re.escape(host))}
    if fqdn and fqdn != host:
        pats["fqdn"] = re.compile(re.escape(fqdn))
    pats["ipv4"] = re.compile(r"\b(?!127\.0\.0\.1\b)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
                              r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
    pats["home-path"] = re.compile(r"/root/(?!swarm-colosseum\b)[A-Za-z0-9_.\-]+")
    return pats


# Reviewed and benign (L11, 2026-10-04). Anything else that matches is reported.
ALLOWED = {
    "ipv4": {"1.1.1.1"},                       # the address the no-network sandbox test tries
    "home-path": {"/root/.local", "/root/backups", "/root/x"},   # generic; /root/x is a test
}


def _hits(name, rx, text):
    return [m.group(0) for m in rx.finditer(text)
            if m.group(0) not in ALLOWED.get(name, set())]


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          errors="replace").stdout


def main():
    findings = set()
    ident = identity_patterns()
    commits = git("rev-list", "--all").split()
    seen_blobs = set()
    for c in commits:
        meta = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", c)
        for name, rx in {**SECRET_PATTERNS, **ident}.items():
            if _hits(name, rx, meta):
                findings.add((c[:7], "(commit message / identity)", name))
        for line in git("ls-tree", "-r", c).splitlines():
            mode_type_sha, path = line.split("\t", 1)
            blob = mode_type_sha.split()[2]
            if FORBIDDEN_PATHS.search(path):
                findings.add((c[:7], path, "forbidden-path"))
            if blob in seen_blobs:
                continue
            seen_blobs.add(blob)
            text = git("cat-file", "-p", blob)
            for name, rx in {**SECRET_PATTERNS, **ident}.items():
                if _hits(name, rx, text):
                    findings.add((c[:7], path, name))
    by_kind = {}
    for c, path, name in sorted(findings):
        by_kind.setdefault(name, []).append((c, path))
    print(f"scanned {len(commits)} commits, {len(seen_blobs)} distinct file versions")
    for name, rows in sorted(by_kind.items()):
        paths = sorted({p for _, p in rows})
        print(f"  {name}: {len(rows)} hit(s) in {len(paths)} path(s): "
              + ", ".join(paths[:8]) + (" ..." if len(paths) > 8 else ""))
    if not findings:
        print("  nothing found")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
