"""Weekly meta report: what happened in the league this week, readable on a phone.

    python -m colosseum.meta_report --week 1          # write out/meta/WEEK_1.md + reports/
    python -m colosseum.meta_report --if-due --commit # what cron runs after each night
    python -m colosseum.meta_report --season          # out/meta/SEASON_1.md + reports/

A "night" is a date with at least one real run in out/nights.jsonl (dry runs are never
recorded there). Week n is real nights 7(n-1)+1 .. 7n, so a failed night still counts as
a night and a date with no run at all does not. --if-due writes week n only on the night the
7n-th real night finishes, and only if WEEK_n.md does not exist yet.

Sources, all written by the league itself: out/nights.jsonl (one line per run),
out/history/<date>/ (ladder, matrix, breaches after that night), the bots' .meta.json
sidecars, and root BALANCE.md. House bots are read as text (ast), never imported.

--commit commits reports/WEEK_n.md and nothing else (a pathspec commit), under a separate
author, so it cannot sweep in anything else in the working tree.
"""
import argparse
import ast
import json
import re
import shutil
import statistics as st
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from . import library, season
from .personas import PERSONAS
from .tournament import DEFAULT_OUT, ROOT

REPORTS = ROOT / "reports"
BOT_FOLDERS = ("house", "house/RETIRED", "submitted/attacker", "submitted/defender",
               "submitted/attacker/RETIRED", "submitted/defender/RETIRED")


# --- loading ------------------------------------------------------------------

def load_nights(out: Path):
    """[(date, [runs...])] in date order."""
    path = out / "nights.jsonl"
    by_date = defaultdict(list)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                by_date[rec["date"]].append(rec)
    return sorted(by_date.items())


def week_dates(nights, week):
    return [d for d, _ in nights[7 * (week - 1): 7 * week]]


def load_snapshot(out: Path, day: str):
    d = out / "history" / day
    if not (d / "leaderboard.json").exists():
        return None
    snap = dict(leaderboard=json.loads((d / "leaderboard.json").read_text()))
    for name in ("matrix", "breaches"):
        p = d / f"{name}.json"
        snap[name] = json.loads(p.read_text()) if p.exists() else None
    return snap


def load_metas(bots_root: Path):
    """name -> (meta dict, path of the .py, alive?) for every house or submitted bot."""
    found = {}
    for folder in BOT_FOLDERS:
        for meta_path in sorted((bots_root / folder).glob("*.meta.json")):
            name = meta_path.name[:-len(".meta.json")]
            py = meta_path.with_name(name + ".py")
            found[name] = (json.loads(meta_path.read_text()), py,
                           "RETIRED" not in folder and py.exists())
    return found


def docstring_line(py: Path) -> str:
    """One line saying what the bot's idea is, quoted from its docstring.

    Preference: an explicit "Idea: ..." line (the generator prompt asks for one), then a
    paragraph that describes the bot ("This bot ..."), then the first paragraph that is not
    bookkeeping (NAME:, Target:). First sentence only.
    """
    try:
        doc = ast.get_docstring(ast.parse(py.read_text())) or ""
    except (SyntaxError, OSError):
        return ""
    m = re.search(r"^\s*Idea:\s*(.+)$", doc, re.M | re.I)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", doc)]
    paras = [p for p in paras if p and not re.match(r"(NAME|Target)\s*:", p, re.I)]
    if m:
        text = m.group(1).strip()
    else:
        described = [p for p in paras if re.match(r"This (bot|defender|attacker)\b", p)]
        text = (described or paras or [""])[0]
    first = re.split(r"(?<=[.!?:])\s", text, maxsplit=1)[0].rstrip(":")
    return first if len(first) <= 220 else first[:217] + "..."


def short(name: str) -> str:
    """'2026-09-28_attacker_staggered_screen_trickle' -> 'staggered_screen_trickle (h)'."""
    m = re.match(r"\d{4}-\d{2}-\d{2}_(attacker|defender)_(.+)", name)
    if m:
        return m.group(2) + " (h)"
    if "__" in name:                                  # submitted: <handle>__<name>
        return name.split("__", 1)[1] + " (s)"
    return name


# --- sections -----------------------------------------------------------------

