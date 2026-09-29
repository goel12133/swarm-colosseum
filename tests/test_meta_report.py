"""Meta report: built from a fabricated seven-night history, every section present."""
import json
from datetime import date, timedelta
from pathlib import Path

from colosseum import meta_report as mr
from colosseum import season

ROOT = Path(__file__).resolve().parents[1]
DATES = [(date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(7)]
HOUSE_A = "2026-10-01_attacker_reserve_wave"
HOUSE_D = "2026-10-03_defender_label_skeptic"


def ladder(extra_elo):
    atts = [("rush", 900), ("flanker", 1000), (HOUSE_A, 1000 + extra_elo), ("trickle", 1010),
            ("multi_axis", 990), ("decoy_screen", 980)]
    defs = [("layered", 1000), ("gun_only", 800), (HOUSE_D, 1050 + extra_elo),
            ("identify_then_engage", 1020), ("nearest_first", 900)]

    def rows(pairs, role):
        return sorted([dict(name=n, role=role, elo=float(e), win_rate=0.5, mean_score=0.5,
                            mean_cer=1.0, matches=10) for n, e in pairs],
                      key=lambda r: -r["elo"])
    return dict(attackers=rows(atts, "attacker"), defenders=rows(defs, "defender"))


def fabricate(tmp_path):
    out = tmp_path / "out"
    bots = tmp_path / "bots"
    (bots / "house").mkdir(parents=True)
    (bots / "house" / "RETIRED").mkdir()
    rows = []
    for i, d in enumerate(DATES):
        failed = i == 4
        rows.append(dict(
            date=d, status="error" if failed else "ok",
            reason="claude CLI failed (exit 1): Not logged in" if failed else None,
            written=[] if failed else [f"{d}_attacker_x.py"],
            rejected=[["defender", "imports socket"]] if i == 2 else [],
            retired=["2026-09-20_attacker_old"] if i == 6 else [],
            spend=dict(calls=2, input_tokens=5000, output_tokens=7000),
            phases=dict(generation=60.0, tournament=120.0 + i),
            tournament_seconds=None if failed else 120.0 + i))
        if not failed:
            snap = out / "history" / d
            snap.mkdir(parents=True)
            lb = ladder(10 * i)
            (snap / "leaderboard.json").write_text(json.dumps(lb))
            defenders = [r["name"] for r in lb["defenders"]]
            b = {a["name"]: {dd: (0 if dd == HOUSE_D else 3) for dd in defenders}
                 for a in lb["attackers"]}
            b["rush"] = {dd: 10 for dd in defenders}             # nobody stops rush
            b["rush"][HOUSE_D] = 10
            for a in b:
                if a != "rush":
                    b[a][HOUSE_D] = 0
            (snap / "breaches.json").write_text(json.dumps(dict(seeds=10, breaches=b)))
    out.mkdir(exist_ok=True)
    (out / "nights.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    for name, persona, role, beat in [(HOUSE_A, "counter_meta", "attacker", True),
                                      (HOUSE_D, "contrarian", "defender", False)]:
        (bots / "house" / f"{name}.py").write_text(
            f'"""NAME: {name}\n\nHolds three strikers back until the defender\'s stock is '
            f'gone, then sends them together. Second sentence.\n"""\n'
            f'NAME = "{name}"\nROLE = "{role}"\ndef act(obs):\n    return {{}}\n')
        (bots / "house" / f"{name}.meta.json").write_text(json.dumps(dict(
            name=name, role=role, date=name[:10], persona=persona, target="x",
            result=dict(beat_target=beat, rank=1))))
    balance = tmp_path / "BALANCE.md"
    balance.write_text("# Rules findings\n\n## S0-2 — Something new (2026-10-02)\n\ntext\n\n"
                       "## S0-1 — Old news (2026-09-28)\n\ntext\n")
    return out, bots, balance


def test_a_fabricated_week_has_every_section(tmp_path):
    out, bots, balance = fabricate(tmp_path)
    text = mr.build_report(1, out=out, bots_root=bots, balance=balance,
                           health_text="docker ok\ncli-login ok")
    for heading in ("# Week 1 — 2026-10-01 to 2026-10-07", "## Ladders",
                    "## Which personas produced winners", "## Best new idea", "## Coverage",
                    "## Rules findings", "## Health"):
        assert heading in text, heading
    # ladder: exactly one table, house bots marked, Elo change since the week's first night
    assert sum(1 for l in text.splitlines() if l.startswith("|---")) == 1
    assert "reserve_wave (h)" in text and "(+60)" in text
    # personas
    assert "**counter_meta**: 1 written, 1 beat their target, 1 still alive" in text
    assert "**generalist**: no bots this week." in text
    # best idea: quoted from the docstring, first real sentence only
    assert "Holds three strikers back until the defender's stock is gone" in text
    assert "Second sentence" not in text
    # coverage flags
    assert "no attacker can breach label_skeptic (h)" not in text     # rush breaches it
    assert "no defender can stop rush" in text
    # findings: only this week's
    assert "S0-2 — Something new" in text and "Old news" not in text
    # health
    assert "Nights run: 7" in text
    assert "2026-10-05 (claude CLI failed (exit 1): Not logged in)" in text
    assert "defender: imports socket" in text
    assert "Retired: old (h)" in text
    assert "Tokens: 84,000 this week" in text
    assert "docker ok" in text
    # phone-readable: no raw JSON
    assert "{" not in text and "}" not in text


def test_coverage_flags_a_defender_nobody_breaches(tmp_path):
    out, bots, balance = fabricate(tmp_path)
    last = out / "history" / DATES[-1] / "breaches.json"
    b = json.loads(last.read_text())
    b["breaches"]["rush"][HOUSE_D] = 0
    last.write_text(json.dumps(b))
    text = mr.build_report(1, out=out, bots_root=bots, balance=balance)
    assert "no attacker can breach label_skeptic (h)" in text
    assert "- label_skeptic (h): **nobody**" in text


def test_due_only_on_the_seventh_night_and_only_once(tmp_path):
    out, _, _ = fabricate(tmp_path)
    assert mr.due_week(out) == 1
    (out / "meta").mkdir()
    (out / "meta" / "WEEK_1.md").write_text("done")
    assert mr.due_week(out) is None
    lines = (out / "nights.jsonl").read_text().splitlines()[:6]
    (out / "nights.jsonl").write_text("\n".join(lines) + "\n")
    (out / "meta" / "WEEK_1.md").unlink()
    assert mr.due_week(out) is None


def test_several_runs_on_one_date_are_one_night(tmp_path):
    out, _, _ = fabricate(tmp_path)
    with open(out / "nights.jsonl", "a") as f:
        f.write(json.dumps(dict(date=DATES[-1], status="ok", spend={})) + "\n")
    assert len(mr.load_nights(out)) == 7


def test_season_md_matches_season_py():
    text = (ROOT / "SEASON.md").read_text()
    assert season.FIRST_NIGHT.isoformat() in text
    assert season.LAST_NIGHT.isoformat() in text
    assert season.ENDS.isoformat() in text
    assert season.ENDS.isoformat() == "2026-10-26"


def test_best_idea_prefers_an_explicit_idea_line(tmp_path):
    py = tmp_path / "b.py"
    py.write_text('"""NAME: b\n\nTarget: layered, because reasons.\n\n'
                  'Idea: fire the gun at close decoys in case the label is wrong.\n"""\n')
    assert mr.docstring_line(py) == "fire the gun at close decoys in case the label is wrong."
    py.write_text('"""NAME: b\n\nTarget: layered.\n\nThis bot waits. Then it strikes.\n"""\n')
    assert mr.docstring_line(py) == "This bot waits."


def test_best_match_replay_prefers_the_target(tmp_path):
    rep = tmp_path / "replays"
    rep.mkdir()
    for a, d, seed, score in [("hb", "layered", 0, 0.1), ("hb", "rush_d", 1, 0.0),
                              ("hb", "layered", 2, 0.3)]:
        (rep / f"{a}__{d}__s{seed}.json").write_text(json.dumps(
            {"meta": {"score_defender": score}}))
    p, opp = mr.best_match_replay(tmp_path, "hb", "attacker", target="layered")
    assert opp == "layered" and p.name == "hb__layered__s0.json"
    p, opp = mr.best_match_replay(tmp_path, "hb", "attacker", target=None)
    assert opp == "rush_d"
