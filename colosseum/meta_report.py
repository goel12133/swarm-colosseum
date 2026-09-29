"""Weekly meta report: what happened in the league this week, readable on a phone.

    python -m colosseum.meta_report --week 1          # write out/meta/WEEK_1.md + reports/
    python -m colosseum.meta_report --if-due --commit # what cron runs after each night

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


def best_idea_section(metas, dates, end):
    lines = ["## Best new idea", ""]
    week = {n: m for n, m in metas.items() if m[0].get("date") in dates}
    if not week or not end:
        return lines + ["None this week.", ""]
    elo = {r["name"]: (r, role) for role in ("attackers", "defenders")
           for r in end["leaderboard"][role]}
    scored = [(elo[n][0]["elo"], n) for n in week if n in elo]
    if not scored:
        return lines + ["No bot written this week is still on the ladder.", ""]
    _, name = max(scored)
    row, role = elo[name]
    rank = [r["name"] for r in end["leaderboard"][role]].index(name) + 1
    meta, py, _ = week[name]
    line = docstring_line(py) or "(no docstring)"
    result = meta.get("result") or {}
    beat = {True: "beat its target", False: "did not beat its target"}.get(
        result.get("beat_target"), "target not judged")
    return lines + [f"**{short(name)}** ({meta.get('persona', '?')}, {role[:-1]}): "
                    f"“{line}”", "",
                    f"Result: #{rank} {role[:-1]}, Elo {row['elo']:.0f}, wins "
                    f"{row['win_rate']:.0%} of its matches, {beat}.", ""]


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
                 balance: Path = ROOT / "BALANCE.md", health_text: str = None) -> str:
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
    lines += best_idea_section(metas, dates, end)
    lines += coverage_section(end)
    lines += findings_section(balance, dates)
    lines += health_section(nights, dates, prev, out, health_text)
    return "\n".join(lines).rstrip() + "\n"


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


def write(week: int, out: Path = DEFAULT_OUT, reports: Path = REPORTS, commit=False):
    text = build_report(week, out, health_text=health_output())
    (out / "meta").mkdir(parents=True, exist_ok=True)
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
    ap.add_argument("--commit", action="store_true", help="git-commit reports/WEEK_n.md")
    args = ap.parse_args()
    week = args.week if args.week else due_week()
    if week is None:
        print("meta report: not due")
        return 0
    path = write(week, commit=args.commit)
    print(f"meta report: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
