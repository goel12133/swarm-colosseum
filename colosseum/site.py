"""Static site bundle, built every night from the live data: python -m colosseum.site.

The design (2026-10-10) is the founder's reference (design_ref/, not committed) carried into
this generator: colosseum/site_assets/style.css and site.js, fonts served with the site
(assets/fonts, SIL OFL 1.1). A page makes no outside request; its only link out is the
code repository. Every page works without JavaScript: site.js only adds the theme button,
ladder sorting, the framed viewer's height and the header's "now showing" line.

    index.html              the arena: the replay channel, figures, ladder tops, last
                            night's recap, results, three doors, the season strip
    ladders.html            both ladders in full (sortable), the latest meta report
    bots/<name>.html        a bot: rank, figures, head to head, best and worst match, source
    replays.html            every current replay: its page or the viewer, and its data
    replays/viewer.html     the viewer (viewer/template.html): ?r= one packed replay;
                            ?mode=broadcast&channel=channel.json the replay channel
    replays/channel.json    last night's featured matches, on a clock everyone shares
    replays/data/<stem>.json.gz   every current replay, packed (colosseum/replay_pack.py)
    replays/<stem>.html     full pages, only for the matches site.full_page_stems picks
    research.html           the write-ups (research/*.md), one page each under research/
    changelog.html          one entry per night, newest first, from out/nights.jsonl
    library/index.html      the tactic library; library/cards/<n>.html one card each
    seasons.html            SEASON.md and every archived season under seasons/
    about.html, submitting.html   ABOUT.md; SUBMITTING.md and CONTRIBUTING.md
    style.css, site.js, fonts/, CNAME

Nothing on any page claims to be live: the league plays at 03:30 UTC in the sandbox, and
the home page's channel replays those matches, labelled REPLAY.

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
from datetime import date
from pathlib import Path
from urllib.parse import unquote

from .tournament import DEFAULT_OUT, ROOT

SITE = DEFAULT_OUT / "site"
BOT_DIRS = ("attackers", "defenders", "house", "submitted/attacker", "submitted/defender")

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


def md_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


# --- which replays get a full page (post-launch site trim, founder, 2026-10-10) ---------

NIGHT_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})_")


def match_night(stem: str, first_night: str) -> str:
    """The night a match was first played: the later of its two bots' first nights (a house
    bot's name starts with it; baselines have been there since the season began)."""
    nights = [m.group(1) for name in stem.split("__")[:2] if (m := NIGHT_PREFIX.match(name))]
    return max(nights + [first_night])


def full_page_stems(metas: dict, as_of: str, first_night: str) -> set:
    """The rule: a full replay page for every match first played in the current or the
    previous week of the season (weeks counted from first_night, the week of as_of being
    current), plus each live bot's best and worst match by its own score. Every other
    replay is data only, opened by the viewer on demand. metas: {stem: replay meta}."""
    from datetime import date
    def week(night):
        return (date.fromisoformat(night) - date.fromisoformat(first_night)).days // 7
    now = week(as_of)
    keep = {s for s in metas if week(match_night(s, first_night)) >= now - 1}
    by_bot = {}
    for s, m in metas.items():
        by_bot.setdefault(("attacker", m["attacker"]), []).append((m["score_attacker"], s))
        by_bot.setdefault(("defender", m["defender"]), []).append((m["score_defender"], s))
    for scored in by_bot.values():
        keep.add(min(scored, key=lambda x: (x[0], x[1]))[1])        # worst (ties: first stem)
        keep.add(min(scored, key=lambda x: (-x[0], x[1]))[1])       # best
    return keep


def replay_href(stem: str, full: set, up: str = "") -> str:
    """A match's link: its full page if it has one, else the viewer on its data file."""
    slug = slugify(stem)
    if stem in full:
        return f"{up}replays/{slug}.html"
    return f"{up}replays/viewer.html?r=data/{slug}.json.gz"


# The trimmed site's size target (founder, 2026-10-10); after-night alerts above it.
SIZE_BUDGET = 60_000_000


def bundle_bytes(site: Path) -> int:
    return sum(f.stat().st_size for f in Path(site).rglob("*") if f.is_file())


# The site's custom domain (founder, 2026-10-10). GitHub Pages reads it from a CNAME file at
# the root of gh-pages; publish.sh pushes the whole build, so every publish keeps it.
DOMAIN = "pelennor.tech"



# --- the night's data: ladders over time, the ledger, the research -----------------

def history(out: Path) -> list:
    """[(night, leaderboard)] from out/history/<night>/leaderboard.json, oldest first."""
    h = out / "history"
    rows = []
    for d in sorted(p for p in h.iterdir() if p.is_dir()) if h.is_dir() else []:
        f = d / "leaderboard.json"
        if f.exists():
            rows.append((d.name, json.loads(f.read_text())))
    return rows


def ledger(out: Path) -> list:
    """out/nights.jsonl, one record per night, oldest first (dry runs left out)."""
    p = out / "nights.jsonl"
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    return [r for r in recs if not r.get("dry_run")]


def nights_run(recs: list, hist: list) -> int:
    """Nights run: distinct ledger dates with status ok, up to the last ladder snapshot. Not
    len(hist): a backfilled night (2026-09-28) is in the ledger but left no snapshot."""
    if not hist:
        return 0
    last = hist[-1][0]
    return len({r["date"] for r in recs if r.get("status") == "ok" and r.get("date", "") <= last})


def movement(now: list, before: list) -> dict:
    """{name: places moved since the night before} for one side's ladder rows: positive is
    up; None for a bot that wasn't on the earlier ladder (new)."""
    was = {r["name"]: i for i, r in enumerate(before)}
    return {r["name"]: (was[r["name"]] - i if r["name"] in was else None)
            for i, r in enumerate(now)}


def first_nights(hist: list) -> dict:
    """{bot: (night number, date) it first appeared on a ladder}."""
    seen = {}
    for n, (night, lb) in enumerate(hist, 1):
        for role in ("attackers", "defenders"):
            for r in lb[role]:
                seen.setdefault(r["name"], (n, night))
    return seen