def ladder_section(start, end, start_label):
    lines = ["## Ladders", ""]
    if not end:
        return lines + ["No ladder snapshot for this week.", ""]
    s_lb = start["leaderboard"] if start else None
    e_lb = end["leaderboard"]
    lines += ["| # | attacker | Elo (Δ) | defender | Elo (Δ) |", "|---|---|---|---|---|"]

    def cell(role, i):
        rows = e_lb[role]
        if i >= len(rows):
            return "", ""
        r = rows[i]
        before = {x["name"]: x["elo"] for x in s_lb[role]} if s_lb else {}
        delta = r["elo"] - before[r["name"]] if r["name"] in before else None
        d = "new" if delta is None else f"{delta:+.0f}"
        return short(r["name"]), f"{r['elo']:.0f} ({d})"

    for i in range(5):
        a, ae = cell("attackers", i)
        d, de = cell("defenders", i)
        lines.append(f"| {i + 1} | {a} | {ae} | {d} | {de} |")
    lines += ["", "(h) house bot, (s) outside submission. Δ is Elo change " + start_label + ".",
              ""]

    for role in ("attackers", "defenders"):
        now = [r["name"] for r in e_lb[role][:5]]
        was = [r["name"] for r in s_lb[role][:5]] if s_lb else []
        entered = [short(n) for n in now if n not in was]
        left = [short(n) for n in was if n not in now]
        bits = []
        if entered and s_lb:
            bits.append("entered the top five: " + ", ".join(entered))
        if left:
            bits.append("left it: " + ", ".join(left))
        if bits:
            lines.append(f"{role.capitalize()}: " + "; ".join(bits) + ".")
    if lines[-1] != "":
        lines.append("")
    return lines


def ranks_in(snapshots, name):
    out = []
    for snap in snapshots:
        for role in ("attackers", "defenders"):
            for i, r in enumerate(snap["leaderboard"][role], 1):
                if r["name"] == name:
                    out.append((i, role[:-1]))
    return out


def persona_section(metas, dates, snapshots):
    lines = ["## Which personas produced winners", ""]
    week = {n: m for n, m in metas.items() if m[0].get("date") in dates}
    if not week:
        return lines + ["No house bots were written this week.", ""]
    for persona in PERSONAS:
        mine = {n: m for n, m in week.items() if m[0].get("persona") == persona}
        if not mine:
            lines.append(f"- **{persona}**: no bots this week.")
            continue
        beat = sum(1 for m, _, _ in mine.values() if (m.get("result") or {}).get("beat_target"))
        alive = sum(1 for _, _, a in mine.values() if a)
        best = None
        for n in mine:
            for rank, role in ranks_in(snapshots, n):
                if best is None or rank < best[0]:
                    best = (rank, role)
        best_s = f"best finish #{best[0]} {best[1]}" if best else "no finish recorded"
        lines.append(f"- **{persona}**: {len(mine)} written, {beat} beat their target, "
                     f"{alive} still alive, {best_s}.")
    legacy = [n for n, m in week.items() if m[0].get("persona") not in PERSONAS]
    if legacy:
        lines.append(f"- Other: {len(legacy)} bot(s) with no recognised persona.")
    return lines + [""]


def pick_best_idea(metas, dates, end):
    """The week's new bot that stands highest by Elo on the last night: (name, row, role)."""
    week = {n: m for n, m in metas.items() if m[0].get("date") in dates}
    if not week or not end:
        return None
    elo = {r["name"]: (r, role) for role in ("attackers", "defenders")
           for r in end["leaderboard"][role]}
    scored = [(elo[n][0]["elo"], n) for n in week if n in elo]
    if not scored:
        return None
    _, name = max(scored)
    return name, elo[name][0], elo[name][1]


def best_idea_section(metas, dates, end, clip_note=None):
    lines = ["## Best new idea", ""]
    best = pick_best_idea(metas, dates, end)
    if not best:
        return lines + ["None this week.", ""]
    name, row, role = best
    rank = [r["name"] for r in end["leaderboard"][role]].index(name) + 1
    meta, py, _ = metas[name]
    line = docstring_line(py) or "(no docstring)"
    result = meta.get("result") or {}
    beat = {True: "beat its target", False: "did not beat its target"}.get(
        result.get("beat_target"), "target not judged")
    lines += [f"**{short(name)}** ({meta.get('persona', '?')}, {role[:-1]}): “{line}”", "",
              f"Result: #{rank} {role[:-1]}, Elo {row['elo']:.0f}, wins "
              f"{row['win_rate']:.0%} of its matches, {beat}.", ""]
    if clip_note:
        lines += [clip_note, ""]
    return lines


