"""Match result cache: warm runs are byte-identical and only play what's new."""
from pathlib import Path

import pytest

from colosseum import cache as cache_mod
from colosseum import tournament as T
from colosseum.rules import SEASON0
from colosseum.sim import run_match

ROOT = Path(__file__).resolve().parents[1]
ATT = sorted((ROOT / "bots" / "attackers").glob("*.py"))
DEF = sorted((ROOT / "bots" / "defenders").glob("*.py"))[:4]
OUTPUTS = ("leaderboard.json", "matrix.json", "breaches.json", "BALANCE.md")


def outputs(out):
    return {f: (out / f).read_bytes() for f in OUTPUTS}


def test_cold_and_warm_runs_are_byte_identical_and_warm_plays_nothing(tmp_path):
    out = tmp_path / "out"
    T.run_tournament(seeds=2, out=out, quiet=True, roster=(ATT, DEF))
    cold = outputs(out)
    assert T.LAST_RUN["ran"] == len(ATT) * len(DEF) * 2 and T.LAST_RUN["cached"] == 0
    T.run_tournament(seeds=2, out=out, quiet=True, roster=(ATT, DEF))
    assert T.LAST_RUN["ran"] == 0 and T.LAST_RUN["cached"] == len(ATT) * len(DEF) * 2
    assert outputs(out) == cold
    # and identical to a run with no cache at all
    T.run_tournament(seeds=2, out=tmp_path / "nocache", quiet=True, roster=(ATT, DEF),
                     cache=False)
    assert outputs(tmp_path / "nocache") == cold


def test_adding_one_bot_plays_exactly_its_matches(tmp_path):
    out = tmp_path / "out"
    T.run_tournament(seeds=2, out=out, quiet=True, roster=(ATT[:-1], DEF))
    T.run_tournament(seeds=2, out=out, quiet=True, roster=(ATT, DEF))
    assert T.LAST_RUN["ran"] == 1 * len(DEF) * 2
    warm = outputs(out)
    T.run_tournament(seeds=2, out=tmp_path / "fresh", quiet=True, roster=(ATT, DEF),
                     cache=False)
    assert warm == outputs(tmp_path / "fresh")


def test_a_rules_change_or_an_engine_change_plays_everything_again(tmp_path, monkeypatch):
    out = tmp_path / "out"
    n = len(ATT) * len(DEF) * 1
    T.run_tournament(seeds=1, out=out, quiet=True, roster=(ATT, DEF))
    T.run_tournament(seeds=1, out=out, quiet=True, roster=(ATT, DEF),
                     rules=SEASON0.tuned(gun_ammo=121))
    assert T.LAST_RUN["ran"] == n
    monkeypatch.setattr(cache_mod, "engine_version", lambda: "a-different-engine")
    T.run_tournament(seeds=1, out=out, quiet=True, roster=(ATT, DEF))
    assert T.LAST_RUN["ran"] == n


def test_a_cached_entry_is_the_fresh_match(tmp_path):
    out = tmp_path / "out"
    T.run_tournament(seeds=1, out=out, quiet=True, roster=(ATT[:1], DEF[:1]))
    store = cache_mod.ResultCache(out / "cache" / "results.sqlite")
    meta = store.get(store.key(ATT[0], DEF[0], 0, SEASON0))
    assert meta == run_match(ATT[0], DEF[0], 0, record=False)["meta"]


def test_editing_a_bot_file_invalidates_only_its_matches(tmp_path):
    bots = tmp_path / "bots"
    bots.mkdir()
    copy = bots / ATT[0].name
    copy.write_text(ATT[0].read_text())
    roster = ([copy] + ATT[1:], DEF)
    out = tmp_path / "out"
    T.run_tournament(seeds=1, out=out, quiet=True, roster=roster)
    copy.write_text(ATT[0].read_text() + "\n# edited\n")
    T.run_tournament(seeds=1, out=out, quiet=True, roster=roster)
    assert T.LAST_RUN["ran"] == len(DEF)
