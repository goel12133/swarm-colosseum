"""Static site bundle: prepared, not served.

    python -m colosseum.site            # writes out/site/

Everything is a local file, with no external requests, no fonts or scripts from elsewhere,
and no JavaScript except the replay viewer's own. Nothing serves it; the founder decides
where it goes.

    index.html              home: what this is, where to start, ladder tops, research
    ladders.html            both ladders in full, the latest meta report
    research.html           the research write-ups (research/*.md), one page each under
    research/<n>.html         research/, links between them kept and any other link dropped
    bots/<name>.html        docstring, persona, author, metadata, recent results
    replays.html            a picker (plain links) over every current replay
    replays/<stem>.html     the viewer with that replay embedded (viewer/build_viewer.page_with)
    library/index.html      the tactic library's INDEX.md (python -m colosseum.library)
    library/cards/<n>.html  one tactic card each, replay links pointing at replays/<stem>.html
    seasons.html            SEASON.md, then every archived season under seasons/
    seasons/<S>/<f>.html    each markdown file of an archived season
    about.html              ABOUT.md, the plain-language introduction
    submitting.html         SUBMITTING.md
    style.css               one stylesheet, light and dark

Bot names, docstrings, authors and metadata come from untrusted files, so every string is
HTML-escaped before it reaches a page, and bot files are read with `ast`, never imported.
The library's cards are already markdown-escaped (library.md_safe); the renderer here
honours those escapes and still HTML-escapes the result.
"""
import argparse
import ast
import html
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

from .tournament import DEFAULT_OUT, ROOT

SITE = DEFAULT_OUT / "site"
BOT_DIRS = ("attackers", "defenders", "house", "submitted/attacker", "submitted/defender")

CSS = """:root{--bg:#f4f6f8;--panel:#fff;--ink:#131a20;--soft:#5e6d79;--rule:#d4dce3;
--link:#1f5f9e;--good:#2f6f4f;--bad:#b23a2c;--code:#eef1f4}
@media (prefers-color-scheme:dark){:root{--bg:#0d1216;--panel:#151d23;--ink:#e6edf3;
--soft:#93a4b1;--rule:#25313a;--link:#7cb8f0;--good:#4fbd88;--bad:#ff7a66;--code:#1b252d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
nav{display:flex;flex-wrap:wrap;gap:12px;padding:12px 16px;border-bottom:1px solid var(--rule);
background:var(--panel)}
nav a{font-weight:600}
a{color:var(--link)}
h1{font-size:1.5rem;margin:.6em 0 .2em;overflow-wrap:anywhere}h2{font-size:1.2rem;margin:1.4em 0 .5em}
h3{font-size:1.05rem}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:12px 16px;
margin:12px 0}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.95rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule);white-space:nowrap}
td.name{white-space:normal;overflow-wrap:anywhere;min-width:9.5em}
.tag{white-space:nowrap}
@media (max-width:480px){.wide{display:none}}
.doc p,.doc li{overflow-wrap:anywhere}
th{color:var(--soft);font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;
background:var(--code);border-radius:4px}
code{padding:1px 4px}pre{padding:10px 12px;overflow-x:auto;white-space:pre-wrap}
.soft{color:var(--soft)}.good{color:var(--good)}.bad{color:var(--bad)}
.tag{display:inline-block;font-size:.8rem;padding:1px 8px;border-radius:99px;
border:1px solid var(--rule);color:var(--soft);margin-left:6px}
ul.picks{list-style:none;padding:0;margin:0}ul.picks li{padding:6px 0;
border-bottom:1px solid var(--rule)}
footer{max-width:860px;margin:24px auto 0;padding:16px;border-top:1px solid var(--rule);color:var(--soft);font-size:.85rem}
blockquote{margin:12px 0;padding:8px 12px;border-left:3px solid var(--rule);color:var(--soft)}
nav a.home{color:var(--ink);margin-right:auto}
.hero{padding:8px 0 4px}.hero h1{font-size:1.9rem;margin-bottom:.3em}
.lede{font-size:1.1rem;margin:.2em 0 .6em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;
margin:12px 0}
.grid .card{margin:0}a.card{display:block;text-decoration:none;color:inherit}
a.card:hover,a.card:focus{border-color:var(--link)}a.card h3{color:var(--link)}.grid h3{margin:.2em 0 .3em}.grid p{margin:0;color:var(--soft)}
.more{margin:4px 0 0;font-weight:600}
"""

