"""Static site bundle: builds, every internal link resolves, every live bot is listed, the
tactic library and the season archive are linked, and the about page is there."""
import json
import re
from pathlib import Path

import pytest

from colosseum import library, site
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
    library.build(out / "library", out)
    seasons = tmp_path_factory.mktemp("seasons")
    (seasons / "S1" / "meta").mkdir(parents=True)
    (seasons / "S1" / "SEASON_REPORT.md").write_text(
        "# Season one\n\nSee [week 1](meta/WEEK_1.md), [gone](missing.md) and "
        "[out](https://example.com).\n")
    (seasons / "S1" / "meta" / "WEEK_1.md").write_text(
        "# Week 1\n\nBack to [the report](../SEASON_REPORT.md).\n")
    research = tmp_path_factory.mktemp("research")
    (research / "01_first.md").write_text(
        "# 01 · First <finding>\n\nSee [the second](02_second.md) and "
        "[outside](https://example.com) and [a file](../out/matrix.json).\n")
    (research / "02_second.md").write_text("# 02 · Second\n\nBack to [one](01_first.md).\n")
    dest = tmp_path_factory.mktemp("site") / "site"
    info = site.build(dest, out, seasons=seasons, research=research)
    return dest, lb, info


def test_the_bundle_builds(bundle):
    dest, lb, info = bundle
    for f in ("index.html", "ladders.html", "replays.html", "submitting.html", "style.css",
              "about.html", "seasons.html", "library/index.html", "research.html"):
        assert (dest / f).exists(), f
    assert info["research"] == 2
    assert info["replays"] == len(list((dest / "replays").glob("*.html"))) > 0
    assert info["cards"] == len(list((dest / "library" / "cards").glob("*.html"))) > 0
    assert info["seasons"] == 1


def test_every_page_links_the_library_the_seasons_and_the_about_page(bundle):
    dest, _, _ = bundle
    for page in dest.rglob("*.html"):
        if page.parent.name == "replays":
            continue                                   # the viewer's own page
        text = page.read_text()
        for target in ("index.html", "ladders.html", "library/index.html", "research.html",
                       "seasons.html", "about.html"):
            assert re.search(r'href="(\.\./)*' + re.escape(target) + '"', text), (page, target)


def test_the_library_index_links_every_card_and_cards_link_replay_pages(bundle):
    dest, _, info = bundle
    index = (dest / "library" / "index.html").read_text()
    cards = sorted((dest / "library" / "cards").glob("*.html"))
    for card in cards:
        assert f'href="cards/{card.name}"' in index, card.name
    linked = [c for c in cards if "../../replays/" in c.read_text()]
    assert linked, "no card links a replay page"
    for card in linked:
        assert ".json\"" not in card.read_text()
        assert "<pre><code>" in card.read_text()       # the source, as code


def test_the_season_archive_keeps_its_own_links_and_drops_the_rest(bundle):
    dest, _, _ = bundle
    seasons = (dest / "seasons.html").read_text()
    assert 'href="seasons/S1/SEASON_REPORT.html"' in seasons
    assert "2026-10-26" in seasons                     # SEASON.md rendered above the archive
    report = (dest / "seasons" / "S1" / "SEASON_REPORT.html").read_text()
    assert 'href="meta/WEEK_1.html"' in report
    assert "missing" not in report and "gone" in report
    assert "example.com" not in report
    week = (dest / "seasons" / "S1" / "meta" / "WEEK_1.html").read_text()
    assert 'href="../SEASON_REPORT.html"' in week and 'href="../../../style.css"' in week


def test_the_about_page_is_plain_and_states_the_abstract_only_rule(bundle):
    dest, _, _ = bundle
    about = (dest / "about.html").read_text()
    for heading in ("What this is", "Why it exists", "How a match works",
                    "How to read the ladder", "How to submit", "Abstract only"):
        assert f">{heading}" in about, heading
    assert "everything in the game is made up" in about
    assert 'href="submitting.html"' in about


def test_without_a_library_the_page_says_so(tmp_path):
    dest = tmp_path / "site"
    (dest / "replays").mkdir(parents=True)
    assert site.write_library(dest, tmp_path / "no-library") == 0
    assert "Not built yet" in (dest / "library" / "index.html").read_text()


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