def best_match_replay(out: Path, name: str, role: str, target: str = None):
    """Replay of the bot's strongest match: against its target if that pairing exists,
    otherwise against anyone. Strongest = best score from the bot's side."""
    pattern = f"{name}__*__s*.json" if role == "attacker" else f"*__{name}__s*.json"
    best = None
    for p in (out / "replays").glob(pattern):
        a, d, _ = p.stem.split("__")
        opponent = d if role == "attacker" else a
        meta = json.loads(p.read_text())["meta"]
        mine = 1 - meta["score_defender"] if role == "attacker" else meta["score_defender"]
        key = (opponent == target, mine)
        if best is None or key > best[0]:
            best = (key, p, opponent)
    return (best[1], best[2]) if best else (None, None)


def coverage_section(end):
    lines = ["## Coverage", ""]
    if not end or not end.get("breaches"):
        return lines + ["No breach data for the last night of the week.", ""]
    b = end["breaches"]["breaches"]
    seeds = end["breaches"]["seeds"]
    attackers = sorted(b)
    defenders = sorted({d for row in b.values() for d in row})
    flags = []
    lines.append("Who gets through each defender (at least one seed of " + str(seeds) + "):")
    lines.append("")
    for d in defenders:
        by = [short(a) for a in attackers if b[a].get(d, 0) > 0]
        lines.append(f"- {short(d)}: " + (", ".join(by) if by else "**nobody**"))
        if not by:
            flags.append(f"no attacker can breach {short(d)}")
    lines += ["", "Which defenders each attacker never gets through:", ""]
    for a in attackers:
        never = [short(d) for d in defenders if b[a].get(d, 0) == 0]
        lines.append(f"- {short(a)}: " + (", ".join(never) if never else "none"))
        if all(b[a].get(d, 0) == seeds for d in defenders):
            flags.append(f"no defender can stop {short(a)}")
    lines.append("")
    lines.append("**Flags:** " + ("; ".join(flags) + "." if flags else "none."))
    return lines + [""]


FINDING = re.compile(r"^## (S\d+-\d+ — .+?) \((\d{4}-\d{2}-\d{2})\)\s*$", re.M)


def findings_section(balance: Path, dates):
    lines = ["## Rules findings", ""]
    new = []
    if balance.exists():
        new = [title for title, day in FINDING.findall(balance.read_text()) if day in dates]
    if not new:
        return lines + ["Nothing new in BALANCE.md this week.", ""]
    return lines + [f"- {t}" for t in new] + ["", "Details in root BALANCE.md.", ""]


def watch_section(out: Path):
    """The founder's seven-night watches (see ops.WATCHES), if any are running."""
    paths = sorted(out.glob("WATCH*.md"))
    if not paths:
        return []
    lines = ["## Watch", ""]
    for path in paths:
        body = path.read_text().splitlines()
        verdict = [l for l in body if l.startswith("**Verdict") or l.startswith("Undecided")]
        rows = [l for l in body if l.startswith("| 20")]
        lines += [body[0].lstrip("# ") + ".", ""]
        for r in rows:
            cells = [c.strip() for c in r.strip("|").split("|")]
            lines.append(f"- {cells[0]}: it won {cells[1]} of its matches; best opponent "
                         f"{short(cells[2])} at {cells[3]}.")
        lines += [""] + verdict + [""]
    return lines


def phase_means(nights, dates):
    per = defaultdict(list)
    for d, runs in nights:
        if d in dates:
            for r in runs:
                for k, v in (r.get("phases") or {}).items():
                    per[k].append(v)
    return {k: st.mean(v) for k, v in per.items() if v}


def disk_usage(out: Path):
    def size(p):
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    parts = {name: size(out / name) for name in ("replays", "house_raw", "history", "meta")}
    return size(out), parts


