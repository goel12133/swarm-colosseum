"""Static site bundle: builds, every internal link resolves, every live bot is listed."""
import json
import re
from pathlib import Path

import pytest

from colosseum import site
from colosseum.tournament import run_tournament

LINK = re.compile(r'(?:href|src)="([^"]*)"')


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    lb, _, _ = run_tournament(seeds=1, out=out, write_replays=True, quiet=True, workers=1)
    (out / "meta").mkdir()
    (out / "meta" / "WEEK_1.md").write_text(
        "# Week 1 — test\n\n| # | attacker |\n|---|---|\n| 1 | <script>x</script> |\n\n"
        "- **bold** and `code` and [a link](https://example.com)\n")
    dest = tmp_path_factory.mktemp("site") / "site"
    info = site.build(dest, out)
    return dest, lb, info


def test_the_bundle_builds(bundle):
    dest, lb, info = bundle
    for f in ("index.html", "replays.html", "submitting.html", "style.css"):
        assert (dest / f).exists(), f
    assert info["replays"] == len(list((dest / "replays").glob("*.html"))) > 0


def test_every_link_resolves_inside_the_bundle(bundle):
    dest, _, _ = bundle
    checked = 0
    for page in dest.rglob("*.html"):
        for target in LINK.findall(page.read_text()):
            assert not re.match(r"^([a-z]+:|//)", target), f"external link in {page}: {target}"
            if target.startswith("#"):
                continue
            resolved = (page.parent / target.split("#")[0]).resolve()
            assert resolved.exists(), f"{page.relative_to(dest)} -> {target}"
            assert resolved.is_relative_to(dest.resolve())
            checked += 1
    assert checked > 50


def test_the_index_lists_every_live_bot(bundle):
    dest, lb, _ = bundle
    index = (dest / "index.html").read_text()
    for role in ("attackers", "defenders"):
        for r in lb[role]:
            assert f'href="bots/{site.slugify(r["name"])}.html"' in index, r["name"]
            assert (dest / "bots" / f"{site.slugify(r['name'])}.html").exists()


def test_untrusted_text_is_escaped_and_no_script_but_the_viewers(bundle):
    dest, _, _ = bundle
    index = (dest / "index.html").read_text()
    assert "<script>x</script>" not in index and "&lt;script&gt;" in index
    assert "https://example.com" not in index                  # external link dropped
    for page in dest.rglob("*.html"):
        n = page.read_text().count("<script")
        assert n == (1 if page.parent.name == "replays" else 0), page


def test_markdown_renderer_escapes_everything():
    html = site.md_to_html('# <b>t</b>\n\n"quote" & <img src=x onerror=alert(1)>\n')
    assert "<img" not in html and "<b>" not in html
    assert "&lt;img" in html
