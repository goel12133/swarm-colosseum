"""Round robin: every attacker against every defender, on every seed.

    python -m colosseum.tournament                 # seeds 0..9
    python -m colosseum.tournament --seeds 2       # quick

Match order is fixed (attacker, defender, seed, all sorted) so the Elo ladders are
reproducible -- Elo is path dependent, and an unordered run would give a different ladder
from the same matches.

Writes out/leaderboard.json, out/matrix.json, out/replays/ and out/BALANCE.md.
"""
import argparse
import json
import sys
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .elo import Ladders
from .rules import SEASON0
from .sim import replay_json, run_match

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "out"


# House bots, plus outside submissions (bots/submitted/<side>/). RETIRED/ is not searched.
UNTRUSTED_FOLDERS = [ROOT / "bots" / "house", ROOT / "bots" / "submitted" / "attacker",
                     ROOT / "bots" / "submitted" / "defender"]


def untrusted_bots():
    return [p for folder in UNTRUSTED_FOLDERS for p in discover(folder)]


def discover(folder: Path):
    return sorted(p for p in folder.glob("*.py") if not p.name.startswith("_"))


def _role_of(path: Path) -> str:
    """Read ROLE out of a bot file without executing it.

    House bots are untrusted, so the host reads the text and never imports them; the only
    place they run is inside a container.
    """
    import re
    m = re.search(r'^ROLE\s*=\s*["\'](attacker|defender)["\']',
                  path.read_text(errors="replace"), re.M)
    return m.group(1) if m else ""


def default_workers() -> int:
    """One fewer than the cores, so the box stays usable while a tournament runs."""
    return max(1, (os.cpu_count() or 2) - 1)


def _match_job(job):
    """Runs in a worker process. Writes its own replay so only the meta crosses back."""
    a, d, seed, rules, record, sandbox, out = job
    res = run_match(a, d, seed, rules=rules, record=record, sandbox=sandbox)
    if record:
        name = f"{Path(a).stem}__{Path(d).stem}__s{seed}.json"
        (Path(out) / "replays" / name).write_text(replay_json(res))
    return res["meta"]


def run_tournament(seeds=10, out=DEFAULT_OUT, rules=SEASON0, write_replays=True,
                   quiet=False, sandbox=False, workers=None):
    attackers = discover(ROOT / "bots" / "attackers")
    defenders = discover(ROOT / "bots" / "defenders")
    untrusted = untrusted_bots()
    if untrusted and not sandbox:
        # Untrusted bots never run on the host. An in-process tournament is baselines only.
        print(f"in-process run: leaving out {len(untrusted)} untrusted bot(s); "
              "use --sandbox to include them", file=sys.stderr)
        untrusted = []
    for p in untrusted:
        role = _role_of(p)
        if role == "attacker":
            attackers.append(p)
        elif role == "defender":
            defenders.append(p)
    attackers, defenders = sorted(attackers), sorted(defenders)
    seed_list = list(range(seeds))
    workers = default_workers() if workers is None else max(1, int(workers))

    out = Path(out)
    (out / "replays").mkdir(parents=True, exist_ok=True)

    stats = defaultdict(lambda: dict(matches=0, score=0.0, wins=0, cer=0.0, cer_n=0))
    matrix = defaultdict(dict)
    pair_scores = defaultdict(list)
    ladders = Ladders([p.stem for p in attackers], [p.stem for p in defenders])
    results = []

    # The job list is built in sorted order and the RESULTS ARE CONSUMED IN THAT ORDER,
    # whatever order the workers finish in. Elo is path dependent, so consuming by
    # completion order would make the ladder depend on machine timing.
    jobs = [(str(a), str(d), seed, rules, write_replays, sandbox, str(out))
            for a in attackers for d in defenders for seed in seed_list]

    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            metas = list(ex.map(_match_job, jobs))     # map preserves input order
    else:
        metas = [_match_job(j) for j in jobs]

    for (a_s, d_s, seed, *_), meta in zip(jobs, metas):
        a_stem, d_stem = Path(a_s).stem, Path(d_s).stem
        results.append(meta)
        ladders.record(a_stem, d_stem, meta["score_attacker"])
        pair_scores[(a_stem, d_stem)].append(meta["score_defender"])

        sa, sd = stats[("attacker", a_stem)], stats[("defender", d_stem)]
        sa["matches"] += 1
        sd["matches"] += 1
        sa["score"] += meta["score_attacker"]
        sd["score"] += meta["score_defender"]
        sa["wins"] += 1 if meta["outcome"] == "breached" else 0
        sd["wins"] += 1 if meta["outcome"] == "defended" else 0
        if meta["defender_spent"] > 0:
            sd["cer"] += meta["cost_exchange_ratio"]
            sd["cer_n"] += 1
            sa["cer"] += meta["cost_exchange_ratio"]
            sa["cer_n"] += 1
        if not quiet:
            print(f"  {a_stem:<14} vs {d_stem:<22} s{seed}  "
                  f"{meta['outcome']:<9} hp={meta['asset_hp']:<3} "
                  f"cer={meta['cost_exchange_ratio']:.2f} "
                  f"score_def={meta['score_defender']:.3f}", flush=True)

    for (a, d), scores in pair_scores.items():
        matrix[a][d] = round(sum(scores) / len(scores), 4)

    def table(role, ratings):
        rows = []
        for name, rating in ratings.items():
            s = stats[(role, name)]
            rows.append(dict(
                name=name, role=role, elo=round(rating, 1),
                matches=s["matches"],
                mean_score=round(s["score"] / s["matches"], 4) if s["matches"] else 0.0,
                win_rate=round(s["wins"] / s["matches"], 4) if s["matches"] else 0.0,
                mean_cer=round(s["cer"] / s["cer_n"], 4) if s["cer_n"] else None))
        return sorted(rows, key=lambda r: -r["elo"])

    leaderboard = dict(
        season=0, seeds=seed_list, matches=len(results),
        attackers=table("attacker", ladders.attackers),
        defenders=table("defender", ladders.defenders),
        rules=rules.as_dict(),
    )
    (out / "leaderboard.json").write_text(json.dumps(leaderboard, indent=2, sort_keys=True))
    (out / "matrix.json").write_text(json.dumps(
        dict(note="mean score_defender for each attacker x defender pair",
             matrix={a: matrix[a] for a in sorted(matrix)}),
        indent=2, sort_keys=True))
    report = balance_report(leaderboard, matrix, results)
    findings = ROOT / "BALANCE.md"          # hand-written rules findings, committed
    if findings.exists():
        report += "\n---\n\n" + findings.read_text()
    (out / "BALANCE.md").write_text(report)
    return leaderboard, matrix, results


