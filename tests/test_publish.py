"""Publish pipeline (L10), tested only against a local bare remote: never a real one."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "scripts" / "publish.sh"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def remote(tmp_path):
    r = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(r)], check=True)
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<!doctype html><title>t</title>")
    return r, site


def publish(remote, site, *extra):
    return subprocess.run([str(PUBLISH), *extra, "--site", str(site), str(remote)],
                          capture_output=True, text=True, timeout=600)


def test_publishes_rewritten_main_and_the_site_to_a_local_bare_remote(remote):
    r, site = remote
    p = publish(r, site)
    assert p.returncode == 0, p.stderr
    assert "published: main" in p.stdout
    emails = set(git(r, "log", "main", "--format=%ae%n%ce").split())
    assert not any(e.startswith("root@") for e in emails)          # hostname rewritten
    name, email = (ROOT / "scripts" / "public_identity").read_text().split("\n")[:2]
    assert email in emails
    files = git(r, "ls-tree", "--name-only", "gh-pages").split()
    assert "index.html" in files and ".nojekyll" in files
    assert git(r, "rev-list", "--count", "gh-pages").strip() == "1"  # one orphan commit


def test_republishing_fast_forwards_main_because_the_rewrite_is_deterministic(remote):
    r, site = remote
    assert publish(r, site).returncode == 0
    first = git(r, "rev-parse", "main").strip()
    assert publish(r, site).returncode == 0                        # no force needed on main
    assert git(r, "rev-parse", "main").strip() == first


def test_a_non_local_remote_is_refused_without_live(tmp_path, remote):
    _, site = remote
    p = publish("git@github.com:goel12133/swarm-colosseum.git", site)
    assert p.returncode == 2 and "refusing" in p.stderr and "--live" in p.stderr


PRIVATE = ("CLAUDE.md", "FOUNDER_TODO.md", "DECISIONS.local.md")


def test_the_private_files_never_reach_the_public_mirror(tmp_path, remote):
    """Founder (2026-10-16): CLAUDE.md, FOUNDER_TODO.md and DECISIONS.local.md stay out of
    every commit after scripts/public_private_since; history up to it is unchanged."""
    import shutil
    r, site = remote
    live = tmp_path / "live"
    subprocess.run(["git", "clone", "-q", "-b", "master", str(ROOT), str(live)], check=True)
    for rel in ("scripts/rewrite_identity.sh", "scripts/publish.sh", "scripts/audit_secrets.py",
                "scripts/public_identity", "scripts/public_private_since"):
        shutil.copy2(ROOT / rel, live / rel)
    for name in PRIVATE:
        (live / name).write_text(f"private: {name}\n")
    lg = ["-c", "user.name=Swarm Colosseum league", "-c", "user.email=league@localhost"]
    git(live, "add", "-A")
    git(live, *lg, "commit", "-q", "-m", "after the cut-off")
    p = subprocess.run([str(live / "scripts" / "publish.sh"), "--site", str(site), str(r)],
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stderr
    files = git(r, "ls-tree", "-r", "--name-only", "main").split()
    assert not set(PRIVATE) & set(files)
    since = (ROOT / "scripts" / "public_private_since").read_text().strip()
    msg = git(ROOT, "log", "-1", "--format=%s", since).strip()
    old = [c for c in git(r, "rev-list", "main").split()
           if git(r, "log", "-1", "--format=%s", c).strip() == msg]
    assert old, "the cut-off commit is in the public history"
    for c in git(r, "rev-list", f"{old[0]}..main").split():        # everything newer
        assert not set(PRIVATE) & set(git(r, "ls-tree", "-r", "--name-only", c).split()), c
    # up to the cut-off nothing changed: what was public stays as it was, so main fast-forwards
    assert "DECISIONS.local.md" in git(r, "ls-tree", "-r", "--name-only", old[0]).split()