e = html.escape


# --- a small, safe markdown renderer -----------------------------------------------

ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">"}


def _inline(text: str, link_map=None) -> str:
    """Escape first, then turn `code`, **bold**, *em* and [links](x) into tags.

    Backslash-escaped punctuation and the entities &amp; &lt; &gt; (what library.md_safe
    writes) are held aside as placeholders, so they never form markup, and come back as
    the literal character, HTML-escaped. `link_map` is a dict, or a function from target
    to target where None means "drop the link, keep the label"."""
    text = re.sub("[\ue000\ue001]", "", text)
    held = []

    def hold(ch):
        held.append(ch)
        return f"\ue000{len(held) - 1}\ue001"
    text = re.sub(r"&(?:amp|lt|gt);", lambda m: hold(ENTITIES[m.group(0)]), text)
    text = re.sub(r"\\([!-/:-@\[-`{-~])", lambda m: hold(m.group(1)), text)

    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{e(part[1:-1])}</code>")
            continue
        s = e(part, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![\w*\\])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", s)

        def link(m):
            label, target = m.group(1), m.group(2)
            if callable(link_map):
                target = link_map(target)
            else:
                target = (link_map or {}).get(target, target)
            if target is None or re.match(r"^[a-z]+:", target):   # no external links
                return label
            return f'<a href="{e(target)}">{label}</a>'
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
        out.append(s)
    return re.sub("\ue000(\\d+)\ue001", lambda m: e(held[int(m.group(1))]), "".join(out))


