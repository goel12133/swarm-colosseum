"""Tactic library: one card per bot that mattered, grouped by tactic family.

    python -m colosseum.library             # writes out/library/
    python -m colosseum.library --out DIR

A bot gets a card if it ever reached the top five of its ladder (any night in out/history/,
or the current ladder) or if it holds unique coverage now: it is the only bot that breaches
some defender, or the only one that stops some attacker, in the latest breach table.
Retired bots keep their cards; their record comes from the last night they played.

    out/library/INDEX.md          families, one line per card, written for a reader
    out/library/cards/<name>.md   name, side, persona, author, description, idea, what it
                                  beats, what beats it, best and worst replay, source
    out/library/library.json      the same, machine-readable (the site bundle reads it)

Everything is derived from the league's own files, so a rebuild from the same out/ is
byte-identical. Bot files are untrusted: they are read as text and parsed with `ast`, never
imported, and every string from them is escaped before it reaches markdown.
"""
import argparse
import ast
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

from .house_league import unique_coverage
from .tournament import DEFAULT_OUT, ROOT

LIBRARY = DEFAULT_OUT / "library"
SOURCE_FOLDERS = ("attackers", "defenders", "house", "house/RETIRED",
                  "submitted/attacker", "submitted/defender",
                  "submitted/attacker/RETIRED", "submitted/defender/RETIRED")
LISTED = 5          # opponents listed under "beats" and "beaten by"

# Families are defined from what has actually emerged in season one (charter 3.7). A new
# bot lands in "unsorted" until someone places it here; the index says so.
FAMILIES = {
    "attacker": [
        ("Saturation",
         "Put more strikers into the defence at once than it can launch against. Wins on "
         "the launch cap and the magazine, not on cleverness.",
         ["rush", "2026-10-03_attacker_depth_shell_saturation"]),
        ("Synchronised arrival",
         "Engineer the arrival times so many strikers cross a line on the same tick from "
         "many bearings. The defender's per-tick launch cap becomes the bottleneck.",
         ["flanker", "2026-09-29_attacker_synchronized_ring",
          "2026-09-30_attacker_phase_locked_ring"]),
        ("Decoy screening",
         "Cheap decoys go first and soak up interceptors and gun rounds before the "
         "strikers arrive. Only works against a defender that commits before it identifies.",
         ["decoy_screen", "multi_axis"]),
        ("Trickle",
         "Never present a mass target. Small groups at intervals drain the magazine "
         "one engagement at a time, and the rest walk in.",
         ["trickle", "2026-09-28_attacker_staggered_screen_trickle"]),
    ],
    "defender": [
        ("Identify first",
         "Commit interceptors only to tracks confirmed as strikers, and retarget rather "
         "than waste. Beats decoys; the cost is engaging later.",
         ["identify_then_engage", "2026-09-28_defender_discriminating_ledger",
          "2026-09-30_defender_reveal_timed_prelaunch"]),
        ("Patient defence",
         "Hold fire until the attack packs itself together, then time each interceptor so "
         "one blast kills several strikers. The league's answer to synchronised rings.",
         ["2026-10-01_defender_convergence_blast_scheduler",
          "2026-10-02_defender_loiter_then_collapse",
          "2026-10-03_defender_backscheduled_blast_packer"]),
        ("Budgeted defence",
         "Think in time to impact and ration the magazine: plan for misses, order "
         "launches by deadline, keep depth for confirmed strikers.",
         ["layered", "2026-09-29_defender_miss_budget_scheduler"]),
        ("Value-model optimisation",
         "Write down what each tick's decision is worth and let a search (or a greedy "
         "picker over the same model) choose launches and gun shots together.",
         ["annealed_assignment", "annealed_assignment_eager", "greedy_value_model"]),
        ("Controls",
         "Deliberately naive baselines that anchor the ladder: commit on range alone, "
         "or never launch at all.",
         ["nearest_first", "gun_only"]),
    ],
}
UNSORTED = ("Unsorted",
            "Not yet placed in a family. A lead engineer should read the card and add the "
            "bot to FAMILIES in colosseum/library.py.")

# One-sentence ideas for bots whose docstring has no "Idea:" line and no summary first line.
# Written from the docstring, not from the code's behaviour.
IDEAS = {
    "2026-09-29_attacker_synchronized_ring":
        "Park every striker just outside the defender's identification gate, spread evenly "
        "round a ring, then release them together so the launch cap and the magazine run "
        "out before the ring does.",
    "2026-09-28_attacker_staggered_screen_trickle":
        "Send groups of two decoys and one striker every 18 ticks on rotating bearings, so "
        "the decoys draw the gun just before each striker arrives.",
    "2026-09-28_defender_discriminating_ledger":
        "Keep a strict ledger: one interceptor per confirmed striker, orphans retargeted to "
        "the most urgent uncovered striker, and the gun on strikers only.",
}