def mv_html(d) -> str:
    if d is None:
        return '<span class="mv flat">–</span>'
    if d > 0:
        return f'<span class="mv up" aria-label="up {d}">▲ {d}</span>'
    if d < 0:
        return f'<span class="mv down" aria-label="down {-d}">▼ {-d}</span>'
    return '<span class="mv flat" aria-label="no change">– 0</span>'


def target_name(t) -> str:
    return "the field" if not t or t == "field" else display(t)


def held_for(hist: list, role: str) -> int:
    """How many nights running the current #1 of a side has been #1."""
    if not hist:
        return 0
    top, n = hist[-1][1][role][0]["name"], 0
    for _, lb in reversed(hist):
        if lb[role] and lb[role][0]["name"] == top:
            n += 1
        else:
            break
    return n


def ordinal(n: int) -> str:
    words = {2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh"}
    return words.get(n, f"{n}th")


def recap(rec: dict, hist: list, night: int = None) -> str:
    """Last night in one paragraph, every clause read from the ledger and the ladders."""
    if not rec or not hist:
        return "No night has run yet."
    lb = hist[-1][1]
    parts = [f"Night {len(hist) if night is None else night} ({e(rec['date'])})."]
    wrote = []
    for name, pos in sorted((rec.get("house_positions") or {}).items()):
        target = target_name(pos.get("target"))
        verdict = "and beat it" if pos.get("beat_target") else "and didn't beat it"
        persona = str(pos.get("persona", "")).replace("_", "-")
        wrote.append(f"<span class=mono>{e(display(name))}</span> ({e(pos['role'])}, "
                     f"{e(persona)} persona, aimed at <span class=mono>{e(target)}</span> "
                     f"{verdict}" + (f"; it entered the ladder at #{pos['rank']})" if pos.get("rank")
                                   else ")"))
    if wrote:
        parts.append("The league wrote " + " and ".join(wrote) + ".")
    elif rec.get("status") == "ok":
        parts.append("The league wrote no new bot.")
    for role, word in (("attackers", "attacker"), ("defenders", "defender")):
        top = lb[role][0]["name"]
        prev = hist[-2][1][role][0]["name"] if len(hist) > 1 else None
        n = held_for(hist, role)
        if prev and prev != top:
            parts.append(f"<span class=mono>{e(display(top))}</span> took the top {word} place "
                         f"from <span class=mono>{e(display(prev))}</span>.")
        else:
            parts.append(f"<span class=mono>{e(display(top))}</span> held the top {word} "
                         f"place{f' for a {ordinal(n)} night' if n > 1 else ''}.")
    cache = rec.get("cache") or {}
    cer = [r["mean_cer"] for r in lb["defenders"]]
    if cache and cer:
        parts.append(f"{cache['matches']:,} matches make up the ladder, {cache['ran']:,} of "
                     f"them played for the first time last night; the defenders' mean cost "
                     f"exchange was {sum(cer) / len(cer):.2f}.")
    for name in rec.get("retired") or []:
        parts.append(f"<span class=mono>{e(display(name))}</span> was retired.")
    return " ".join(parts)


def beat_their_target(recs: list) -> int:
    """House bots that beat the bot they were written to beat, over every night."""
    return len({n for r in recs for n, v in (r.get("house_positions") or {}).items()
                if v.get("beat_target")})


def paper_info(p: Path) -> dict:
    """A research write-up's number, title, status, one-line summary and date."""
    import subprocess
    text = p.read_text()
    m = re.match(r"(\d+)", p.stem)
    status = "preliminary" if "preliminary" in text[:600].lower() else "final"
    bottom = re.search(r"\*\*Bottom line:?\*\*:?\s*(.+?)(?:\n\n|$)", text, re.S)
    if bottom:
        summary = " ".join(bottom.group(1).split())
    else:
        def prose(b):           # not a heading, table, list, or an all-italic subtitle
            b = b.strip()
            return (b and not b.startswith(("#", "|", "- ", "* ", "---"))
                    and not re.match(r"\d+\.\s", b)
                    and not (b.startswith("*") and not b.startswith("**")))
        paras = [b for b in text.split("\n\n")[1:] if prose(b)]
        summary = " ".join(paras[0].split()) if paras else ""
    summary = re.sub(r"\(\S+?\.md\)|[*_`\[\]]", "", summary)
    summary = summary[:1].upper() + summary[1:]
    if len(summary) > 160:
        summary = summary[:160].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    try:
        when = subprocess.run(["git", "-C", str(p.parent), "log", "-1", "--format=%cs", "--",
                               p.name], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        when = ""
    title = re.sub(r"^\d+\s*·\s*", "", md_title(text, p.stem))      # the number is shown apart
    return dict(n=m.group(1) if m else "", title=title, status=status,
                summary=summary, when=when, stem=p.stem)


# --- page chrome ----------------------------------------------------------------

NAV = (("index.html", "Arena", "home", True), ("ladders.html", "Ladders", "ladders", True),
       ("replays.html", "Replays", "replays", True),
       ("research.html", "Research", "research", False),
       ("library/index.html", "Library", "library", False),
       ("changelog.html", "Changelog", "changelog", False),
       ("seasons.html", "Seasons", "seasons", False), ("about.html", "About", "about", False))
REPO_URL = "https://github.com/goel12133/swarm-colosseum"
CHROME = {}            # set by build(): the night and the replay channel's first match
ASSETS = Path(__file__).resolve().parent / "site_assets"
FONTS = ROOT / "assets" / "fonts"


def page(title: str, body: str, depth: int = 0, current: str = "") -> str:
    """Every page: the header (wordmark, the replay channel's indicator, the nav), the body,
    the footer. The indicator reads right without JavaScript (CHROME, from the build);
    site.js keeps it in step with the channel's clock."""
    up = "../" * depth
    cur = lambda key: ' aria-current="page"' if key == current else ""
    links = "".join(f'<a href="{up}{h}"{cur(k)}{"" if always else " class=wide"}>{e(t)}</a>'
                    for h, t, k, always in NAV)
    more = "".join(f'<a href="{up}{h}"{cur(k)}>{e(t)}</a>'
                   for h, t, k, always in NAV if not always)
    who = CHROME.get("who") or "no replays yet"
    night = CHROME.get("night")
    built = (f"built from night {night} ({e(CHROME.get('date', ''))})" if night
             else "built before the first night")
    return f"""<!doctype html>
<html lang="en" data-root="{up}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>{e(title)} · Swarm Colosseum</title>
<meta name="description" content="An open arena where AI-written strategies play an abstract game every night: ladders, replays, research.">
<link rel="stylesheet" href="{up}style.css"></head><body>
<a class="skip" href="#main">Skip to the content</a>
<header class="hdr"><div class="wrap">
<div class="hdr-row"><a class="wordmark" href="{up}index.html">Swarm Colosseum</a>
<a class="live" href="{up}index.html#broadcast" aria-label="Now showing a replay from night {e(str(night or ''))}: {e(who)}"><span class="dot" aria-hidden="true"></span><b>REPLAY</b><span class="who">{e(who)}</span></a></div>
<nav class="nav" aria-label="Primary">{links}<a href="{up}submitting.html" class="submit"{cur("submit")}>Submit</a><details><summary>More</summary><div class="more-menu">{more}</div></details></nav>
</div></header><main id="main">{body}</main>
<footer class="ftr"><div class="wrap">
<span>Code: Apache License 2.0 · Replays, results and research: CC BY 4.0</span><a href="{REPO_URL}">GitHub</a><span>built by Pelennor</span>
<span class="t3">{built}</span>
<button class="theme-btn" type="button" id="theme" aria-label="Toggle light and dark theme" hidden>Theme</button>
</div></footer>
<script src="{up}site.js" defer></script></body></html>
"""


def page_head(title: str, lede: str = "") -> str:
    return (f'<div class="page-head"><h1>{e(title)}</h1>'
            + (f"<p>{lede}</p>" if lede else "") + "</div>")


def kind_tag(path, meta) -> str:
    o = origin(path, meta)
    if o.startswith("house"):
        persona = meta.get("persona")
        return "house" + (f" · {persona.replace('_', '-')}" if persona else "")
    if o.startswith("submitted"):
        return "@" + str(meta.get("author", "?"))
    return "baseline"


def ladder_rows(rows, moves, firsts, prefix="", full=False) -> str:
    """Table rows for one side; full=True adds CER, matches, kind and first night."""
    out = []
    for i, r in enumerate(rows, 1):
        name = r["name"]
        path = bot_file(name)
        meta = read_meta(path)
        mv = moves.get(name)
        new = ' <span class="tag new">new</span>' if name in moves and mv is None else ""
        cells = [f'<td class="rk num" data-v="{i}">{i}</td>',
                 f'<td class="name"><a href="{prefix}bots/{e(slugify(name))}.html">'
                 f'{e(display(name))}</a>{new}</td>',
                 f'<td class="num" data-v="{r["elo"]:.1f}">{r["elo"]:.0f}</td>',
                 f'<td class="num" data-v="{r["win_rate"] * 100:.1f}">{r["win_rate"]:.1%}</td>']
        if full:
            cells += [f'<td class="num hide-sm" data-v="{r["mean_cer"]:.3f}">{r["mean_cer"]:.2f}</td>',
                      f'<td class="num hide-sm" data-v="{r["matches"]}">{r["matches"]:,}</td>']
        cells.append(f'<td class="num" data-v="{mv if mv is not None else 0}">{mv_html(mv)}</td>')
        if full:
            n, _ = firsts.get(name, (0, ""))
            cells += [f'<td class="t2 hide-sm">{e(kind_tag(path, meta))}</td>',
                      f'<td class="mono t3 hide-sm" data-v="{n:03d}">night {n}</td>']
        out.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(out)


def ladder_panel(role, rows, moves, firsts, prefix="", full=False, link=True) -> str:
    side = "att" if role == "attackers" else "def"

    def th(k, label, cls=""):
        if full:
            return f'<th data-k="{k}" class="{cls}"><button type="button">{label}</button></th>'
        return f'<th class="{cls}">{label}</th>'
    head = [th("rk", "#", "num"), th("name", "Bot"), th("elo", "Elo", "num"),
            th("wr", "Win", "num")]
    if full:
        head += [th("cer", "CER", "num hide-sm"), th("m", "Matches", "num hide-sm")]
    head.append(th("mv", "Δ night", "num"))
    if full:
        head += [th("who", "Kind", "hide-sm"), th("first", "First", "hide-sm")]
    more = f'<a href="{prefix}ladders.html#{role}">full ladder →</a>' if link else ""
    return (f'<section class="panel {side}-side" id="{role}" aria-label="{role.capitalize()} '
            f'ladder"><div class="panel-head"><span class="side-tag {side}">{role.capitalize()}'
            f'</span>{more}</div><div class="tbl-wrap"><table{" data-sort" if full else ""}>'
            f'<thead><tr>{"".join(head)}</tr></thead><tbody>'
            f'{ladder_rows(rows, moves, firsts, prefix, full)}</tbody></table></div></section>')


# --- the replay channel ---------------------------------------------------------

def channel(metas: dict, lb: dict, rec: dict, out: Path, night: int) -> dict:
    """Last night's featured matches for the home page's replay channel, in order: #1
    attacker v #1 defender (their longest match), each bot written last night in its best
    match, and the night's biggest upset (the lowest-ranked attacker to breach a top-three
    defender). Played back to back on a shared clock from 03:30 UTC of that night."""
    rank = {r["name"]: i for role in ("attackers", "defenders")
            for i, r in enumerate(lb[role], 1)}
    picks = []

    def add(stem, label):
        if stem and stem not in [s for s, _ in picks]:
            picks.append((stem, label))
    who = lambda s: s.split("__")[:2]          # (attacker, defender) file names
    ta, td = lb["attackers"][0]["name"], lb["defenders"][0]["name"]
    top = [s for s in metas if who(s) == [ta, td]]
    add(max(top, key=lambda s: (metas[s]["ticks"], s), default=None), "#1 v #1")
    for name, pos in sorted((rec.get("house_positions") or {}).items()):
        side = "attacker" if pos["role"] == "attacker" else "defender"
        mine = [s for s in metas if who(s)[side == "defender"] == name]
        add(max(mine, key=lambda s: (metas[s][f"score_{side}"], s), default=None),
            "new last night")
    upsets = [s for s, m in metas.items() if m["outcome"] == "breached"
              and rank.get(who(s)[1], 99) <= 3]
    add(max(upsets, key=lambda s: (rank.get(who(s)[0], 0), s), default=None), "upset")
    items = []
    for stem, label in picks[:5]:
        m = metas[stem]
        frames = len(json.loads((out / "replays" / f"{stem}.json").read_text())["frames"])
        a, d = who(stem)
        items.append(dict(data=f"data/{slugify(stem)}.json.gz", a=display(a), d=display(d),
                          ar=rank.get(a, 0), dr=rank.get(d, 0), frames=frames, label=label,
                          page=f"{slugify(stem)}.html"))
    return dict(epoch=f"{rec.get('date', '2026-01-01')}T03:30:00Z", night=night, items=items)


# --- build ----------------------------------------------------------------------

def build(site: Path = SITE, out: Path = DEFAULT_OUT, library: Path = None,
          seasons: Path = ROOT / "seasons", research: Path = ROOT / "research") -> dict:
    from . import replay_pack, season
    library = library or out / "library"
    lb = json.loads((out / "leaderboard.json").read_text())
    matrix = json.loads((out / "matrix.json").read_text())["matrix"]
    if site.exists():
        shutil.rmtree(site)
    (site / "bots").mkdir(parents=True)
    (site / "replays" / "data").mkdir(parents=True)
    shutil.copy2(ASSETS / "style.css", site / "style.css")
    shutil.copy2(ASSETS / "site.js", site / "site.js")
    (site / "fonts").mkdir()
    for f in sorted(FONTS.glob("*")):
        shutil.copy2(f, site / "fonts" / f.name)
    (site / "CNAME").write_text(DOMAIN)

    replays = sorted((out / "replays").glob("*__*__s*.json"))
    live = {r["name"] for role in ("attackers", "defenders") for r in lb[role]}
    current = [p for p in replays if p.stem.split("__")[0] in live
               and p.stem.split("__")[1] in live]
    hist = history(out)
    recs = ledger(out)
    rec = recs[-1] if recs else {}
    before = hist[-2][1] if len(hist) > 1 else None
    moves = {role: movement(lb[role], before[role]) if before else
             {r["name"]: 0 for r in lb[role]} for role in ("attackers", "defenders")}
    firsts = first_nights(hist)
    night = nights_run(recs, hist)

    # replays: every one as packed data (replays/data/<stem>.json.gz), one shared viewer
    # that opens them on demand, and a full page only for the matches the rule picks
    spec = importlib.util.spec_from_file_location("build_viewer",
                                                  ROOT / "viewer" / "build_viewer.py")
    viewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viewer)
    (site / "replays" / "viewer.html").write_text(viewer.page_with(None))
    metas = {}
    for p in current:
        rep = json.loads(p.read_text())
        rep["meta"]["rules"] = {}
        metas[p.stem] = rep["meta"]
        (site / "replays" / "data" / f"{slugify(p.stem)}.json.gz").write_bytes(
            replay_pack.pack(rep))
    first = season.FIRST_NIGHT.isoformat()
    as_of = max([n for n, _ in hist] + [match_night(s, first) for s in metas] + [first])
    full = full_page_stems(metas, as_of, first)
    if metas and lb["attackers"] and lb["defenders"]:
        ch = channel(metas, lb, rec, out, night)
    else:
        ch = dict(epoch="2026-01-01T03:30:00Z", night=night, items=[])
    (site / "replays" / "channel.json").write_text(json.dumps(ch, indent=1) + "\n")
    CHROME.clear()
    CHROME.update(night=night, date=rec.get("date", ""),
                  who=f"{ch['items'][0]['a']} v {ch['items'][0]['d']}" if ch["items"] else "")
    rank = {r["name"]: i for role in ("attackers", "defenders")
            for i, r in enumerate(lb[role], 1)}
    for stem in sorted(full):
        write_replay_page(site, stem, metas[stem], rank)

    papers = write_research(site, research)
    write_ladders(site, lb, moves, firsts, out, night)
    write_home(site, lb, moves, firsts, rec, recs, hist, papers, ch, live, season)
    for role in ("attackers", "defenders"):
        for r in lb[role]:
            write_bot_page(site, r, role, matrix, metas, full, rank, firsts)
    write_replays_index(site, current, metas, full)
    write_changelog(site, recs, hist)
    write_submit(site)
    (site / "about.html").write_text(page("About", '<div class="read">' + md_to_html(
        (ROOT / "ABOUT.md").read_text(),
        link_map={"SUBMITTING.md": "submitting.html", "SEASON.md": "seasons.html"})
        + "</div>", current="about"))
    cards = write_library(site, library)
    archived = write_seasons(site, seasons)
    return dict(site=str(site), bots=len(live), replays=len(current), full_pages=len(full),
                cards=cards, seasons=archived, research=len(papers))


def write_home(site, lb, moves, firsts, rec, recs, hist, papers, ch, live, season):
    night = nights_run(recs, hist)
    first_item = ch["items"][0] if ch["items"] else None
    if first_item:
        frame = ('<iframe class="viewer" src="replays/viewer.html?mode=broadcast&amp;'
                 'channel=channel.json" title="Replay channel: last night\'s featured '
                 'matches"></iframe>')
        has_page = (site / "replays" / first_item["page"]).exists()
        line = ('<p class="stage-line t3">Replays of last night\'s matches, not a live feed: '
                'every match was played in the sandbox at 03:30 UTC.'
                + (f' <a href="replays/{e(first_item["page"])}">Watch with controls →</a>'
                   if has_page else "") + "</p>")
    else:
        frame = ('<div class="stage"><div class="field"></div><div class="stage-load"><span>'
                 'No replays yet</span></div></div>')
        line = ""
    body = ['<h1 class="wrap" style="position:absolute;left:-9999px">Swarm Colosseum: '
            'the arena</h1>',
            f'<section class="broadcast" id="broadcast" aria-label="Replay channel">'
            f'<div class="frame">{frame}</div>{line}</section>', '<div class="wrap">']
    submitted = sum(1 for d in ("attacker", "defender")
                    for _ in (ROOT / "bots" / "submitted" / d).glob("*.py"))
    day = (date.fromisoformat(hist[-1][0]) - season.FIRST_NIGHT).days + 1 if hist else 0
    day = max(0, min(day, season.LENGTH_NIGHTS))
    nums = [("ladders.html", f"{lb.get('matches', 0):,}", "matches on last night's ladder"),
            ("ladders.html", f"{len(live)}", "bots in the arena"),
            ("changelog.html", f"{night}", "nights run"),
            ("research.html", f"{beat_their_target(recs)}",
             "house bots that beat the bot they were written to beat"),
            ("submitting.html", f"{submitted}", "outside submissions · not open yet"),
            ("seasons.html", f"{day}", f"{season.NAME.lower()} · day of {season.LENGTH_NIGHTS}")]
    body.append('<p class="t2" style="margin:var(--s4) 0 0;max-width:var(--readw)">An open '
                'arena where AI-written attackers and AI-written defenders play an abstract '
                'strategy game every night, and every match can be replayed and reproduced. '
                'Everything in the game is made up: the units, the distances, the rules. '
                '<a href="about.html">What this is →</a></p>')
    body.append('<nav class="nums" aria-label="Arena figures">' + "".join(
        f'<a href="{h}"><span class="v">{v}</span><span class="k">{e(k)}</span></a>'
        for h, v, k in nums) + "</nav>")
    body.append('<section class="section" style="margin-top:var(--s5)"><div class="section-head">'
                f'<h2>Ladders</h2><span class="label">after night {night}</span></div>'
                '<div class="grid2">' + "".join(
                    ladder_panel(role, lb[role][:8], moves[role], firsts)
                    for role in ("attackers", "defenders")) + "</div></section>")
    body.append('<section class="section"><div class="section-head"><h2>Last night’s recap</h2>'
                f'<span class="label mono">{e(rec.get("date", ""))}</span></div>'
                f'<div class="recap"><p>{recap(rec, hist, night)}</p></div></section>')
    if papers:
        cards = "".join(
            f'<a class="result" href="{e(p["href"])}"><span class="label">R-{e(p["n"])} · '
            f'{e(p["status"])}</span><p>{e(p["title"])}</p><span class="go">read →</span></a>'
            for p in sorted(papers, key=lambda x: x["n"], reverse=True)[:3])
        body.append('<section class="section"><div class="section-head"><h2>Results so far</h2>'
                    '<a class="mono t2" href="research.html">all research →</a></div>'
                    f'<div class="cards3">{cards}</div></section>')
    body.append('<section class="section"><div class="doors">'
                '<a href="submitting.html"><b>Play</b> <span>— write a bot and get it '
                'ready</span></a>'
                '<a href="research.html"><b>Study</b> <span>— research and the tactic '
                'library</span></a>'
                '<a href="submitting.html#build"><b>Build with us</b> <span>— contribute to '
                'the arena</span></a></div></section>')
    pct = 100 * min(day, season.LENGTH_NIGHTS) / season.LENGTH_NIGHTS
    nxt = f"{season.ENDS.day} {season.ENDS.strftime('%b')}"
    body.append(f'<section class="section"><p class="season" style="margin:0">{e(season.NAME)} · '
                f'day <b>{day}</b> of {season.LENGTH_NIGHTS} · the next season begins '
                f'<b>{nxt}</b></p><div class="bar" role="progressbar" aria-valuenow="{day}" '
                f'aria-valuemin="0" aria-valuemax="{season.LENGTH_NIGHTS}" aria-label="Season '
                f'progress"><i style="width:{pct:.1f}%"></i></div></section></div>')
    (site / "index.html").write_text(page("The arena", "\n".join(body), current="home"))


def write_ladders(site, lb, moves, firsts, out, night):
    reports = sorted((out / "meta").glob("WEEK_*.md"),
                     key=lambda p: int(re.search(r"\d+", p.stem).group()))
    body = ['<div class="wrap">', page_head(
        "Ladders", "Elo per side, rebuilt from 1000 every night from that night's full round "
        "robin: every bot plays every bot on the other side on the same ten seeds. Δ night is "
        "the change in place since the night before. <a href=\"about.html\">How to read "
        "this →</a>"),
        '<nav class="toggle" aria-label="Side"><a href="#attackers"><span class="side-tag '
        'att">Attackers</span></a><a href="#defenders"><span class="side-tag def">Defenders'
        '</span></a></nav>',
        '<div class="stack">' + "".join(
            ladder_panel(role, lb[role], moves[role], firsts, full=True, link=False)
            for role in ("attackers", "defenders")) + "</div>",
        '<section class="section" style="margin-top:var(--s5)"><div class="section-head">'
        f'<h2>Latest meta report</h2><span class="label">after night {night}</span></div>']
    if reports:
        body.append('<div class="read wide-read" style="padding:0;margin:0">'
                    f'{md_to_html(public_report(reports[-1].read_text()))}</div>')
    else:
        body.append('<div class="panel"><p class="empty">No weekly report yet: the first is '
                    'written after the seventh night.</p></div>')
    body.append("</section></div>")
    (site / "ladders.html").write_text(page("Ladders", "\n".join(body), current="ladders"))


def write_replay_page(site: Path, stem: str, m: dict, rank: dict):
    """A full replay page: the site's chrome, the match's facts, and the viewer (framed,
    sized to fit by site.js), which loads the packed replay next to it."""
    slug = slugify(stem)
    a, d = stem.split("__")[:2]
    src = f"viewer.html?r=data/{slug}.json.gz&amp;ar={rank.get(a, 0)}&amp;dr={rank.get(d, 0)}"
    body = (f'<div class="wrap replay-head"><span class="label">Replay · seed {m["seed"]}</span>'
            f'<h1><span class="att">{e(display(a))}</span> <span class="t3">v</span> '
            f'<span class="def">{e(display(d))}</span></h1>'
            f'<div class="meta"><span>{e(m["outcome"])}</span><span>{m["ticks"]} ticks</span>'
            f'<span>attacker {m["score_attacker"]:.3f} · defender {m["score_defender"]:.3f}'
            f'</span><a href="../bots/{e(slugify(a))}.html">{e(display(a))}</a>'
            f'<a href="../bots/{e(slugify(d))}.html">{e(display(d))}</a>'
            f'<a href="data/{e(slug)}.json.gz">data</a></div></div>'
            f'<iframe class="viewer fit" src="{src}" title="Replay viewer"></iframe>'
            f'<p class="wrap mono t3" style="margin-top:var(--s2)"><a href="{src}">Open the '
            f'viewer on its own →</a></p>')
    (site / "replays" / f"{slug}.html").write_text(
        page(f"{display(a)} v {display(d)}", body, 1, current="replays"))


def write_replays_index(site, current, metas, full):
    items = []
    for p in current:
        m = metas[p.stem]
        kind = "page" if p.stem in full else "viewer"
        a, d = p.stem.split("__")[:2]
        items.append(f'<li><a href="{e(replay_href(p.stem, full))}"><span class="att">'
                     f'{e(display(a))}</span> v <span class="def">'
                     f'{e(display(d))}</span></a><span class="t3">seed {m["seed"]} · '
                     f'{e(m["outcome"])} · {m["ticks"]} ticks · {kind} · <a href="replays/data/'
                     f'{e(slugify(p.stem))}.json.gz">data</a></span></li>')
    body = ('<div class="wrap">' + page_head(
        "Replays", f"{len(current):,} matches from last night's round robin. The "
        f"{len(full):,} first played this week or last, and each bot's best and worst, have "
        "their own page; the rest open in the same viewer, which loads the match when you ask "
        "for it. <b>data</b> is the replay itself (gzipped JSON; <code>python -m "
        "colosseum.replay_pack unpack</code> turns it back into the full replay).")
        + f'<ul class="picks">{"".join(items)}</ul></div>')
    (site / "replays.html").write_text(page("Replays", body, current="replays"))


def write_research(site: Path, research: Path) -> list:
    """research.html and research/<n>.html from research/*.md. Links between the write-ups
    are kept; any other link is dropped (its label stays). Returns their info dicts."""
    docs = sorted(research.glob("*.md")) if research.is_dir() else []
    names = {p.name for p in docs}
    papers = []
    if docs:
        (site / "research").mkdir()
    for p in docs:
        info = paper_info(p)
        info["href"] = f"research/{slugify(p.stem)}.html"
        body = (f'<article class="read"><span class="label">R-{e(info["n"])} · '
                f'<span class="tag {info["status"]}">{e(info["status"])}</span>'
                + (f' · {e(info["when"])}' if info["when"] else "") + "</span>"
                + md_to_html(p.read_text(), lambda t: f"{slugify(t[:-3])}.html"
                             if t in names else None) + "</article>")
        (site / info["href"]).write_text(page(info["title"], body, 1, current="research"))
        papers.append(info)
    body = ['<div class="wrap">', page_head(
        "Research", "Numbered notes from the arena. Every number in them comes from the "
        "league's own records and can be rebuilt with <code>make reproduce</code>. "
        "Preliminary notes change as the nights add up.")]
    if papers:
        body.append('<ul class="list">')
        for info in sorted(papers, key=lambda x: x["n"], reverse=True):
            body.append(f'<li><a href="{e(info["href"])}"><span class="n">{e(info["n"])}</span>'
                        f'<span><span class="ttl">{e(info["title"])}</span> <span class="tag '
                        f'{info["status"]}">{e(info["status"])}</span><span class="sum">'
                        f'{e(info["summary"])}</span>'
                        + (f'<span class="when">{e(info["when"])}</span>' if info["when"] else "")
                        + "</span></a></li>")
        body.append("</ul>")
    else:
        body.append('<div class="panel"><p class="empty">Nothing written up yet.</p></div>')
    body.append('<section class="section" id="library" style="margin-top:var(--s5)">'
                '<div class="doors"><a href="library/index.html"><b>Tactic library</b> <span>— '
                'the ideas that worked, one card each</span></a><a href="seasons.html"><b>'
                'Seasons</b> <span>— the season so far and the archive</span></a><a href='
                '"changelog.html"><b>Changelog</b> <span>— every night, newest first</span></a>'
                '</div></section></div>')
    (site / "research.html").write_text(page("Research", "\n".join(body), current="research"))
    return papers


AUTOMATED = ("Night ", "Season report", "Build session", "DAILY.md", "Merge ", "test:")


def write_changelog(site, recs, hist):
    """One entry per night, newest first, from the ledger; plus the day's code and rules
    commits (the automated night, report and build-session ones left out)."""
    import subprocess
    # Number nights from the ledger by nights_run's rule, not by snapshot: the backfilled
    # 2026-09-28 night is in the ledger but left no snapshot.
    last = hist[-1][0] if hist else None
    ok = sorted({r["date"] for r in recs if r.get("status") == "ok"
                 and (last is None or r.get("date", "") <= last)})
    numbers = {night: n for n, night in enumerate(ok, 1)}
    body = ['<div class="wrap">', page_head(
        "Changelog", "One entry per night, newest first: what the league wrote, what happened "
        "on the ladders, and what changed in the code that day.")]
    if not recs:
        body.append('<div class="panel"><p class="empty">No night has run yet.</p></div>')
    for rec in reversed(recs):
        date = rec["date"]
        lines = []
        cache = rec.get("cache") or {}
        if cache:
            lines.append(f"{cache['matches']:,} matches on the ladder, {cache['ran']:,} played "
                         "for the first time.")
        if rec.get("status") != "ok":
            lines.append("The night didn't complete: "
                         f"{e(str(rec.get('reason') or rec.get('status')))}.")
        for name, pos in sorted((rec.get("house_positions") or {}).items()):
            lines.append(f"Wrote <span class=mono>{e(display(name))}</span> ({e(pos['role'])}, "
                         f"{e(str(pos.get('persona', '')).replace('_', '-'))}): aimed at "
                         f"<span class=mono>{e(target_name(pos.get('target')))}"
                         f"</span>, {'beat it' if pos.get('beat_target') else 'did not beat it'}"
                         + (f", entered at #{pos['rank']}." if pos.get('rank') else "."))
        if rec.get("rejected"):
            lines.append(f"{len(rec['rejected'])} generated bot(s) rejected before the ladder.")
        for name in rec.get("retired") or []:
            lines.append(f"Retired <span class=mono>{e(display(name))}</span>.")
        if rec.get("top_attacker"):
            lines.append(f"Top attacker <span class=mono>{e(display(rec['top_attacker']))}"
                         f"</span>, top defender <span class=mono>"
                         f"{e(display(rec['top_defender']))}</span>.")
        try:
            log = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%s",
                                  f"--since={date}T00:00:00Z", f"--until={date}T23:59:59Z"],
                                 capture_output=True, text=True, timeout=10).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            log = []
        code = "".join(f"<li>{e(s)}</li>" for s in
                       [s for s in log if not s.startswith(AUTOMATED)][:4])
        n = numbers.get(date)
        body.append(f'<section class="night"><h2>{e(date)}' + (f" · night {n}" if n else "")
                    + f'</h2><p>{" ".join(lines)}</p>' + (f"<ul>{code}</ul>" if code else "")
                    + "</section>")
    body.append("</div>")
    (site / "changelog.html").write_text(page("Changelog", "\n".join(body), current="changelog"))


