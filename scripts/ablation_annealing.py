"""Optimiser ablation (charter 3.5): does annealing beat a greedy pick with the same value model?

    python3 scripts/ablation_annealing.py [--out out] [--json FILE] [--timing SEEDS]

Reads only what the league already produced, and runs nothing:
  paired matches  out/cache/results.sqlite, current engine version and rules hash only. Each
                  pair is the same attacker on the same seed against annealed_assignment and
                  against greedy_value_model; the two bots differ only in the search
                  (tests/test_annealed.py enforces the shared value model).
  ladder series   out/history/<night>/leaderboard.json: Elo, mean score, mean CER and rank.

The interval on the mean paired difference is a bootstrap over attackers (resampling whole
attackers, not single matches, because the ten seeds against one attacker aren't
independent), with a fixed seed, so the output is deterministic.

--timing N plays N seeds of each of the three defenders against every paired attacker, both
bots in the sandbox as always, and times each defender act() round trip on the host: what
the league actually pays per tick. The three defenders' matches are interleaved in one pool,
so machine load hits all of them alike. Run it when the nightly league isn't running. Alongside it, an exact sign
test on which bot is ahead per attacker (a difference within 0.005 counts as level). Prints
JSON.
"""
import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colosseum.cache import engine_version, rules_hash   # noqa: E402
from colosseum.rules import SEASON0                      # noqa: E402

OPT, GREEDY, EAGER = "annealed_assignment", "greedy_value_model", "annealed_assignment_eager"
BOTS = (OPT, GREEDY, EAGER)
BOOT = 10_000


def paired(db: Path):
    """{attacker: {seed: {defender: meta}}} for the three bots, current engine and rules."""
    tail = f":{rules_hash(SEASON0)}:{engine_version()}"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("SELECT key, attacker, defender, seed, meta FROM results "
                       "WHERE defender IN (?, ?, ?)", BOTS).fetchall()
    con.close()
    out = defaultdict(lambda: defaultdict(dict))
    for key, att, dfn, seed, meta in rows:
        if key.endswith(tail):
            out[att][seed][dfn] = json.loads(meta)
    return out


def bootstrap_ci(per_attacker: list, n: int = BOOT, seed: int = 0):
    rng = random.Random(seed)
    k = len(per_attacker)
    means = sorted(sum(rng.choice(per_attacker) for _ in range(k)) / k for _ in range(n))
    return round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)


def sign_test(ahead: int, behind: int) -> float:
    """Exact two-sided sign test (ties dropped): the chance of a split this lopsided or more
    if each attacker were a coin flip between the two bots."""
    from math import comb
    n, k = ahead + behind, min(ahead, behind)
    if n == 0:
        return 1.0
    return round(min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n), 4)


def analyse(out: Path):
    data = paired(out / "cache" / "results.sqlite")
    per_att = {}
    for att, seeds in sorted(data.items()):
        both = [s for s in seeds.values() if OPT in s and GREEDY in s]
        if not both:
            continue
        d = [s[OPT]["score_defender"] - s[GREEDY]["score_defender"] for s in both]
        per_att[att] = dict(
            seeds=len(both), diff=round(sum(d) / len(d), 4),
            opt=round(sum(s[OPT]["score_defender"] for s in both) / len(both), 4),
            greedy=round(sum(s[GREEDY]["score_defender"] for s in both) / len(both), 4),
            opt_cer=round(sum(s[OPT]["cost_exchange_ratio"] for s in both) / len(both), 4),
            greedy_cer=round(sum(s[GREEDY]["cost_exchange_ratio"] for s in both) / len(both), 4),
            opt_breached=sum(s[OPT]["outcome"] != "defended" for s in both),
            greedy_breached=sum(s[GREEDY]["outcome"] != "defended" for s in both))
    diffs = [v["diff"] for v in per_att.values()]
    summary = dict(
        attackers=len(diffs), pairs=sum(v["seeds"] for v in per_att.values()),
        mean_diff=round(sum(diffs) / len(diffs), 4) if diffs else None,
        ci95=bootstrap_ci(diffs) if diffs else None,
        opt_ahead=sum(x > 0.005 for x in diffs), greedy_ahead=sum(x < -0.005 for x in diffs),
        level=sum(abs(x) <= 0.005 for x in diffs))
    summary["sign_p"] = sign_test(summary["opt_ahead"], summary["greedy_ahead"])
    nights = []
    for night in sorted(p for p in (out / "history").iterdir() if p.is_dir()):
        lb = json.loads((night / "leaderboard.json").read_text())
        ranks = {r["name"]: i + 1 for i, r in enumerate(lb["defenders"])}
        row = dict(night=night.name, defenders=len(lb["defenders"]))
        for r in lb["defenders"]:
            if r["name"] in BOTS:
                row[r["name"]] = dict(elo=r["elo"], score=r["mean_score"], cer=r["mean_cer"],
                                      rank=ranks[r["name"]])
        nights.append(row)
    return dict(summary=summary, per_attacker=per_att, nights=nights,
                engine=engine_version(), rules=rules_hash(SEASON0))


def _time_one(job):
    import time
    from colosseum.sandbox import SandboxedPolicy, SandboxLimits
    from colosseum.sim import Match
    attacker, defender, seed = job
    times = []

    class Timed(SandboxedPolicy):
        def act(self, obs):
            t0 = time.perf_counter()
            try:
                return super().act(obs)
            finally:
                times.append((time.perf_counter() - t0) * 1000)

    lim = SandboxLimits()
    a = SandboxedPolicy(str(attacker), "attacker", lim)
    try:
        d = Timed(str(defender), "defender", lim)
        try:
            Match(a, d, seed, rules=SEASON0, record=False).run()
        finally:
            d.close()
    finally:
        a.close()
    return Path(defender).stem, times


def timing(attackers, seeds: int, workers: int = 4):
    from concurrent.futures import ProcessPoolExecutor
    files = {}
    for name in attackers:
        for folder in ("bots/attackers", "bots/house"):
            if (ROOT / folder / f"{name}.py").exists():
                files[name] = ROOT / folder / f"{name}.py"
    jobs = [(files[a], ROOT / "bots" / "defenders" / f"{d}.py", s)
            for s in range(seeds) for a in sorted(files) for d in BOTS]
    per = defaultdict(list)
    with ProcessPoolExecutor(workers) as pool:
        for name, times in pool.map(_time_one, jobs):
            per[name] += times
    def q(xs, f):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(f * len(xs)))], 3)
    return {name: dict(ticks=len(t), median_ms=q(t, 0.5), p99_ms=q(t, 0.99),
                       max_ms=round(max(t), 3)) for name, t in sorted(per.items())}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--timing", type=int, default=0, metavar="SEEDS")
    a = ap.parse_args()
    res = analyse(a.out)
    if a.timing:
        res["timing"] = timing(list(res["per_attacker"]), a.timing)
    text = json.dumps(res, indent=1, sort_keys=True)
    if a.json:
        a.json.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
