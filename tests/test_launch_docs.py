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
    assert "submissions are not open yet" in text
    assert "Apache License 2.0" in text and "CC BY 4.0" in text
