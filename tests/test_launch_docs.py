"""The front-door documents (L8): links resolve, the content check passes, citation is whole."""
import re
from pathlib import Path

import pytest

from colosseum import content_check

ROOT = Path(__file__).resolve().parents[1]
DOCS = ["README.md", "CONTRIBUTING.md", "LICENSE_NOTE.md", "CITATION.cff"]


@pytest.mark.parametrize("name", DOCS)
def test_local_links_resolve(name):
    text = (ROOT / name).read_text()
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if "://" not in target:
            assert (ROOT / target).exists(), f"{name} links to missing {target}"


@pytest.mark.parametrize("name", DOCS)
def test_the_content_check_passes(name):
    assert content_check.findings((ROOT / name).read_text()) == []


def test_the_citation_has_its_required_keys_and_no_licence_yet():
    keys = {line.split(":", 1)[0] for line in (ROOT / "CITATION.cff").read_text().splitlines()
            if line and not line.startswith((" ", "-"))}
    assert {"cff-version", "message", "title", "authors"} <= keys
    # No licence is chosen (LICENSE_NOTE.md); the citation must not claim one.
    assert "license" not in keys and not (ROOT / "LICENSE").exists()


def test_the_readme_says_submissions_are_closed_and_no_licence_is_granted():
    text = (ROOT / "README.md").read_text()
    assert "submissions are not open yet" in text
    assert "no licence is granted" in text
