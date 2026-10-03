"""Tactic library: who gets a card, what the card says, and that untrusted bot text stays
inert. Built on a synthetic out/ and bots/ tree: no tournament runs and no bot is executed."""
import json
import re

import pytest

from colosseum import library
from colosseum.tournament import ROOT

ATTACKERS = [f"a{i}" for i in range(1, 8)]          # a6: unique coverage; a7: no card
EVIL = "2026-01-02_attacker_evil"                    # house bot, top five, hostile text
OLD = "2026-01-01_defender_old"                      # retired after night 1, top five then


def snapshot(attackers, defenders, breaches, seeds=10):
    lb = {"attackers": [dict(name=n, elo=1000 - i, win_rate=0.5, mean_score=0.5)
                        for i, n in enumerate(attackers)],
          "defenders": [dict(name=n, elo=1000 - i, win_rate=0.5, mean_score=0.5)
                        for i, n in enumerate(defenders)],
          "seeds": list(range(seeds))}
    matrix = {a: {d: 1 - breaches[a][d] / seeds for d in defenders} for a in attackers}
    return {"leaderboard.json": lb, "matrix.json": {"matrix": matrix},
            "breaches.json": {"breaches": breaches, "seeds": seeds}}


def write(d, snap):
    d.mkdir(parents=True, exist_ok=True)
    for name, obj in snap.items():
        (d / name).write_text(json.dumps(obj))


@pytest.fixture
def tree(tmp_path):
    bots, out = tmp_path / "bots", tmp_path / "out"
    marker = tmp_path / "IMPORTED"
    for folder in ("attackers", "defenders", "house/RETIRED"):
        (bots / folder).mkdir(parents=True)
    for a in ATTACKERS:
        (bots / "attackers" / f"{a}.py").write_text(
            f'"""{a.upper()}: a plain baseline attacker.\n\nIt flies at the asset and '
            f'hopes for the best, which is the whole of its plan."""\nNAME = "{a}"\n')
    for d in ("d1", "d2"):
        (bots / "defenders" / f"{d}.py").write_text(f'"""{d}: shoots."""\nNAME = "{d}"\n')
    (bots / "house" / f"{EVIL}.py").write_text(
        '"""Idea: <script>alert(1)</script> see [here](https://example.com) | cell.\n\n'
        'This bot hides ``` a fence and `code` in its docstring so a careless card ends '
        'its code block early.\n"""\n'
        f'open({str(marker)!r}, "w").write("x")\nraise SystemExit("imported")\n'
        's = """\n````\n# Not a heading\n"""\n')
    (bots / "house" / f"{EVIL}.meta.json").write_text(json.dumps(dict(
        persona="exploiter", model="opus", target="d1", author="<b>x</b>")))
    (bots / "house" / "RETIRED" / f"{OLD}.py").write_text(
        '"""Idea: hold everything back until the last moment."""\n')
    (bots / "house" / "RETIRED" / f"{OLD}.meta.json").write_text(
        json.dumps(dict(persona="contrarian", model="opus")))

    attackers = [EVIL] + ATTACKERS
    full = lambda n: {d: n for d in ("d1", "d2", OLD)}            # noqa: E731
    night1 = {a: full(5) for a in attackers}
    night1["a7"] = full(0)
    write(out / "history" / "2026-01-01",
          snapshot(attackers, ["d1", OLD, "d2"], night1))
    now = {a: {"d1": 6, "d2": 3} for a in attackers}
    now["a1"] = {"d1": 10, "d2": 9}
    now["a6"] = {"d1": 0, "d2": 0}
    now["a7"] = {"d1": 0, "d2": 0}
    for a in attackers:
        if a not in ("a6", "a7"):
            now[a]["d2"] = 0
    now["a6"]["d2"] = 1                       # a6 is the only attacker that ever breaches d2
    snap = snapshot(attackers, ["d1", "d2"], now)
    write(out / "history" / "2026-01-02", snap)
    write(out, snap)

    (out / "replays").mkdir()
    for stem, sd in (("a1__d1__s0", 0.1), ("a1__d1__s1", 0.4), ("a1__d2__s0", 0.3),
                     ("2026-01-01_attacker_dryrun__d1__s0", 0.0)):
        (out / "replays" / f"{stem}.json").write_text(json.dumps({"meta": dict(
            seed=int(stem[-1]), outcome="breached", ticks=100, score_defender=sd)}))
    dest = tmp_path / "library"
    info = library.build(dest, out, bots)
    return dest, info, marker, out, bots


def cards(dest):
    return {p.stem: p.read_text() for p in (dest / "cards").glob("*.md")}


