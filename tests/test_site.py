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
    assert info["replays"] == len(list((dest / "replays" / "data").glob("*.json.gz"))) > 0
    pages = [p for p in (dest / "replays").glob("*.html") if p.name != "viewer.html"]
    assert info["full_pages"] == len(pages) > 0
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
            if target == site.REPO_URL:          # the footer's one link out: the code
                continue
            assert not re.match(r"^([a-z]+:|//)", target), f"external link in {page}: {target}"
            if target.startswith("#"):
                continue
            from html import unescape
            from urllib.parse import parse_qs
            path, _, query = unescape(target).split("#")[0].partition("?")
            resolved = (page.parent / path).resolve()
            for r in parse_qs(query).get("r", []):    # the viewer's on-demand replay
                data = (resolved.parent / r).resolve()
                assert data.exists(), f"{page.relative_to(dest)} -> {target}"
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
                 "ladders.html", "submitting.html", "changelog.html"):
        assert f'href="{href}"' in home, href
    for role in ("attackers", "defenders"):               # the top eight of each side
        top = [f'href="bots/{site.slugify(r["name"])}.html"' for r in lb[role]]
        assert all(t in home for t in top[:8])
        assert not any(t in home for t in top[8:])
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
        text = page.read_text()
        scripts = re.findall(r"<script([^>]*)>", text)
        if page.relative_to(dest).as_posix() == "replays/viewer.html":
            assert scripts == [""], page                   # the viewer's own, inline
        else:                                              # site.js only, never inline
            assert len(scripts) == 1 and re.fullmatch(r' src="(\.\./)*site\.js" defer',
                                                      scripts[0]), (page, scripts)


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


def test_nested_list_items_render_as_a_sub_list():
    html = site.md_to_html("- top\n  - child one\n    continued\n  - child two\n- next")
    assert html == ("<ul><li>top<ul><li>child one continued</li><li>child two</li></ul></li>"
                    "<li>next</li></ul>")


def test_the_build_writes_the_custom_domain_cname(tmp_path):
    """GitHub Pages keeps a custom domain only while gh-pages has CNAME at its root."""
    site.build(tmp_path / "site")
    assert (tmp_path / "site" / "CNAME").read_text() == "pelennor.tech"


def test_every_replay_is_packed_and_opens_from_the_index(bundle):
    from colosseum import replay_pack
    dest, _, info = bundle
    index = (dest / "replays.html").read_text()
    for data in (dest / "replays" / "data").glob("*.json.gz"):
        stem = data.name[:-len(".json.gz")]
        assert f'href="replays/data/{data.name}"' in index, stem
        page = dest / "replays" / f"{stem}.html"
        watch = (f"replays/{stem}.html" if page.exists()
                 else f"replays/viewer.html?r=data/{data.name}")
        assert f'href="{watch}"' in index, stem
        assert replay_pack.unpack(data.read_bytes())["frames"]
    viewer = (dest / "replays" / "viewer.html").read_text()
    assert "const SAMPLE = null;" in viewer and "loadFromQuery" in viewer


# --- the design pass (2026-10-10) -------------------------------------------------

def test_fonts_are_served_with_the_site_and_nothing_loads_from_elsewhere(bundle):
    dest, _, _ = bundle
    assert sorted(p.name for p in (dest / "fonts").glob("*.woff2")) == [
        "JetBrainsMono-latin.woff2", "SpaceGrotesk-latin.woff2"]
    assert len(list((dest / "fonts").glob("OFL-*.txt"))) == 2      # the fonts' licences
    css = (dest / "style.css").read_text()
    assert "url(fonts/SpaceGrotesk-latin.woff2)" in css and "googleapis" not in css
    for page in dest.rglob("*.html"):
        assert "googleapis" not in page.read_text() and "gstatic" not in page.read_text()


def test_light_mode_and_reduced_motion_in_the_site_and_the_viewer(bundle):
    dest, _, _ = bundle
    for text in ((dest / "style.css").read_text(), (dest / "replays" / "viewer.html").read_text()):
        assert "prefers-color-scheme" in text and 'data-theme="light"' in text
        assert "prefers-reduced-motion: reduce" in text.replace("motion:reduce", "motion: reduce")
    viewer = (dest / "replays" / "viewer.html").read_text()
    assert "REDUCED" in viewer and "big-play" in viewer        # the channel waits for a click
    js = (dest / "site.js").read_text()
    assert "sc-theme" in js and "sc-theme" in viewer               # one remembered choice