def health_section(nights, dates, prev_dates, out: Path, health_text=None):
    lines = ["## Health", ""]
    runs = [r for d, rs in nights if d in dates for r in rs]
    failed = [(d, rs[-1].get("reason") or "unknown") for d, rs in nights
              if d in dates and rs[-1].get("status") != "ok"]
    rejected = [(role, reason) for r in runs for role, reason in (r.get("rejected") or [])]
    retired = [n for r in runs for n in (r.get("retired") or [])]
    tokens_week = sum((r.get("spend") or {}).get("input_tokens", 0)
                      + (r.get("spend") or {}).get("output_tokens", 0) for r in runs)
    tokens_all = sum((r.get("spend") or {}).get("input_tokens", 0)
                     + (r.get("spend") or {}).get("output_tokens", 0)
                     for _, rs in nights for r in rs)
    t_times = [r["tournament_seconds"] for r in runs if r.get("tournament_seconds")]

    lines.append(f"- Nights run: {len(dates)} ({len(runs)} runs in all).")
    lines.append("- Nights failed: " + (", ".join(f"{d} ({why})" for d, why in failed)
                                        if failed else "none") + ".")
    if rejected:
        lines.append(f"- Bots rejected: {len(rejected)} — " +
                     "; ".join(f"{role}: {why}" for role, why in rejected) + ".")
    else:
        lines.append("- Bots rejected: none.")
    lines.append("- Retired: " + (", ".join(short(n) for n in retired) if retired else "none")
                 + ".")
    lines.append(f"- Tokens: {tokens_week:,} this week, {tokens_all:,} this season.")
    cached = [r["cache"] for r in runs if r.get("cache")]
    if cached:
        played = sum(c.get("ran") or 0 for c in cached)
        total = sum(c.get("matches") or 0 for c in cached)
        lines.append(f"- Result cache: {cached[-1].get('cache_entries'):,} entries; this week "
                     f"{total - played:,} of {total:,} matches came from it "
                     f"({(total - played) / total:.0%} hit rate), {played:,} were played.")
    lines.append("- Mean tournament time: " +
                 (f"{st.mean(t_times):.0f} s over {len(t_times)} tournaments." if t_times
                  else "no tournaments this week."))

    now, before = phase_means(nights, dates), phase_means(nights, prev_dates)
    slow = [f"{k} {before[k]:.0f} s → {now[k]:.0f} s" for k in now
            if k in before and before[k] >= 1 and now[k] >= 2 * before[k]]
    lines.append("- Phase times doubled since last week: " +
                 (", ".join(slow) if slow else "none") + ".")
    total, parts = disk_usage(out)
    lines.append(f"- Disk: out/ is {total / 1e6:.0f} MB (" + ", ".join(
        f"{k} {v / 1e6:.0f} MB" for k, v in parts.items()) + ").")
    if health_text:
        lines += ["", "Health check:", ""] + [f"    {l}" for l in health_text.splitlines()]
    return lines + [""]


# --- the report ---------------------------------------------------------------

def build_report(week: int, out: Path = DEFAULT_OUT, bots_root: Path = ROOT / "bots",
                 balance: Path = ROOT / "BALANCE.md", health_text: str = None,
                 clip_note: str = None) -> str:
    nights = load_nights(out)
    dates = week_dates(nights, week)
    prev = week_dates(nights, week - 1) if week > 1 else []
    snaps = [s for s in (load_snapshot(out, d) for d in dates) if s]
    end = snaps[-1] if snaps else None
    start = load_snapshot(out, prev[-1]) if prev else None
    start_label = (f"since {prev[-1]}" if start else
                   f"since the first night of the week ({dates[0]})" if dates else "")
    if not start and snaps:
        start = snaps[0]
    metas = load_metas(bots_root)

    if dates:
        span = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else dates[0]
    else:
        span = "no nights yet"
    partial = "" if len(dates) == 7 else f" Partial week: {len(dates)} of 7 nights so far."
    lines = [f"# Week {week} — {span}", "",
             f"Swarm Colosseum weekly meta report, real nights {7 * (week - 1) + 1}–"
             f"{7 * (week - 1) + len(dates)}.{partial}", ""]
    lines += ladder_section(start, end, start_label)
    lines += persona_section(metas, dates, snaps)
    lines += best_idea_section(metas, dates, end, clip_note)
    lines += coverage_section(end)
    lines += findings_section(balance, dates)
    lines += watch_section(out)
    lines += health_section(nights, dates, prev, out, health_text)
    return "\n".join(lines).rstrip() + "\n"


# --- the season report (item 3.6; a draft until the boundary) ---------------------