# --- untrusted text --------------------------------------------------------------

def md_safe(text: str) -> str:
    """Untrusted text as inert markdown: no HTML, no links, no code spans, no table cells."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`\[\]|])", r"\\\1", text)


def fence(source: str) -> str:
    """A code fence longer than any backtick run in the source, so the source cannot close
    it early and turn the rest of the card into markdown."""
    longest = max((len(m) for m in re.findall(r"`+", source)), default=0)
    return "`" * max(3, longest + 1)


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def display(name: str) -> str:
    m = re.match(r"\d{4}-\d{2}-\d{2}_(attacker|defender)_(.+)", name)
    if m:
        return m.group(2)
    return name.split("__", 1)[1] if "__" in name else name


# --- reading bots (ast only) -------------------------------------------------------

def find_source(name: str, bots_root: Path):
    """(path, retired?) for a bot by name, searching RETIRED folders too."""
    for folder in SOURCE_FOLDERS:
        p = bots_root / folder / f"{name}.py"
        if p.exists():
            return p, "RETIRED" in folder
    return None, False


def read_docstring(path: Path) -> str:
    try:
        return ast.get_docstring(ast.parse(path.read_text())) or ""
    except (SyntaxError, OSError, ValueError):
        return ""


BOOKKEEPING = re.compile(r"(NAME|Name|Target|Idea|Core idea)\s*:", re.I)


def paragraphs(doc: str):
    """Docstring paragraphs as single lines, without section underlines or bullet marks."""
    out = []
    for block in re.split(r"\n\s*\n", doc):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        lines = [l for i, l in enumerate(lines)
                 if not re.fullmatch(r"[-=~]{3,}", l)
                 and not (i + 1 < len(lines) and re.fullmatch(r"[-=~]{3,}", lines[i + 1]))]
        lines = [re.sub(r"^[*\-]\s+", "", l) for l in lines]
        if lines:
            out.append(" ".join(" ".join(lines).split()))
    return out


def idea_of(name: str, doc: str) -> str:
    m = re.search(r"^\s*(?:Core )?idea:\s*(.+(?:\n(?!\s*\n).+)*)", doc, re.M | re.I)
    if m:
        text = " ".join(m.group(1).split())
    elif name in IDEAS:
        text = IDEAS[name]
    else:
        paras = [p for p in paragraphs(doc) if not BOOKKEEPING.match(p)]
        text = paras[0] if paras else ""
        text = re.sub(r"^[\w ,'-]{1,40}:\s+", "", text)          # "Rush: everything ..."
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    first = first[:1].upper() + first[1:]
    return first if len(first) <= 300 else first[:297] + "..."


def description_of(doc: str, limit: int = 700) -> str:
    """One paragraph: the docstring's prose with bookkeeping and short titles dropped, cut
    at a sentence boundary near `limit` characters."""
    paras = [p for p in paragraphs(doc) if not BOOKKEEPING.match(p) and len(p) >= 40]
    text = " ".join(paras)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "..."


def origin(path: Path, meta: dict):
    """(persona, author) as a reader should see them."""
    if path is not None and "submitted" in path.parts:
        return meta.get("persona") or "outside submission", meta.get("author") or "unknown"
    if path is not None and "house" in path.parts:
        model = meta.get("model")
        return (meta.get("persona") or "unrecorded",
                "house league" + (f" (model {model})" if model else ""))
    return "hand-written baseline", "Pelennor"


# --- league data ---------------------------------------------------------------------

def load_snapshots(out: Path):
    """[(label, {leaderboard, matrix, breaches})] oldest first: every night in history/,
    then the current files if they differ from the last night."""
    snaps = []
    for d in sorted(p for p in (out / "history").glob("*") if p.is_dir()):
        snap = _load(d)
        if snap:
            snaps.append((d.name, snap))
    current = _load(out)
    if current and (not snaps or current != snaps[-1][1]):
        snaps.append(("current", current))
    return snaps


def _load(d: Path):
    if not (d / "leaderboard.json").exists():
        return None
    snap = dict(leaderboard=json.loads((d / "leaderboard.json").read_text()))
    for key in ("matrix", "breaches"):
        p = d / f"{key}.json"
        snap[key] = json.loads(p.read_text()) if p.exists() else None
    return snap


def side_of(role: str) -> str:
    return "attacker" if role == "attackers" else "defender"


def select(snaps):
    """name -> side for every bot that earns a card, plus its best finish per night."""
    finishes, side = {}, {}
    for label, snap in snaps:
        for role in ("attackers", "defenders"):
            for rank, row in enumerate(snap["leaderboard"][role], 1):
                finishes.setdefault(row["name"], []).append((label, rank))
                side[row["name"]] = side_of(role)
    chosen = {n for n, f in finishes.items() if any(rank <= 5 for _, rank in f)}
    latest = snaps[-1][1]
    only = {}
    if latest.get("breaches"):
        for role in ("attackers", "defenders"):
            for row in latest["leaderboard"][role]:
                cov = unique_coverage(row["name"], side_of(role), latest["breaches"])
                if cov:
                    only[row["name"]] = cov
                    chosen.add(row["name"])
    return {n: side[n] for n in sorted(chosen)}, finishes, only


def record(name: str, side: str, snaps):
    """Per-opponent results from the last night `name` played: [(opp, mine, wins, seeds)]."""
    for label, snap in reversed(snaps):
        names = {r["name"] for r in snap["leaderboard"][side + "s"]}
        if name not in names or not snap.get("matrix"):
            continue
        matrix = snap["matrix"]["matrix"]
        b = (snap.get("breaches") or {}).get("breaches", {})
        seeds = (snap.get("breaches") or {}).get("seeds") or len(snap["leaderboard"]["seeds"])
        rows = []
        if side == "attacker":
            for opp, s in matrix.get(name, {}).items():
                rows.append((opp, 1 - s, b.get(name, {}).get(opp), seeds))
        else:
            for opp, row in matrix.items():
                if name in row:
                    held = b.get(opp, {}).get(name)
                    rows.append((opp, row[name], None if held is None else seeds - held,
                                 seeds))
        return label, sorted(rows)
    return None, []


def replay_index(out: Path, live: set):
    """name -> [(own score, stem, meta)] over the replays in out/replays/ between two bots
    of the current roster (older files may be from dry runs or retired opponents)."""
    by_bot = {}
    for p in sorted((out / "replays").glob("*__*__s*.json")):
        a, d, _ = p.stem.split("__")
        if a not in live or d not in live:
            continue
        try:
            meta = json.loads(p.read_text())["meta"]
        except (ValueError, KeyError, OSError):
            continue
        by_bot.setdefault(a, []).append((1 - meta["score_defender"], p.stem, meta))
        by_bot.setdefault(d, []).append((meta["score_defender"], p.stem, meta))
    return by_bot


def family_of(name: str, side: str):
    for title, blurb, members in FAMILIES[side]:
        if name in members:
            return title, blurb
    return UNSORTED


# --- writing ----------------------------------------------------------------------

def result_line(opp, mine, wins, seeds, side):
    verb = "breached" if side == "attacker" else "held"
    won = f"{verb} in {wins} of {seeds} seeds, " if wins is not None else ""
    return f"- **{md_safe(display(opp))}**: {won}mean score {mine:.2f}"


def replay_line(entry, side, card_dir: Path, out: Path):
    score, stem, meta = entry
    a, d, _ = stem.split("__")
    opp = d if side == "attacker" else a
    link = Path(os.path.relpath(out / "replays", card_dir)).as_posix() + "/" + quote(stem)
    return (f"vs **{md_safe(display(opp))}**, seed {meta['seed']}: {md_safe(meta['outcome'])} "
            f"in {meta['ticks']} ticks, its score {score:.2f}. "
            f"[{md_safe(stem)}.json]({link}.json)")


def card(name, side, path, retired, meta, finishes, only, rec, replays, card_dir, out):
    doc = read_docstring(path) if path else ""
    persona, author = origin(path, meta)
    family, _ = family_of(name, side)
    best = min(finishes, key=lambda f: (f[1], f[0]))
    top5 = sum(1 for _, rank in finishes if rank <= 5)
    status = "retired" if retired else "live"
    label, rows = rec
    lines = [f"# {md_safe(display(name))}", "",
             f"**{side}** · family: {family} · persona: {md_safe(persona)} · "
             f"author: {md_safe(author)} · {status}", "",
             f"File: {md_safe(name)}.py", "",
             f"**The idea:** {md_safe(idea_of(name, doc)) or '(no docstring)'}", "",
             "## What it does", "",
             md_safe(description_of(doc)) or "No docstring.", "",
             "## Record", "",
             f"- Best finish: #{best[1]} {side} ({best[0]}).",
             f"- In the top five on {top5} of the {len(finishes)} nights it played.",
             ]
    if meta.get("target"):
        lines.append(f"- Written against: **{md_safe(display(str(meta['target'])))}**.")
    if only:
        verb = "breaches" if side == "attacker" else "stops"
        lines.append(f"- The only bot that {verb}: "
                     + ", ".join(f"**{md_safe(display(o))}**" for o in only) + ".")
    lines.append("")

    def won(r):
        return r[2] / r[3] if r[2] is not None else r[1]
    beats = sorted((r for r in rows if won(r) > 0.5), key=lambda r: (-won(r), -r[1], r[0]))
    beaten = sorted((r for r in rows if won(r) < 0.5), key=lambda r: (won(r), r[1], r[0]))
    when = "the current tournament" if label == "current" else f"night {label}"
    lines += ["## What it beats", "", f"Opponents it wins against most of the time, from {when}.",
              ""]
    lines += [result_line(*r, side) for r in beats[:LISTED]] or [
        "- No opponent: it loses to every one more often than it wins."]
    if len(beats) > LISTED:
        lines.append(f"- … and {len(beats) - LISTED} more.")
    lines += ["", "## What beats it", ""]
    lines += [result_line(*r, side) for r in beaten[:LISTED]] or [
        "- No opponent beats it more often than not."]
    if len(beaten) > LISTED:
        lines.append(f"- … and {len(beaten) - LISTED} more.")

    lines += ["", "## Replays", ""]
    if replays:
        ordered = sorted(replays, key=lambda r: (-r[0], r[1]))
        lines += ["- Best: " + replay_line(ordered[0], side, card_dir, out),
                  "- Worst: " + replay_line(ordered[-1], side, card_dir, out), "",
                  "Open one with `python viewer/build_viewer.py <replay>`, then "
                  "`viewer/index.html`."]
    else:
        lines.append("No replay kept: it has not played in the latest tournament.")

    src = path.read_text() if path else ""
    f = fence(src)
    lines += ["", "## Source", ""]
    lines += [f"{f}python", src.rstrip("\n"), f] if path else ["Source not found."]
    return "\n".join(lines) + "\n", dict(
        name=name, side=side, family=family, persona=persona, author=author, status=status,
        idea=idea_of(name, doc), best_rank=best[1], top5_nights=top5, nights=len(finishes),
        unique_coverage=only, card=f"cards/{slugify(name)}.md")


def build(dest: Path = LIBRARY, out: Path = DEFAULT_OUT, bots_root: Path = ROOT / "bots"):
    snaps = load_snapshots(out)
    if not snaps:
        raise SystemExit(f"no ladder in {out}: run a tournament first")
    chosen, finishes, only = select(snaps)
    live = {r["name"] for role in ("attackers", "defenders")
            for r in snaps[-1][1]["leaderboard"][role]}
    replays = replay_index(out, live)
    if dest.exists():
        shutil.rmtree(dest)
    cards_dir = dest / "cards"
    cards_dir.mkdir(parents=True)
    entries = []
    for name, side in chosen.items():
        path, retired = find_source(name, bots_root)
        meta = {}
        if path is not None and path.with_suffix(".meta.json").exists():
            meta = json.loads(path.with_suffix(".meta.json").read_text())
        text, entry = card(name, side, path, retired or name not in live, meta,
                           finishes[name], only.get(name, []), record(name, side, snaps),
                           replays.get(name, []), cards_dir, out)
        (cards_dir / f"{slugify(name)}.md").write_text(text)
        entries.append(entry)
    (dest / "INDEX.md").write_text(index(entries, snaps))
    (dest / "library.json").write_text(json.dumps(
        dict(as_of=snaps[-1][0], cards=entries), indent=2, sort_keys=True) + "\n")
    return dict(library=str(dest), cards=len(entries), as_of=snaps[-1][0])


def index(entries, snaps):
    nights = [label for label, _ in snaps if label != "current"]
    span = f"{nights[0]} to {nights[-1]}" if nights else "the current tournament"
    lines = ["# Swarm Colosseum tactic library", "",
             "Every tactic the league has found worth keeping. A bot gets a card if it ever "
             "reached the top five of its ladder, or if it is the only bot that beats some "
             "opponent. Cards are grouped by family: the broad idea, whatever the details.", "",
             f"Evidence: {len(nights)} nights of the house league ({span}). Each card shows "
             "what the bot says it does (from its own docstring), what it beats and what "
             "beats it on the last night it played, its best and worst replay, and its full "
             "source. All units are abstract: `u` for distance, `ticks` for time, "
             "`credits` for cost.", ""]
    for side in ("attacker", "defender"):
        lines += [f"## {side.capitalize()}s", ""]
        mine = [e for e in entries if e["side"] == side]
        families = FAMILIES[side] + [UNSORTED + ([],)]
        for title, blurb, _ in families:
            members = sorted((e for e in mine if e["family"] == title),
                             key=lambda e: (e["best_rank"], e["name"]))
            if not members:
                continue
            lines += [f"### {title}", "", blurb, ""]
            for e in members:
                tag = "" if e["status"] == "live" else " (retired)"
                lines.append(f"- [{md_safe(display(e['name']))}]({e['card']}){tag}: "
                             f"{md_safe(e['idea'])} Best #{e['best_rank']}.")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=LIBRARY)
    args = ap.parse_args()
    info = build(args.out)
    print(f"{info['library']}: {info['cards']} tactic cards, as of {info['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
