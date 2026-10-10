"""Packed replays and the site-trim rule (post-launch, 2026-10-10)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colosseum import replay_pack, site

ROOT = Path(__file__).resolve().parents[1]


def synthetic():
    """Ids that appear late and vanish, an interceptor, and a negative zero."""
    return {"meta": {"attacker": "a", "defender": "d", "seed": 3},
            "events": [{"kind": "kill", "t": 2, "x": 1.5, "y": -0.5}],
            "frames": [{"t": 1, "hp": 30, "d": [[1, 1, 480.0, 10.0]], "i": []},
                       {"t": 2, "hp": 30, "d": [[1, 1, 476.1, -0.0], [2, 0, 470.8, 47.2]],
                        "i": [[7, 0.3, -12.9]]},
                       {"t": 3, "hp": 20, "d": [[2, 0, 466.9, 44.0]], "i": [[7, 4.4, -0.1]]}]}


def test_pack_round_trips_and_is_deterministic():
    rep = synthetic()
    data = replay_pack.pack(rep)
    assert replay_pack.unpack(data) == rep
    assert replay_pack.pack(rep) == data                      # no timestamp in the gzip
    assert data[:2] == b"\x1f\x8b"


def test_unpack_refuses_other_formats():
    with pytest.raises(ValueError):
        replay_pack.unpack_doc({"frames": []})


def test_real_replays_round_trip():
    files = sorted((ROOT / "out" / "replays").glob("*__*__s*.json"))[::50]
    if not files:
        pytest.skip("no replays in out/")
    for p in files:
        rep = json.loads(p.read_text())
        assert replay_pack.unpack(replay_pack.pack(rep)) == rep, p.name


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_viewer_unpacks_exactly_like_python(tmp_path):
    """The browser's unpackReplay (viewer/template.html) against the Python reference."""
    tpl = (ROOT / "viewer" / "template.html").read_text()
    fn = re.search(r"function unpackReplay\(doc\)\{.*?\n\}\n", tpl, re.S).group(0)
    rep = synthetic()
    (tmp_path / "t.js").write_text(
        fn + f"\nconst u = unpackReplay({json.dumps(replay_pack.pack_doc(rep))});\n"
        "process.stdout.write(JSON.stringify(u));\n")
    out = subprocess.run(["node", str(tmp_path / "t.js")], capture_output=True, text=True,
                         check=True).stdout
    assert json.loads(out) == rep


# --- the rule: which matches get a full page ------------------------------------------

def meta(a, d, sa):
    return {"attacker": a, "defender": d, "score_attacker": sa, "score_defender": 1 - sa}


def test_full_pages_are_this_week_last_week_and_each_bots_best_and_worst():
    first = "2026-09-28"                       # week 0: 09-28..10-04, week 1: 10-05.., ...
    old = "2026-09-29_attacker_old"            # first played in week 0
    new = "2026-10-13_attacker_new"            # week 2
    base_d, mid_d = "layered", "2026-10-06_defender_mid"          # week 0 and week 1
    metas = {
        f"{old}__{base_d}__s0": meta(old, base_d, 0.5),
        f"{old}__{base_d}__s1": meta(old, base_d, 0.6),
        f"{old}__{base_d}__s2": meta(old, base_d, 0.4),
        f"{old}__{mid_d}__s0": meta(old, mid_d, 0.3),
        f"{new}__{base_d}__s0": meta(new, base_d, 0.9),
    }
    full = site.full_page_stems(metas, as_of="2026-10-14", first_night=first)
    # week 2 is current, week 1 previous: the mid defender's and the new attacker's matches
    assert f"{old}__{mid_d}__s0" in full and f"{new}__{base_d}__s0" in full
    # week 0 matches stay only as a bot's best or worst: old's best is s1 (0.6), and
    # layered's best (as defender, 1 - 0.4 = 0.6) is s2; s0 is neither, so it is data only
    assert f"{old}__{base_d}__s1" in full and f"{old}__{base_d}__s2" in full
    assert f"{old}__{base_d}__s0" not in full
    assert site.match_night(f"{new}__{base_d}__s0", first) == "2026-10-13"
    assert site.match_night(f"rush__{base_d}__s0", first) == first


def test_replay_links_go_to_the_page_or_the_viewer():
    full = {"a__b__s0"}
    assert site.replay_href("a__b__s0", full) == "replays/a__b__s0.html"
    assert site.replay_href("a__b__s1", full, "../") == \
        "../replays/viewer.html?r=data/a__b__s1.json.gz"