def season_nights(nights):
    first, last = season.FIRST_NIGHT.isoformat(), season.LAST_NIGHT.isoformat()
    return [(d, rs) for d, rs in nights if first <= d <= last]


def best_ideas(metas, end, n=5):
    """The season's n best house bots: best rank on their own ladder, then Elo.
    [(name, row, role, rank)]"""
    found = []
    for role in ("attackers", "defenders"):
        for rank, r in enumerate(end["leaderboard"][role], 1):
            if r["name"] in metas:
                found.append((rank, -r["elo"], r["name"], r, role))
    return [(name, r, role, rank) for rank, _, name, r, role in sorted(found)[:n]]


def season_numbers(nights, metas, out: Path):
    runs = [r for _, rs in nights for r in rs]
    dates = [d for d, _ in nights]
    failed = [d for d, rs in nights if rs[-1].get("status") != "ok"]
    mine = {n: m for n, m in metas.items()
            if dates and dates[0] <= m[0].get("date", "") <= dates[-1]}
    by_role = defaultdict(int)
    for m, _, _ in mine.values():
        by_role[m.get("role")] += 1
    alive = sum(1 for _, _, a in mine.values() if a)
    rejected = sum(len(r.get("rejected") or []) for r in runs)
    tokens = sum((r.get("spend") or {}).get("input_tokens", 0)
                 + (r.get("spend") or {}).get("output_tokens", 0) for r in runs)
    matches, tournaments = 0, 0
    for d in dates:
        snap = load_snapshot(out, d)
        if snap and snap.get("breaches"):
            b = snap["breaches"]
            matches += sum(len(row) for row in b["breaches"].values()) * b["seeds"]
            tournaments += 1
    cached = [r["cache"] for r in runs if r.get("cache")]
    lines = ["## The season in numbers", "",
             f"- Nights: {len(dates)} of {season.LENGTH_NIGHTS}"
             + (f", {len(failed)} failed ({', '.join(failed)})." if failed else ", none failed."),
             f"- House bots written: {len(mine)} ({by_role['attacker']} attackers, "
             f"{by_role['defender']} defenders); {alive} still on the ladder, "
             f"{len(mine) - alive} retired. Rejected before the ladder: {rejected}.",
             f"- Matches: {matches:,} in {tournaments} nightly round-robins"
             + (f"; {cached[-1]['cache_entries']:,} distinct results in the cache." if cached
                else "."),
             f"- Tokens: {tokens:,}.", ""]
    return lines


def season_ideas_section(metas, end, clip_notes=None):
    lines = ["## The five best ideas", ""]
    if not end:
        return lines + ["No ladder snapshot yet.", ""]
    ideas = best_ideas(metas, end)
    if not ideas:
        return lines + ["No house bot is on the ladder yet.", ""]
    for i, (name, row, role, rank) in enumerate(ideas, 1):
        meta, py, _ = metas[name]
        idea = library.md_safe(library.idea_of(name, library.read_docstring(py)))  # as the card
        lines.append(f"{i}. **{short(name)}** ({meta.get('persona', '?')}, {role[:-1]}): "
                     f"“{idea or '(no docstring)'}” #{rank} {role[:-1]}, "
                     f"Elo {row['elo']:.0f}, wins {row['win_rate']:.0%}.")
        if clip_notes and clip_notes.get(name):
            lines.append(f"   {clip_notes[name]}")
    return lines + [""]


def season_findings_section(balance: Path, out: Path):
    lines = ["## Rules findings", ""]
    titles = FINDING.findall(balance.read_text()) if balance.exists() else []
    lines += [f"- {t} ({d})" for t, d in titles] or ["- None recorded."]
    names = re.compile(r"\d{4}-\d{2}-\d{2}_(?:attacker|defender)_\w+")
    for path in sorted(out.glob("WATCH*.md")):
        body = path.read_text().splitlines()
        for l in body:
            if l.startswith("**Verdict") or l.startswith("Undecided"):
                line = f"{body[0].lstrip('# ')}: {l.replace('**', '')}"
                lines.append("- " + names.sub(lambda m: short(m.group(0)), line))
    return lines + ["", "Details in BALANCE.md.", ""]