def test_cards_for_the_top_five_ever_and_for_unique_coverage(tree):
    dest, info, *_ = tree
    got = set(cards(dest))
    # EVIL and a1..a4 are the attacker top five; a6 is the only one through d2.
    assert got == {EVIL, "a1", "a2", "a3", "a4", "a6", "d1", "d2", OLD}
    assert info["cards"] == len(got)
    assert "The only bot that breaches: **d2**" in cards(dest)["a6"]


def test_a_retired_bot_keeps_its_card_and_its_last_record(tree):
    dest, *_ = tree
    old = cards(dest)[OLD]
    assert "· retired" in old and "persona: contrarian" in old
    assert "from night 2026-01-01" in old
    assert "No replay kept" in old
    entry = {e["name"]: e for e in json.loads((dest / "library.json").read_text())["cards"]}
    assert entry[OLD]["status"] == "retired" and entry["a1"]["status"] == "live"


def test_beats_and_beaten_by_come_from_the_breach_table(tree):
    dest, *_ = tree
    a1 = cards(dest)["a1"]
    beats = a1.split("## What it beats")[1].split("## What beats it")[0]
    beaten = a1.split("## What beats it")[1].split("## Replays")[0]
    assert "**d1**: breached in 10 of 10 seeds" in beats
    assert "**d2**: breached in 0 of 10 seeds" in beaten and "d2" not in beats
    a5 = cards(dest).get("a5")
    assert a5 is None                         # sixth on both nights, covers nothing alone
    evil = cards(dest)[EVIL]
    assert "No opponent: it loses" not in evil
    assert "**d1**: breached in 6 of 10 seeds" in evil.split("## What beats it")[0]
    d1 = cards(dest)["d1"]
    assert "**a6**: held in 10 of 10 seeds" in d1.split("## What beats it")[0]
    assert "**a1**: held in 0 of 10 seeds" in d1.split("## What beats it")[1]


def test_best_and_worst_replay_only_from_the_current_roster(tree):
    dest, *_ = tree
    a1 = cards(dest)["a1"]
    assert "Best: vs **d1**, seed 0" in a1 and "(../../out/replays/a1__d1__s0.json)" in a1
    assert "Worst: vs **d1**, seed 1" in a1
    d1 = cards(dest)["d1"]
    assert "dryrun" not in d1
    assert "Best: vs **a1**, seed 1" in d1


def test_untrusted_text_stays_inert(tree):
    dest, *_ = tree
    evil = cards(dest)[EVIL]
    prose, source = evil.split("## Source")
    assert "<script" not in prose and "&lt;script&gt;" in prose
    assert "[here](" not in prose and "\\[here\\](" in prose      # no live link
    assert "\\`\\`\\`" in prose and "\\|" in prose
    # The source sits in one fence longer than any backtick run in it.
    fences = [l for l in source.splitlines() if re.fullmatch(r"`{3,}(python)?", l)]
    assert fences[0] == "`````python" and fences[-1] == "`````"
    assert sum(1 for l in source.splitlines() if l.startswith("`````")) == 2
    index = (dest / "INDEX.md").read_text()
    assert "<script" not in index and "[here](" not in index


def test_bots_are_parsed_never_imported(tree):
    _, _, marker, *_ = tree
    assert not marker.exists()


def test_rebuild_is_byte_identical(tree, tmp_path):
    dest, _, _, out, bots = tree
    again = tmp_path / "again"
    library.build(again, out, bots)
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            q = again / p.relative_to(dest)
            assert p.read_bytes() == q.read_bytes(), p.name


def test_bots_outside_the_families_are_listed_as_unsorted(tree):
    dest, *_ = tree
    index = (dest / "INDEX.md").read_text()
    unsorted = index.split("### Unsorted")[1]
    assert "evil" in unsorted.split("## Defenders")[0]
    assert "family: Unsorted" in cards(dest)[EVIL]


def test_every_family_member_is_a_real_bot_on_its_side():
    seen = set()
    for side, families in library.FAMILIES.items():
        for _, _, members in families:
            for name in members:
                path, _ = library.find_source(name, ROOT / "bots")
                assert path is not None, name
                assert f"_{side}_" in name or path.parent.name == side + "s", name
                assert name not in seen, f"{name} is in two families"
                seen.add(name)
    assert set(library.IDEAS) <= seen


def test_md_safe_neutralises_markup():
    s = library.md_safe('<img src=x> [a](b) `c` | d & \\')
    assert "<" not in s and ">" not in s
    assert s == '&lt;img src=x&gt; \\[a\\](b) \\`c\\` \\| d &amp; \\\\'