def write_submit(site):
    sub = md_to_html((ROOT / "SUBMITTING.md").read_text(), link_map={"SEASON.md": "seasons.html"})
    contrib = ROOT / "CONTRIBUTING.md"
    build = (md_to_html(re.sub(r"^#\s+.*\n", "", contrib.read_text(), count=1), lambda t: None)
             if contrib.exists() else "")
    body = f'<div class="read">{sub}<h2 id="build">Build with us</h2>{build}</div>'
    (site / "submitting.html").write_text(page("Submit a bot", body, current="submit"))


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
            '<div class="read"><h1>Tactic library</h1><p class=t2>Not built yet. It appears '
            'after the next night, once <code>python -m colosseum.library</code> has run.</p>'
            "</div>"), 1, current="library"))
        return 0

    def card_link(target):
        m = re.search(r"(?:^|/)replays/([^/]+)\.json$", target)
        if not m:
            return None
        stem = slugify(unquote(m.group(1)))
        if (site / "replays" / f"{stem}.html").exists():
            return f"../../replays/{stem}.html"
        if (site / "replays" / "data" / f"{stem}.json.gz").exists():
            return f"../../replays/viewer.html?r=data/{stem}.json.gz"
        return "../../replays.html"

    pages = {}
    for entry in entries:
        stem = slugify(Path(entry["card"]).stem)
        md = library / "cards" / f"{stem}.md"
        if not md.exists():
            continue
        pages[entry["card"]] = f"cards/{stem}.html"
        body = ['<div class="read">']
        if (site / "bots" / f"{slugify(entry['name'])}.html").exists():
            body.append(f"<p class=t2><a href=\"../../bots/{slugify(entry['name'])}.html\">"
                        "On the ladder now →</a></p>")
        body.append(md_to_html(md.read_text(), card_link) + "</div>")
        (dest / "cards" / f"{stem}.html").write_text(
            page(display(entry["name"]), "\n".join(body), 2, current="library"))
    (dest / "index.html").write_text(page("Tactic library", '<div class="read">' + md_to_html(
        index.read_text(), pages.get) + "</div>", 1, current="library"))
    return len(pages)