def test_the_ladders_page_lists_every_live_bot(bundle):
    dest, lb, _ = bundle
    ladders = (dest / "ladders.html").read_text()
    for role in ("attackers", "defenders"):
        for r in lb[role]:
            assert f'href="bots/{site.slugify(r["name"])}.html"' in ladders, r["name"]
            assert (dest / "bots" / f"{site.slugify(r['name'])}.html").exists()


def test_the_home_page_starts_newcomers_and_shows_the_top_five(bundle):
    dest, lb, _ = bundle
    home = (dest / "index.html").read_text()
    assert "everything in the game is made up" in home.lower()
    for href in ("about.html", "replays.html", "library/index.html", "research.html",
                 "ladders.html"):
        assert f'class=card href="{href}"' in home or f'href="{href}">Full' in home, href
    for role in ("attackers", "defenders"):
        top = [f'href="bots/{site.slugify(r["name"])}.html"' for r in lb[role]]
        assert all(t in home for t in top[:5])
        assert not any(t in home for t in top[5:])
    assert 'href="research/01_first.html"' in home
    assert "Latest meta report" not in home


def test_research_pages_keep_links_between_them_and_drop_the_rest(bundle):
    dest, _, _ = bundle
    listing = (dest / "research.html").read_text()
    assert 'href="research/01_first.html"' in listing
    assert 'href="research/02_second.html"' in listing
    first = (dest / "research" / "01_first.html").read_text()
    assert 'href="02_second.html"' in first and 'href="../style.css"' in first
    assert "example.com" not in first and "matrix.json" not in first and "outside" in first
    assert "<finding>" not in first and "&lt;finding&gt;" in first
    assert 'href="01_first.html"' in (dest / "research" / "02_second.html").read_text()


def test_without_research_the_page_says_so(tmp_path):
    dest = tmp_path / "site"
    dest.mkdir()
    assert site.write_research(dest, tmp_path / "none") == []
    assert "Nothing written up yet" in (dest / "research.html").read_text()


def test_untrusted_text_is_escaped_and_no_script_but_the_viewers(bundle):
    dest, _, _ = bundle
    index = (dest / "ladders.html").read_text()
    assert "<script>x</script>" not in index and "&lt;script&gt;" in index
    assert "https://example.com" not in index                  # external link dropped
    for page in dest.rglob("*.html"):
        n = page.read_text().count("<script")
        assert n == (1 if page.parent.name == "replays" else 0), page


def test_markdown_renderer_escapes_everything():
    html = site.md_to_html('# <b>t</b>\n\n"quote" & <img src=x onerror=alert(1)>\n')
    assert "<img" not in html and "<b>" not in html
    assert "&lt;img" in html


def test_library_escapes_render_as_literal_text_and_never_as_markup():
    text = library.md_safe('<script>x</script> [a](b) `c` | d & \\ **e**')
    html = site.md_to_html(text)
    assert "<script" not in html and "<a " not in html and "<code>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html          # escaped once, not twice
    assert "[a](b)" in html and "`c`" in html and "| d &amp; \\" in html
    assert "" not in html


def test_an_escaped_pipe_stays_in_its_table_cell():
    html = site.md_to_html("| a | b |\n|---|---|\n| x \\| y | z |\n")
    assert "<td>x | y</td><td>z</td>" in html


def test_a_long_fence_is_closed_only_by_a_run_as_long():
    html = site.md_to_html("````python\nx = 1\n```\n# not a heading\n````\nafter\n")
    assert html.count("<pre>") == 1 and "<h1>" not in html
    assert "# not a heading" in html and html.endswith("<p>after</p>")


def test_the_public_site_drops_the_reports_health_section():
    text = "# Week 1\n\n## Ladders\n\nx\n\n## Health\n\nok  cron  30 3 * * * /root/x\n\n## After\n\ny\n"
    out = site.public_report(text)
    assert "## Health" not in out and "/root/x" not in out
    assert "## Ladders" in out and "## After" in out


def test_every_page_carries_the_licence_footer(bundle):
    dest, _, _ = bundle
    for page in dest.glob("*.html"):
        assert "Apache License 2.0" in page.read_text() and "CC BY 4.0" in page.read_text(), page