def balance_report(leaderboard, matrix, results) -> str:
    defended = sum(1 for m in results if m["outcome"] == "defended")
    n = len(results)
    lines = [f"# Balance read — season {leaderboard['season']}", "",
             f"{n} matches over seeds {leaderboard['seeds']}.", "",
             f"**Role split:** defenders held the asset in {defended}/{n} "
             f"({defended / n:.0%}), attackers breached it in {n - defended}/{n} "
             f"({(n - defended) / n:.0%}).", ""]

    flags = []
    if defended / n > 0.85:
        flags.append(f"defending role wins {defended / n:.0%} (> 85% threshold)")
    if (n - defended) / n > 0.85:
        flags.append(f"attacking role wins {(n - defended) / n:.0%} (> 85% threshold)")
    for row in leaderboard["attackers"] + leaderboard["defenders"]:
        if row["win_rate"] > 0.90:
            flags.append(f"{row['name']} ({row['role']}) wins {row['win_rate']:.0%} "
                         f"(> 90% threshold)")
    lines += ["**Threshold check:** " +
              ("no flags — strategy has room to matter." if not flags
               else "FLAGGED — " + "; ".join(flags)), ""]

    for role in ("attackers", "defenders"):
        lines += [f"## {role.capitalize()}", "",
                  "| bot | Elo | mean score | win rate | mean CER |", "|---|---|---|---|---|"]
        for row in leaderboard[role]:
            cer = "—" if row["mean_cer"] is None else f"{row['mean_cer']:.2f}"
            lines.append(f"| {row['name']} | {row['elo']:.0f} | {row['mean_score']:.3f} "
                         f"| {row['win_rate']:.0%} | {cer} |")
        lines.append("")

    lines += ["## Matrix (mean score_defender; high means the defender did well)", "",
              "| attacker \\ defender | " + " | ".join(sorted(next(iter(matrix.values()))))
              + " |",
              "|---" * (len(next(iter(matrix.values()))) + 1) + "|"]
    for a in sorted(matrix):
        lines.append(f"| {a} | " + " | ".join(f"{matrix[a][d]:.3f}"
                                              for d in sorted(matrix[a])) + " |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-replays", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--sandbox", action="store_true",
                    help="run every bot in its own container (see colosseum/sandbox.py)")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"parallel matches (default: cores - 1 = {default_workers()})")
    args = ap.parse_args()
    lb, _, results = run_tournament(seeds=args.seeds, out=args.out,
                                    write_replays=not args.no_replays, quiet=args.quiet,
                                    sandbox=args.sandbox, workers=args.workers)
    print(f"\n{len(results)} matches -> {args.out}")
    print(f"top attacker: {lb['attackers'][0]['name']} ({lb['attackers'][0]['elo']:.0f})")
    print(f"top defender: {lb['defenders'][0]['name']} ({lb['defenders'][0]['elo']:.0f})")


if __name__ == "__main__":
    main()