def write_seasons(site: Path, seasons: Path) -> int:
    """seasons.html: SEASON.md, then every archived season's markdown as pages, links
    between them kept and any other link dropped. Returns the number of archived seasons."""
    body = ['<div class="read">', md_to_html((ROOT / "SEASON.md").read_text(), lambda t: None),
            "<h2>Archive</h2>"]
    seasons = seasons.resolve()
    archived = sorted(d for d in seasons.glob("*") if d.is_dir()) if seasons.is_dir() else []
    if not archived:
        body.append("<p class=t2>No season has finished yet. When one ends, its ladders, "
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
            target.write_text(page(f"{d.name}: {p.stem}", '<div class="read">'
                                   + md_to_html(p.read_text(), link) + "</div>", depth,
                                   current="seasons"))
            items.append(f"<li><a href=\"{e(target.relative_to(site).as_posix())}\">"
                         f"{e(p.relative_to(d).as_posix())}</a></li>")
        body.append(f"<h3>{e(d.name)}</h3><ul class=picks>{''.join(items)}</ul>")
    body.append("</div>")
    (site / "seasons.html").write_text(page("Seasons", "\n".join(body), current="seasons"))
    return len(archived)


def h2h(name, me, metas):
    """{opponent: (wins, losses)} over its current matches; a win is a breach for an
    attacker and a hold for a defender. Bots are known by file name (the replay's stem)."""
    out = {}
    k = 0 if me == "attacker" else 1
    for s, m in metas.items():
        if s.split("__")[k] != name:
            continue
        opp = s.split("__")[1 - k]
        won = (m["outcome"] == "breached") == (me == "attacker")
        w, l = out.get(opp, (0, 0))
        out[opp] = (w + won, l + (not won))
    return out


def write_bot_page(site, row, role, matrix, metas, full, rank, firsts):
    name = row["name"]
    path = bot_file(name)
    meta = read_meta(path)
    doc = docstring(path) if path else ""
    me = "attacker" if role == "attackers" else "defender"
    side, other = ("att", "def") if me == "attacker" else ("def", "att")
    n, night = firsts.get(name, (0, ""))
    body = ['<div class="wrap">',
            f'<header class="bot-head {side}"><span class="side-tag {side}">{me.capitalize()}'
            f'</span><h1>{e(display(name))}</h1><div class="meta"><span>rank <b class="{side}">'
            f'#{rank.get(name, 0)}</b></span><span>Elo {row["elo"]:.0f}</span>'
            f'<span class="t3">{e(origin(path, meta))}</span>'
            f'<span class="t3">{e(name)}</span></div></header>']
    body.append(f'<div class="read" style="padding:0;margin:0">{md_to_html(doc)}</div>' if doc
                else '<p class="t2">No docstring.</p>')
    body.append(f'<div class="stats4"><div><span class="v">{row["win_rate"]:.1%}</span>'
                f'<span class="label">win rate</span></div><div><span class="v">'
                f'{row["mean_cer"]:.2f}</span><span class="label">cost exchange</span></div>'
                f'<div><span class="v">{row["matches"]:,}</span><span class="label">matches'
                f'</span></div><div><span class="v">night {n}</span><span class="label">first '
                f'night ({e(night)})</span></div></div>')
    rec = h2h(name, me, metas)
    beats = sorted(((o, w, l) for o, (w, l) in rec.items() if w > l),
                   key=lambda x: (x[2] - x[1], x[0]))
    loses = sorted(((o, w, l) for o, (w, l) in rec.items() if w <= l),
                   key=lambda x: (x[1] - x[2], x[0]))

    def lst(rows):
        if not rows:
            return '<p class="empty">Nobody.</p>'
        return '<ul class="h2h">' + "".join(
            f'<li><a href="{e(slugify(o))}.html" class="{other}">{e(display(o))}</a>'
            f'<span>{w}–{l}</span></li>' for o, w, l in rows[:6]) + "</ul>"
    body.append('<section class="section" style="margin-top:var(--s5)"><div class="grid2">'
                '<div class="panel"><div class="panel-head"><h2>Beats</h2><span class="label">'
                f'wins–losses, last night</span></div>{lst(beats)}</div>'
                '<div class="panel"><div class="panel-head"><h2>Loses to</h2><span class="label">'
                f'wins–losses, last night</span></div>{lst(loses)}</div></div></section>')
    k = 0 if me == "attacker" else 1
    mine = {s: m for s, m in metas.items() if s.split("__")[k] == name}
    opp_of = lambda s: s.split("__")[1 - k]
    if mine:
        key = lambda s: (mine[s][f"score_{me}"], s)
        figs = []
        for label, s in (("Best match", max(mine, key=key)), ("Worst match", min(mine, key=key))):
            m, opp = mine[s], opp_of(s)
            a, d = s.split("__")[:2]
            src = (f"../replays/viewer.html?mode=embed&amp;r=data/{slugify(s)}.json.gz&amp;"
                   f"ar={rank.get(a, 0)}&amp;dr={rank.get(d, 0)}")
            figs.append(f'<figure><span class="label">{label}</span><iframe class="viewer embed fit" '
                        f'src="{src}" title="{label}: {e(display(name))} v {e(display(opp))}" '
                        f'loading="lazy"></iframe><figcaption>vs <span class="{other}">'
                        f'{e(display(opp))}</span> · its score {m[f"score_{me}"]:.3f} · seed '
                        f'{m["seed"]} · <a href="{e(replay_href(s, full, "../"))}">open →</a>'
                        f'</figcaption></figure>')
        body.append(f'<section class="section"><div class="grid2">{"".join(figs)}</div></section>')
    if me == "attacker":
        per = {d: 1 - s for d, s in matrix.get(name, {}).items()}
    else:
        per = {a: r[name] for a, r in matrix.items() if name in r}
    body.append('<section class="section"><div class="grid2"><div class="panel"><div '
                'class="panel-head"><h2>Against each opponent</h2><span class="label">its mean '
                'score</span></div><div class="tbl-wrap"><table><tbody>' + "".join(
                    f'<tr><td class="name"><a href="{e(slugify(o))}.html">{e(display(o))}</a>'
                    f'</td><td class="num">{s:.3f}</td></tr>'
                    for o, s in sorted(per.items(), key=lambda kv: -kv[1]))
                + "</tbody></table></div></div>")
    rows = []
    for s in sorted(mine, key=lambda s: (-mine[s]["seed"], s))[:10]:
        m, opp = mine[s], opp_of(s)
        won = (m["outcome"] == "breached") == (me == "attacker")
        rows.append(f'<tr><td class="name">{e(display(opp))}</td><td class="num">{m["seed"]}</td>'
                    f'<td class="{"good" if won else "bad"}">{e(m["outcome"])}</td>'
                    f'<td class="num">{m[f"score_{me}"]:.3f}</td><td><a href="'
                    f'{e(replay_href(s, full, "../"))}">watch</a></td></tr>')
    body.append('<div class="panel"><div class="panel-head"><h2>Matches</h2><span class="label">'
                'last night</span></div><div class="tbl-wrap"><table><thead><tr><th>Opponent'
                '</th><th class="num">Seed</th><th>Result</th><th class="num">Score</th><th></th>'
                f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div></div></section>')
    if meta:
        cells = []
        for k in sorted(meta):
            v = meta[k]
            if isinstance(v, dict):
                v = ", ".join(f"{a}: {b}" for a, b in v.items())
            elif isinstance(v, list):
                v = ", ".join(map(str, v))
            cells.append(f"<tr><th>{e(str(k))}</th><td style=\"white-space:normal\">"
                         f"{e(str(v))}</td></tr>")
        body.append('<details class="src" style="margin-bottom:var(--s3)"><summary>Record · '
                    f'{e(path.stem if path else name)}.meta.json</summary><div class="tbl-wrap">'
                    f'<table><tbody>{"".join(cells)}</tbody></table></div></details>')
    if path:
        body.append(f'<details class="src"><summary>Source · '
                    f'{e(path.relative_to(ROOT).as_posix())}</summary><pre><code>'
                    f'{e(path.read_text())}</code></pre></details>')
    body.append("</div>")
    (site / "bots" / f"{slugify(name)}.html").write_text(
        page(display(name), "\n".join(body), 1, current="ladders"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=SITE)
    args = ap.parse_args()
    info = build(args.out)
    size = bundle_bytes(info["site"])
    print(f"{info['site']}: {info['bots']} bots, {info['replays']} replays "
          f"({info['full_pages']} with full pages), "
          f"{info['cards']} tactic cards, {info['research']} research pages, "
          f"{info['seasons']} archived seasons, "
          f"{size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