def table_cells(line: str):
    """Cells of a markdown table row; a backslash-escaped pipe stays inside its cell."""
    row = line.strip()[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def md_to_html(text: str, link_map=None) -> str:
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            fence = re.match(r"`+", line).group()     # closes only on a run this long
            j = i + 1
            code = []
            while j < len(lines) and not re.fullmatch(re.escape(fence) + r"`*\s*", lines[j]):
                code.append(lines[j])
                j += 1
            out.append(f"<pre><code>{e(chr(10).join(code))}</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2), link_map)}</h{n}>")
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(table_cells(lines[i]))
                i += 1
            body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            head, rest = body[0], body[1:]
            t = ["<div class=\"scroll\"><table><thead><tr>"]
            t += [f"<th>{_inline(c, link_map)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in rest:
                t.append("<tr>" + "".join(f"<td>{_inline(c, link_map)}</td>" for c in r)
                         + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            base = len(line) - len(line.lstrip())
            items = []      # [text, sub-items]: one level of nesting, by indent
            while i < len(lines) and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) or
                                      (lines[i].startswith("  ") and items)):
                indent = len(lines[i]) - len(lines[i].lstrip())
                if re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])
                    if indent > base and items:
                        items[-1][1].append(text)
                    else:
                        items.append([text, []])
                elif items[-1][1]:
                    items[-1][1][-1] += " " + lines[i].strip()
                else:
                    items[-1][0] += " " + lines[i].strip()
                i += 1
            tag = "ol" if ordered else "ul"
            html = []
            for text, sub in items:
                inner = ("<ul>" + "".join(f"<li>{_inline(x, link_map)}</li>" for x in sub)
                         + "</ul>") if sub else ""
                html.append(f"<li>{_inline(text, link_map)}{inner}</li>")
            out.append(f"<{tag}>" + "".join(html) + f"</{tag}>")
            continue
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(quote), link_map)}</blockquote>")
            continue
        if line.startswith("    ") and line.strip():
            code = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                code.append(lines[i][4:])
                i += 1
            out.append(f"<pre>{e(chr(10).join(code).rstrip())}</pre>")
            continue
        if not line.strip() or line.strip() == "---":
            i += 1
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|```|\||>|\s*([-*]|\d+\.)\s)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para), link_map)}</p>")
    return "\n".join(out)


# --- data -----------------------------------------------------------------------

def public_report(text: str) -> str:
    """The weekly report minus its Health section (machine, login, cron and disk details
    are for the founder, not for a public page)."""
    import re as _re
    return _re.sub(r"(?ms)^## Health\n.*?(?=^## |\Z)", "", text)


def bot_file(name: str):
    for d in BOT_DIRS:
        p = ROOT / "bots" / d / f"{name}.py"
        if p.exists():
            return p
    return None


def docstring(path: Path) -> str:
    try:
        return ast.get_docstring(ast.parse(path.read_text())) or ""
    except (SyntaxError, OSError):
        return ""


def read_meta(path):
    if not path:
        return {}
    m = path.with_suffix(".meta.json")
    return json.loads(m.read_text()) if m.exists() else {}


def origin(path: Path, meta: dict) -> str:
    if path and "submitted" in path.parts:
        return f"submitted by {meta.get('author', '?')}"
    if path and "house" in path.parts:
        persona = meta.get("persona")
        return "house league" + (f", persona {persona}" if persona else "")
    return "baseline"


def display(name: str) -> str:
    """Short name for pages: date/role prefix and submitter handle dropped."""
    m = re.match(r"\d{4}-\d{2}-\d{2}_(attacker|defender)_(.+)", name)
    if m:
        return m.group(2)
    return name.split("__", 1)[1] if "__" in name else name


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def page(title: str, body: str, depth: int = 0) -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(title)} · Swarm Colosseum</title>
<link rel="stylesheet" href="{up}style.css"></head>
<body><nav><a class="home" href="{up}index.html">Swarm Colosseum</a>
<a href="{up}ladders.html">Ladders</a><a href="{up}replays.html">Replays</a>
<a href="{up}library/index.html">Tactic library</a><a href="{up}research.html">Research</a>
<a href="{up}seasons.html">Seasons</a><a href="{up}submitting.html">Submit a bot</a>
<a href="{up}about.html">About</a></nav>
<main>{body}</main>
<footer>Code: Apache License 2.0 · Replays, results and research: CC BY 4.0 · Built by
Pelennor</footer></body></html>
"""


# --- build ----------------------------------------------------------------------

def ladder_table(rows, prefix: str = "") -> str:
    """One ladder as a table; `prefix` is the path from the page to the site root."""
    t = ["<div class=\"card scroll\"><table><thead><tr><th class=num>#</th><th>bot</th>"
         "<th class=num>Elo</th><th class=num>wins</th><th class=\"num wide\">mean score</th>"
         "</tr></thead><tbody>"]
    for i, r in enumerate(rows, 1):
        path = bot_file(r["name"])
        tag = origin(path, read_meta(path)).split(",")[0].split(" ")[0]
        tag = {"house": "house", "submitted": "submitted"}.get(tag, "baseline")
        t.append(f"<tr><td class=num>{i}</td><td class=name><a href=\"{prefix}bots/"
                 f"{e(slugify(r['name']))}.html\">{e(display(r['name']))}</a>"
                 f"<span class=tag>{e(tag)}</span></td>"
                 f"<td class=num>{r['elo']:.0f}</td>"
                 f"<td class=num>{r['win_rate']:.0%}</td>"
                 f"<td class=\"num wide\">{r['mean_score']:.3f}</td></tr>")
    t.append("</tbody></table></div>")
    return "".join(t)


def md_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def build(site: Path = SITE, out: Path = DEFAULT_OUT, library: Path = None,
          seasons: Path = ROOT / "seasons", research: Path = ROOT / "research") -> dict:
    library = library or out / "library"
    lb = json.loads((out / "leaderboard.json").read_text())
    matrix = json.loads((out / "matrix.json").read_text())["matrix"]
    if site.exists():
        shutil.rmtree(site)
    (site / "bots").mkdir(parents=True)
    (site / "replays").mkdir()
    (site / "style.css").write_text(CSS)

    replays = sorted((out / "replays").glob("*__*__s*.json"))
    live = {r["name"] for role in ("attackers", "defenders") for r in lb[role]}
    current = [p for p in replays if p.stem.split("__")[0] in live
               and p.stem.split("__")[1] in live]

    # replay pages, via the viewer's own page builder
    spec = importlib.util.spec_from_file_location("build_viewer",
                                                  ROOT / "viewer" / "build_viewer.py")
    viewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viewer)
    metas = {}
    for p in current:
        rep = json.loads(p.read_text())
        rep["meta"]["rules"] = {}
        metas[p.stem] = rep["meta"]
        (site / "replays" / f"{slugify(p.stem)}.html").write_text(viewer.page_with(rep))

    # ladders: both in full, then the latest meta report
    body = ["<h1>Ladders</h1>",
            "<p class=soft>Every bot plays every bot on the other side, on the same seeds, "
            "every night. <a href=\"about.html\">How to read this</a>.</p>"]
    for role in ("attackers", "defenders"):
        body.append(f"<h2>{role.capitalize()}</h2>{ladder_table(lb[role])}")
    reports = sorted((out / "meta").glob("WEEK_*.md"),
                     key=lambda p: int(re.search(r"\d+", p.stem).group()))
    body.append("<h2>Latest meta report</h2>")
    if reports:
        body.append(f"<div class=card>{md_to_html(public_report(reports[-1].read_text()))}"
                    "</div>")
    else:
        body.append("<p class=soft>No weekly report yet: the first is written after the "
                    "seventh night.</p>")
    (site / "ladders.html").write_text(page("Ladders", "\n".join(body)))

    papers = write_research(site, research)

    # home: what this is, where to start, the top of each ladder, the research
    body = ["<div class=hero><h1>Swarm Colosseum</h1>",
            "<p class=lede>An open arena where AI-written attackers and AI-written "
            "defenders play an abstract strategy game against each other, every night, "
            "and every match can be replayed and reproduced.</p>",
            "<p class=soft>Everything in the game is made up: the units, the distances, the "
            "rules. It is a strategy game and a research benchmark. "
            "<a href=\"about.html\">Read what this is</a>.</p></div>",
            "<h2>Start here</h2><div class=grid>"]
    for href, title, blurb in (
            ("about.html", "What this is", "How a match works and how to read the "
             "ladder, in plain language."),
            ("replays.html", "Watch a match", f"{len(current)} replays from the latest "
             "night, in the browser."),
            ("library/index.html", "Tactic library", "The ideas that worked, one card "
             "each: what it beats and what beats it."),
            ("research.html", "Research", "What the league found, written up with the "
             "numbers.")):
        body.append(f"<a class=card href=\"{href}\"><h3>{e(title)}</h3>"
                    f"<p>{e(blurb)}</p></a>")
    body.append("</div><h2>Top of the ladders</h2>")
    for role in ("attackers", "defenders"):
        body.append(f"<h3>{role.capitalize()}</h3>{ladder_table(lb[role][:5])}")
    body.append(f"<p class=more><a href=\"ladders.html\">Full ladders ({len(live)} bots) "
                "and the latest meta report</a></p>")
    if papers:
        body.append("<h2>Research</h2><div class=card><ul class=picks>")
        body += [f"<li><a href=\"{e(href)}\">{e(title)}</a></li>" for href, title in papers]
        body.append("</ul></div>")
    (site / "index.html").write_text(page("Home", "\n".join(body)))

    # bot pages
    for role in ("attackers", "defenders"):
        for r in lb[role]:
            write_bot_page(site, r, role, matrix, current, metas)

    # replay picker
    items = []
    for p in current:
        m = metas[p.stem]
        items.append(f"<li><a href=\"replays/{e(slugify(p.stem))}.html\">"
                     f"{e(display(p.stem.split('__')[0]))} vs "
                     f"{e(display(p.stem.split('__')[1]))}</a> <span class=soft>seed {m['seed']} · "
                     f"{e(m['outcome'])} · {m['ticks']} ticks</span></li>")
    (site / "replays.html").write_text(page("Replays", (
        f"<h1>Replays</h1><p class=soft>{len(current)} matches from the latest nightly "
        f"tournament. Each opens in the replay viewer.</p>"
        f"<div class=card><ul class=picks>{''.join(items)}</ul></div>")))

    sub = (ROOT / "SUBMITTING.md").read_text()
    (site / "submitting.html").write_text(page("Submit a bot", md_to_html(
        sub, link_map={"SEASON.md": "seasons.html"})))
    (site / "about.html").write_text(page("About", md_to_html(
        (ROOT / "ABOUT.md").read_text(),
        link_map={"SUBMITTING.md": "submitting.html", "SEASON.md": "seasons.html"})))
    cards = write_library(site, library)
    archived = write_seasons(site, seasons)
    return dict(site=str(site), bots=len(live), replays=len(current), cards=cards,
                seasons=archived, research=len(papers))


def write_research(site: Path, research: Path) -> list:
    """research.html and research/<n>.html from research/*.md. Links between the write-ups
    are kept; any other link is dropped (its label stays). Returns [(href, title)]."""
    docs = sorted(research.glob("*.md")) if research.is_dir() else []
    names = {p.name for p in docs}
    papers = []
    if docs:
        (site / "research").mkdir()
    for p in docs:
        text = p.read_text()
        title = md_title(text, p.stem)
        href = f"research/{slugify(p.stem)}.html"
        (site / href).write_text(page(title, md_to_html(
            text, lambda t: f"{slugify(t[:-3])}.html" if t in names else None), 1))
        papers.append((href, title))
    body = ["<h1>Research</h1>",
            "<p class=soft>What the league has found so far. Every number in these "
            "write-ups comes from the league's own records and can be regenerated with "
            "<code>make reproduce</code>.</p>"]
    if papers:
        body.append("<div class=card><ul class=picks>")
        body += [f"<li><a href=\"{e(h)}\">{e(t)}</a></li>" for h, t in papers]
        body.append("</ul></div>")
    else:
        body.append("<p class=soft>Nothing written up yet.</p>")
    (site / "research.html").write_text(page("Research", "\n".join(body)))
    return papers


def write_library(site: Path, library: Path) -> int:
    """The tactic library (python -m colosseum.library) as pages. Cards are rendered from
    their markdown; replay links become the bundle's viewer pages. Returns the card count."""
    dest = site / "library"
    (dest / "cards").mkdir(parents=True)
    index = library / "INDEX.md"
    entries = []
    if (library / "library.json").exists() and index.exists():
        entries = json.loads((library / "library.json").read_text())["cards"]
    if not entries:
        (dest / "index.html").write_text(page("Tactic library", (
            "<h1>Tactic library</h1><p class=soft>Not built yet. It appears after the next "
            "night, once <code>python -m colosseum.library</code> has run.</p>"), 1))
        return 0

    def card_link(target):
        m = re.search(r"(?:^|/)replays/([^/]+)\.json$", target)
        if not m:
            return None
        stem = slugify(unquote(m.group(1)))
        if (site / "replays" / f"{stem}.html").exists():
            return f"../../replays/{stem}.html"
        return "../../replays.html"

    pages = {}
    for entry in entries:
        stem = slugify(Path(entry["card"]).stem)
        md = library / "cards" / f"{stem}.md"
        if not md.exists():
            continue
        pages[entry["card"]] = f"cards/{stem}.html"
        body = []
        if (site / "bots" / f"{slugify(entry['name'])}.html").exists():
            body.append(f"<p class=soft><a href=\"../../bots/{slugify(entry['name'])}.html\">"
                        "On the ladder now</a></p>")
        body.append(md_to_html(md.read_text(), card_link))
        (dest / "cards" / f"{stem}.html").write_text(
            page(display(entry["name"]), "\n".join(body), 2))
    (dest / "index.html").write_text(page("Tactic library", md_to_html(
        index.read_text(), pages.get), 1))
    return len(pages)


def write_seasons(site: Path, seasons: Path) -> int:
    """seasons.html: SEASON.md, then every archived season's markdown as pages, links
    between them kept and any other link dropped. Returns the number of archived seasons."""
    body = [md_to_html((ROOT / "SEASON.md").read_text(), lambda t: None),
            "<h2>Archive</h2>"]
    seasons = seasons.resolve()
    archived = sorted(d for d in seasons.glob("*") if d.is_dir()) if seasons.is_dir() else []
    if not archived:
        body.append("<p class=soft>No season has finished yet. When one ends, its ladders, "
                    "bots and season report are archived here.</p>")

    def html_path(md: Path) -> Path:
        rel = md.relative_to(seasons)
        return site / "seasons" / Path(*(slugify(x) for x in rel.with_suffix(".html").parts))

    for d in archived:
        docs = sorted(p for p in d.rglob("*.md") if p.is_file())
        known = {p.resolve() for p in docs}
        items = []
        for p in docs:
            target = html_path(p)

            def link(t, p=p, target=target):
                ref = (p.parent / unquote(t.split("#")[0])).resolve()
                if ref not in known:
                    return None
                return Path(os.path.relpath(html_path(ref), target.parent)).as_posix()
            target.parent.mkdir(parents=True, exist_ok=True)
            depth = len(target.relative_to(site).parts) - 1
            target.write_text(page(f"{d.name}: {p.stem}", md_to_html(p.read_text(), link),
                                   depth))
            items.append(f"<li><a href=\"{e(target.relative_to(site).as_posix())}\">"
                         f"{e(p.relative_to(d).as_posix())}</a></li>")
        body.append(f"<h3>{e(d.name)}</h3><div class=card><ul class=picks>{''.join(items)}"
                    "</ul></div>")
    (site / "seasons.html").write_text(page("Seasons", "\n".join(body)))
    return len(archived)


def write_bot_page(site, row, role, matrix, current, metas):
    name = row["name"]
    path = bot_file(name)
    meta = read_meta(path)
    doc = docstring(path) if path else ""
    me = "attacker" if role == "attackers" else "defender"
    body = [f"<h1>{e(display(name))}</h1>",
            f"<p class=soft>{e(me)} · {e(origin(path, meta))} · Elo {row['elo']:.0f} · "
            f"wins {row['win_rate']:.0%}<br><code>{e(name)}</code></p>",
            "<h2>What it says it does</h2>",
            f"<div class=\"card doc\">{md_to_html(doc) if doc else '<p>No docstring.</p>'}"
            "</div>"]
    if meta:
        body.append("<h2>Record</h2><div class=\"card scroll\"><table><tbody>")
        for k in sorted(meta):
            v = meta[k]
            if isinstance(v, dict):
                v = ", ".join(f"{a}: {b}" for a, b in v.items())
            elif isinstance(v, list):
                v = ", ".join(map(str, v))
            body.append(f"<tr><th>{e(str(k))}</th><td style=\"white-space:normal\">"
                        f"{e(str(v))}</td></tr>")
        body.append("</tbody></table></div>")

    # its own side's mean score against each opponent
    if me == "attacker":
        per = {d: 1 - s for d, s in matrix.get(name, {}).items()}
    else:
        per = {a: r[name] for a, r in matrix.items() if name in r}
    body.append("<h2>Against each opponent</h2><div class=\"card scroll\"><table><thead>"
                "<tr><th>opponent</th><th class=num>its mean score</th></tr></thead><tbody>")
    for opp, s in sorted(per.items(), key=lambda kv: -kv[1]):
        body.append(f"<tr><td class=name><a href=\"{e(slugify(opp))}.html\">"
                    f"{e(display(opp))}</a></td>"
                    f"<td class=num>{s:.3f}</td></tr>")
    body.append("</tbody></table></div>")

    mine = [p for p in current if p.stem.split("__")[0 if me == "attacker" else 1] == name]
    mine.sort(key=lambda p: (-int(p.stem.rsplit("__s", 1)[1]), p.stem))
    body.append("<h2>Ten most recent matches</h2><p class=soft>From the latest nightly "
                "tournament.</p><div class=\"card scroll\"><table><thead><tr>"
                "<th>opponent</th><th class=num>seed</th><th>outcome</th>"
                "<th class=num>its score</th><th>replay</th></tr></thead><tbody>")
    for p in mine[:10]:
        m = metas[p.stem]
        opp = m["defender"] if me == "attacker" else m["attacker"]
        score = m["score_attacker"] if me == "attacker" else m["score_defender"]
        won = (m["outcome"] == "breached") == (me == "attacker")
        body.append(f"<tr><td class=name>{e(display(opp))}</td><td class=num>{m['seed']}</td>"
                    f"<td class=\"{'good' if won else 'bad'}\">{e(m['outcome'])}</td>"
                    f"<td class=num>{score:.3f}</td><td><a href=\"../replays/"
                    f"{e(slugify(p.stem))}.html\">watch</a></td></tr>")
    body.append("</tbody></table></div>")
    (site / "bots" / f"{slugify(name)}.html").write_text(page(name, "\n".join(body), 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=SITE)
    args = ap.parse_args()
    info = build(args.out)
    size = sum(f.stat().st_size for f in Path(info["site"]).rglob("*") if f.is_file())
    print(f"{info['site']}: {info['bots']} bots, {info['replays']} replays, "
          f"{info['cards']} tactic cards, {info['research']} research pages, "
          f"{info['seasons']} archived seasons, "
          f"{size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
