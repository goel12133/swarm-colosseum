"""The front-door documents (L8): links resolve, the content check passes, citation is whole."""
import re
from pathlib import Path

import pytest

from colosseum import content_check

ROOT = Path(__file__).resolve().parents[1]
DOCS = ["README.md", "CONTRIBUTING.md", "LICENSING.md", "CITATION.cff"]


@pytest.mark.parametrize("name", DOCS)
def test_local_links_resolve(name):
    text = (ROOT / name).read_text()
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if "://" not in target:
            assert (ROOT / target).exists(), f"{name} links to missing {target}"


@pytest.mark.parametrize("name", DOCS)
def test_the_content_check_passes(name):
    assert content_check.findings((ROOT / name).read_text()) == []


def test_the_citation_has_its_required_keys_and_both_licences():
    text = (ROOT / "CITATION.cff").read_text()
    keys = {line.split(":", 1)[0] for line in text.splitlines()
            if line and not line.startswith((" ", "-"))}
    assert {"cff-version", "message", "title", "authors", "license"} <= keys
    # Founder, 2026-10-08: Apache-2.0 for code, CC BY 4.0 for replays and research.
    assert "- Apache-2.0" in text and "- CC-BY-4.0" in text
    assert (ROOT / "LICENSE").read_text().lstrip().startswith("Apache License")
    assert "Attribution 4.0 International" in (ROOT / "LICENSE-CC-BY-4.0").read_text()


def test_the_readme_says_submissions_are_closed_and_names_both_licences():
    text = (ROOT / "README.md").read_text()
    assert "submissions are not open yet" in text and "open on 2026-10-24" not in text
    assert "Apache License 2.0" in text and "CC BY 4.0" in text


def test_the_home_page_says_submissions_are_not_open_yet(tmp_path):
    from colosseum import site
    from colosseum.tournament import run_tournament
    out = tmp_path / "out"
    run_tournament(seeds=1, out=out, write_replays=False, quiet=True, workers=1)
    dest = tmp_path / "site"
    site.build(dest, out, seasons=tmp_path / "no-seasons", research=tmp_path / "no-research")
    home = (dest / "index.html").read_text()
    assert "outside submissions · not open yet" in home and "open 24 Oct" not in home


def test_citation_readme_and_summary_point_at_the_site_and_repo():
    for f in ("CITATION.cff", "README.md", "research/00_summary.md"):
        text = (ROOT / f).read_text()
        assert "https://pelennor.tech" in text and "github.io" not in text, f
        assert "https://github.com/goel12133/swarm-colosseum" in text, f