def research_section(research: Path):
    """Ablations and unaided discoveries: the write-ups' own titles, which state the answer."""
    lines = ["## Research this season", ""]
    papers = sorted(research.glob("[0-9]*.md")) if research.exists() else []
    if not papers:
        return lines + ["No write-ups yet.", ""]
    for p in papers:
        title = p.read_text().splitlines()[0].lstrip("# ").strip()
        lines.append(f"- {title} (`research/{p.name}`)")
    return lines + [""]


def season_coverage_section(end):
    lines = ["## Coverage at the end", ""]
    if not end or not end.get("breaches"):
        return lines + ["No breach data.", ""]
    b, seeds = end["breaches"]["breaches"], end["breaches"]["seeds"]
    defenders = sorted({d for row in b.values() for d in row})
    held = [short(d) for d in defenders if not any(b[a].get(d, 0) for a in b)]
    unstoppable = [short(a) for a in sorted(b)
                   if all(b[a].get(d, 0) == seeds for d in defenders)]
    unique = []
    for d in defenders:
        by = [a for a in sorted(b) if b[a].get(d, 0)]
        if len(by) == 1:
            unique.append(f"{short(by[0])} (only one through {short(d)})")
    lines += [f"- {len(b)} attackers × {len(defenders)} defenders, {seeds} seeds a pairing.",
              f"- Defenders nobody gets through: " + (", ".join(held) or "none") + ".",
              f"- Attackers no defender stops: " + (", ".join(unstoppable) or "none") + ".",
              f"- Unique coverage: " + ("; ".join(unique) or "none") + ".", ""]
    return lines


def season_two_section(season_md: Path, out: Path):
    lines = ["## What season two changes", ""]
    text = season_md.read_text() if season_md.exists() else ""
    rows = [[re.sub(r"[*`]", "", c).strip() for c in l.strip().strip("|").split("|")]
            for l in text.splitlines() if l.startswith("| candidate")]
    lines += [f"- {r[0]} (branch {r[1]}), merging on {r[2]}." for r in rows] or \
        ["- No change approved yet."]
    verdicts = [l for p in sorted(out.glob("WATCH*.md")) for l in p.read_text().splitlines()
                if l.startswith("**Verdict")]
    if any("a meta" in v for v in verdicts):
        lines.append("- S0-2 was answered in play (watch verdict: a meta), so no economy fix "
                     "is added (charter section 1).")
    return lines + [""]


def build_season_report(out: Path = DEFAULT_OUT, bots_root: Path = ROOT / "bots",
                        balance: Path = ROOT / "BALANCE.md", season_md: Path = ROOT / "SEASON.md",
                        research: Path = ROOT / "research", clip_notes=None) -> str:
    nights = season_nights(load_nights(out))
    dates = [d for d, _ in nights]
    snaps = [s for s in (load_snapshot(out, d) for d in reversed(dates)) if s]
    end = snaps[0] if snaps else None
    metas = load_metas(bots_root)
    span = f"{dates[0]} to {dates[-1]}" if dates else "no nights yet"
    if len(dates) < season.LENGTH_NIGHTS:
        head = [f"# {season.NAME} — draft, {len(dates)} of {season.LENGTH_NIGHTS} nights "
                f"({span})", "",
                f"The season ends {season.ENDS.isoformat()}; every number below is from the "
                f"nights so far and is rewritten when this report is rerun.", ""]
    else:
        head = [f"# {season.NAME} — {span}", ""]
    lines = head + season_numbers(nights, metas, out)
    if end:
        lb = end["leaderboard"]
        lines += ["## Top of the ladders", "",
                  f"#1 attacker {short(lb['attackers'][0]['name'])} "
                  f"(Elo {lb['attackers'][0]['elo']:.0f}); #1 defender "
                  f"{short(lb['defenders'][0]['name'])} (Elo {lb['defenders'][0]['elo']:.0f}).",
                  ""]
    lines += season_ideas_section(metas, end, clip_notes)
    lines += season_findings_section(balance, out)
    lines += research_section(research)
    lines += season_coverage_section(end)
    lines += season_two_section(season_md, out)
    return "\n".join(lines).rstrip() + "\n"