def test_nothing_claims_to_be_live(bundle):
    dest, _, _ = bundle
    for page in dest.rglob("*.html"):
        text = re.sub(r"<script.*?</script>", "", page.read_text(), flags=re.S)
        assert ">LIVE<" not in text and "Live now" not in text, page
    home = (dest / "index.html").read_text()
    assert ">REPLAY<" in home and "not a live feed" in home


def test_the_channel_lists_real_replays_of_the_bundle(bundle):
    dest, _, _ = bundle
    ch = json.loads((dest / "replays" / "channel.json").read_text())
    assert ch["items"] and ch["items"][0]["label"] == "#1 v #1"
    for it in ch["items"]:
        assert (dest / "replays" / it["data"]).exists() and it["frames"] > 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T03:30:00Z", ch["epoch"])


def test_movement_arrows_and_new_tags():
    before = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    now = [{"name": "c"}, {"name": "a"}, {"name": "n"}, {"name": "b"}]
    assert site.movement(now, before) == {"c": 2, "a": -1, "n": None, "b": -2}
    assert "▲ 2" in site.mv_html(2) and "▼ 1" in site.mv_html(-1) and "– 0" in site.mv_html(0)
    rows = [dict(name=n, elo=1000, win_rate=.5, mean_cer=1.0, matches=10) for n in "can"]
    html = site.ladder_rows(rows, {"c": 2, "a": -1, "n": None}, {})
    assert html.count("tag new") == 1 and 'aria-label="up 2"' in html


def test_the_recap_is_read_from_the_ledger():
    lb = lambda a, d: {"attackers": [dict(name=a, mean_cer=1)], "defenders": [dict(name=d, mean_cer=.5)]}
    hist = [("2026-10-01", lb("x", "y")), ("2026-10-02", lb("z", "y"))]
    rec = {"date": "2026-10-02", "status": "ok", "cache": {"matches": 20, "ran": 4},
           "house_positions": {"2026-10-02_attacker_z": dict(role="attacker", persona="counter_meta",
                                                             target="y", beat_target=True, rank=1)}}
    text = site.recap(rec, hist)
    assert "Night 2 (2026-10-02)" in text and "and beat it" in text and "counter-meta" in text
    assert "took the top attacker place from" in text and "held the top defender place for a second night" in text
    assert "20 matches" in text and "4 of" in text


def test_the_season_day_is_the_calendar_day_of_the_last_night(tmp_path):
    out = tmp_path / "out"
    run_tournament(seeds=1, out=out, write_replays=False, quiet=True, workers=1)
    board = (out / "leaderboard.json").read_text()
    for d in range(29, 31):                                # 09-28 backfilled: no folder
        (out / "history" / f"2026-09-{d}").mkdir(parents=True)
        (out / "history" / f"2026-09-{d}" / "leaderboard.json").write_text(board)
    for d in range(1, 17):
        (out / "history" / f"2026-10-{d:02d}").mkdir(parents=True)
        (out / "history" / f"2026-10-{d:02d}" / "leaderboard.json").write_text(board)
    dest = tmp_path / "site"
    site.build(dest, out, seasons=tmp_path / "no-seasons", research=tmp_path / "no-research")
    home = (dest / "index.html").read_text()
    assert "day <b>19</b> of 28" in home and 'aria-valuenow="19"' in home


def test_the_changelog_has_an_entry_per_night_newest_first(tmp_path):
    recs = [{"date": "2026-10-01", "status": "ok", "cache": {"matches": 10, "ran": 10},
             "house_positions": {}},
            {"date": "2026-10-02", "status": "failed", "reason": "generator timed out"}]
    hist = [("2026-10-01", {}), ("2026-10-02", {})]
    site.write_changelog(tmp_path, recs, hist)
    text = (tmp_path / "changelog.html").read_text()
    assert text.count('<section class="night">') == 2
    assert text.index("2026-10-02 · night 2") < text.index("2026-10-01 · night 1")
    assert "didn&#x27;t complete: generator timed out" in text or "didn't complete: generator timed out" in text