def write_season(out: Path = DEFAULT_OUT, reports: Path = REPORTS, with_clip=True):
    """out/meta/SEASON_1.md and a copy in reports/; one clip per highlighted idea."""
    (out / "meta").mkdir(parents=True, exist_ok=True)
    notes = {}
    if with_clip:
        dates = [d for d, _ in season_nights(load_nights(out))]
        snaps = [s for s in (load_snapshot(out, d) for d in reversed(dates)) if s]
        metas = load_metas(ROOT / "bots")
        for name, _, role, _ in (best_ideas(metas, snaps[0]) if snaps else []):
            notes[name] = render_best_match(out, name, role[:-1],
                                            metas[name][0].get("target"),
                                            f"SEASON_1_{name}.mp4")
    path = out / "meta" / "SEASON_1.md"
    path.write_text(build_season_report(out, clip_notes=notes))
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, reports / path.name)
    return path


def due_week(out: Path = DEFAULT_OUT):
    n = len(load_nights(out))
    if n and n % 7 == 0 and not (out / "meta" / f"WEEK_{n // 7}.md").exists():
        return n // 7
    return None


def health_output():
    try:
        from . import health
    except ImportError:
        return None
    try:
        return health.report_text()
    except Exception as exc:                     # the report must not die on the check
        return f"health check failed to run: {type(exc).__name__}: {exc}"


def export_clip(week: int, out: Path = DEFAULT_OUT, bots_root: Path = ROOT / "bots"):
    """Render the best new idea's strongest match to out/meta/. Never raises: a failed
    render becomes a line in the report. Videos are not committed (*.mp4 is gitignored)."""
    nights = load_nights(out)
    dates = week_dates(nights, week)
    snaps = [s for s in (load_snapshot(out, d) for d in dates) if s]
    metas = load_metas(bots_root)
    best = pick_best_idea(metas, dates, snaps[-1] if snaps else None)
    if not best:
        return None
    name, _, role = best
    return render_best_match(out, name, role[:-1], metas[name][0].get("target"),
                             f"WEEK_{week}_{name}.mp4")


def render_best_match(out: Path, name: str, role: str, target, dest_name: str):
    """Render a bot's strongest match to out/meta/<dest_name>; returns the report's line."""
    replay, opponent = best_match_replay(out, name, role, target)
    if replay is None:
        return f"Clip: no replay found for {short(name)}."
    dest = out / "meta" / dest_name
    try:
        from . import clip
        info = clip.render(replay, dest, speed=4)
    except Exception as exc:
        return f"Clip: render failed ({type(exc).__name__}: {str(exc)[:120]})."
    clips = out / "meta" / "clips.json"          # rotation keeps these replays for good
    kept = json.loads(clips.read_text()) if clips.exists() else []
    if replay.name not in kept:
        clips.write_text(json.dumps(sorted(kept + [replay.name]), indent=1))
    return (f"Clip: `out/meta/{dest.name}`, its best match against {short(opponent)} "
            f"({replay.stem.rsplit('__', 1)[1]}), {info['bytes'] / 1e6:.2f} MB at 4x.")


def write(week: int, out: Path = DEFAULT_OUT, reports: Path = REPORTS, commit=False,
          with_clip=True):
    (out / "meta").mkdir(parents=True, exist_ok=True)
    note = export_clip(week, out) if with_clip else None
    text = build_report(week, out, health_text=health_output(), clip_note=note)
    path = out / "meta" / f"WEEK_{week}.md"
    path.write_text(text)
    reports.mkdir(parents=True, exist_ok=True)
    copy = reports / path.name
    shutil.copy2(path, copy)
    if commit:
        rel = copy.relative_to(ROOT)
        subprocess.run(["git", "-C", str(ROOT), "add", "--", str(rel)], check=True)
        subprocess.run(["git", "-C", str(ROOT), "-c", "user.name=Swarm Colosseum league",
                        "-c", "user.email=league@localhost", "commit", "-q",
                        "-m", f"Meta report: week {week}", "--", str(rel)], check=True)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--if-due", action="store_true",
                   help="write the report only if this night completed a week")
    g.add_argument("--season", action="store_true",
                   help="write the season report (a draft until the season ends)")
    ap.add_argument("--commit", action="store_true", help="git-commit reports/WEEK_n.md")
    ap.add_argument("--no-clip", action="store_true", help="skip rendering clips")
    args = ap.parse_args()
    if args.season:
        print(f"season report: wrote {write_season(with_clip=not args.no_clip)}")
        return 0
    week = args.week if args.week else due_week()
    if week is None:
        print("meta report: not due")
        return 0
    path = write(week, commit=args.commit)
    print(f"meta report: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
