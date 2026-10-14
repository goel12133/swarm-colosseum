"""Persona ablation (charter 3.4, sprint L3): persona mix vs all-generalist, same evidence.

    python3 scripts/ablation_personas.py --nights 2026-09-29 2026-09-30 ... --out out/ablation

Run it on a scratch copy of the repo; it calls the league's generator once per slot.

Arm P (persona) = the house bots the league actually wrote on those nights.
Arm G (generalist) = for every slot the real league filled on those nights (same role, both
escalation slots included), a bot written by the generalist persona from that night's real
evidence snapshot (out/history/<previous night>/), through the league's own code path:
the same prompt builder, the same CLI backend, ast validation and a sandbox smoke test.

Both arms are added to the same base (baselines + house bots from before the first night)
and played in their own sandboxed tournament. Compared: unique coverage, top-five entries,
mean score against the field, and how many generator calls produced a bot. Retirement needs
three bottom nights per bot and can't be measured on an early cut.
"""
import argparse
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colosseum import house_league as hl          # noqa: E402
from colosseum.tournament import _role_of, discover, run_tournament   # noqa: E402

HOUSE = ROOT / "bots" / "house"


def real_bots(night):
    return sorted(p for p in HOUSE.glob(f"{night}_*.py"))


def slots(night):
    """The roles the real league filled that night: written bots plus rejected slots."""
    roles = [_role_of(p) for p in real_bots(night)]
    for line in (ROOT / "out" / "nights.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["date"] == night:
            roles += [r for r, _ in (rec.get("rejected") or [])]
    return roles


def evidence_dir(night, scratch):
    """A gather_context()-shaped directory from the previous night's real snapshot."""
    prev = (date.fromisoformat(night) - timedelta(days=1)).isoformat()
    src = ROOT / "out" / "history" / prev
    d = scratch / "evidence" / night
    d.mkdir(parents=True, exist_ok=True)
    for f in ("leaderboard.json", "matrix.json"):
        shutil.copy(src / f, d / f)
    (d / "BALANCE.md").write_text("")
    return d


class OutOfBudget(Exception):
    pass


def generate(nights, scratch, max_tokens=None):
    """Resumable: slots already in generation.json are skipped. With max_tokens, a call is
    made only if the league's own conservative projection for it still fits; otherwise the
    run stops cleanly (OutOfBudget) and the next session continues."""
    arm = scratch / "arm_generalist"
    arm.mkdir(parents=True, exist_ok=True)
    log_path = scratch / "generation.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    done = {(r["night"], r["slot"]) for r in log if "slot" in r}
    caps = hl.Caps.from_env({})
    spent = 0
    for night in nights:
        ctx = hl.gather_context(evidence_dir(night, scratch), n_replays=0)
        for i, role in enumerate(slots(night)):
            if (night, i) in done:
                continue
            prompt = hl.build_prompt(ctx, role, "generalist", "field", ROOT / "out")
            projected = hl.estimate_input_tokens(prompt, "cli") + hl.MAX_OUTPUT_TOKENS
            if max_tokens is not None and spent + projected > max_tokens:
                log_path.write_text(json.dumps(log, indent=2))
                raise OutOfBudget(f"stopped before {night} slot {i}: {spent:,} spent, "
                                  f"{projected:,} projected, budget {max_tokens:,}")
            spend = hl.Spend()
            row = dict(night=night, slot=i, role=role,
                       day=date.today().isoformat())
            try:
                text = hl.call_model(prompt, caps, spend, dry_run=False)
            except Exception as exc:
                row.update(status="no response", detail=f"{type(exc).__name__}: {exc}"[:200])
                log.append(row)
                log_path.write_text(json.dumps(log, indent=2))
                print(json.dumps(row), flush=True)
                continue
            row["tokens"] = spend.tokens
            spent += spend.tokens
            blocks = hl.extract_bots(text)
            ok, name, reason = hl.validate_bot(blocks[0], role) if blocks else \
                (False, "", "no code block")
            if not ok:
                row.update(status="rejected", detail=reason)
                log.append(row)
                log_path.write_text(json.dumps(log, indent=2))
                print(json.dumps(row), flush=True)
                continue
            path = arm / f"{night}_g{i}_{role}_{hl.slug(name)}.py"
            path.write_text(blocks[0] + "\n")
            ok, detail = hl.smoke_test(path, role)
            if not ok:
                path.unlink()
                row.update(status="smoke failed", detail=detail)
            else:
                row.update(status="written", bot=path.stem)
            log.append(row)
            log_path.write_text(json.dumps(log, indent=2))
            print(json.dumps(row), flush=True)
    log_path.write_text(json.dumps(log, indent=2))
    return log


def strict_unique(b, name, role, k):
    """Opponents only `name` beats in at least k of the seeds (breach / hold)."""
    bb, seeds = b["breaches"], b["seeds"]
    A = sorted(bb)
    D = sorted({d for r in bb.values() for d in r})
    if role == "attacker":
        cov = lambda a, d: bb[a].get(d, 0) >= k                               # noqa: E731
        return [d for d in D if cov(name, d) and not any(cov(a, d) for a in A if a != name)]
    hold = lambda d, a: seeds - bb[a].get(d, seeds) >= k                      # noqa: E731
    return [a for a in A if hold(name, a) and not any(hold(d, a) for d in D if d != name)]


def retired_share(nights):
    """Of the persona arm's bots, how many the real league has retired so far."""
    retired = {p.stem for p in (HOUSE / "RETIRED").glob("*.py")}
    bots = [p.stem for n in nights for p in [*HOUSE.glob(f"{n}_*.py"),
                                             *(HOUSE / "RETIRED").glob(f"{n}_*.py")]]
    return sum(1 for b in bots if b in retired), len(bots)


def render(result: dict) -> str:
    """The page, from result.json only: a table and the standing caveats. No narrative is
    generated; the early cut's narrative stays in git history. The status word the site
    looks for (site.paper_info) must not appear near the top: this is the final run."""
    p, g, n = result["persona"], result["generalist"], result["nights"]
    rr, rn = result.get("retired_persona", (0, 0))
    return f"""# 03 · Does persona diversity help? ({len(n)}-night run)

*Generated automatically from `out/ablation_14/result.json` after real night 14. Nights
{n[0]} to {n[-1]} (every persona night among the league's first 14), {result['slots']}
generator slots per arm, 10 seeds per pairing. The five-night early cut, with its worked
example, is in this file's git history.*

**Bottom line:** persona mix vs all-generalist: mean score {p['mean_score']} vs
{g['mean_score']}, top-five places {len(p['top_five'])} vs {len(g['top_five'])}, unique
coverage held in at least 8 of 10 seeds {p['unique_coverage_8']} vs {g['unique_coverage_8']}.

**The test.** Every slot the real league filled was refilled by the *generalist* persona
from the same evidence snapshot, through the same generator, validation and sandbox smoke
test. Both arms were added to the same base field and played full sandboxed tournaments.
Reproduce with `scripts/ablation_personas.py`.

| | persona mix (what the league wrote) | all-generalist |
|---|---|---|
| bots written / generator calls | {result['real_league']['written']} / {result['real_league']['slots']} | {result['generation']['written']} / {result['generation']['calls']} |
| mean score of the arm's bots | {p['mean_score']} | {g['mean_score']} |
| places in the two top fives | {len(p['top_five'])} | {len(g['top_five'])} |
| unique coverage, ≥ 1 of 10 seeds | {p['unique_coverage']} | {g['unique_coverage']} |
| unique coverage, ≥ 5 of 10 seeds | {p['unique_coverage_5']} | {g['unique_coverage_5']} |
| unique coverage, ≥ 8 of 10 seeds | {p['unique_coverage_8']} | {g['unique_coverage_8']} |
| retired by the real league so far | {rr} of {rn} | not simulated |

**Caveats that always apply.** The generalist's evidence includes the top three opponents'
self-descriptions, which after the first night include bots the persona mix wrote, so the
arms are not fully independent. The generalist arm is played against the base field once,
not run night by night, so its retirement can't be measured. Coverage differences of one or
two opponents are within what a single bot changes.

---

The arena is an abstract strategy game with made-up units (`u`, ticks, credits).
"""


def evaluate(arm_bots, base, out):
    atts = sorted(base[0] + [p for p in arm_bots if _role_of(p) == "attacker"])
    defs = sorted(base[1] + [p for p in arm_bots if _role_of(p) == "defender"])
    lb, _, _ = run_tournament(seeds=10, out=out, sandbox=True, quiet=True,
                              roster=(atts, defs))
    b = json.loads((out / "breaches.json").read_text())
    mine = {p.stem for p in arm_bots}
    unique = {p.stem: hl.unique_coverage(p.stem, _role_of(p), b) for p in arm_bots}
    strict = {k: sum(len(strict_unique(b, p.stem, _role_of(p), k)) for p in arm_bots)
              for k in (5, 8)}
    top5 = [r["name"] for role in ("attackers", "defenders") for r in lb[role][:5]
            if r["name"] in mine]
    scores = [r["mean_score"] for role in ("attackers", "defenders") for r in lb[role]
              if r["name"] in mine]
    return dict(bots=len(mine), unique_coverage=sum(len(v) for v in unique.values()),
                unique_coverage_5=strict[5], unique_coverage_8=strict[8],
                bots_with_unique=sum(1 for v in unique.values() if v),
                unique_detail={k: v for k, v in unique.items() if v},
                top_five=top5,
                mean_score=round(sum(scores) / len(scores), 3) if scores else None,
                number_ones=[lb["attackers"][0]["name"], lb["defenders"][0]["name"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nights", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "ablation")
    ap.add_argument("--render", type=Path, default=None,
                    help="write the research page from the result to this path")
    ap.add_argument("--commit", action="store_true", help="git-commit the rendered page")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="stop cleanly (exit 3) before a call that could exceed this")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    first = min(args.nights)
    base_house = [p for p in HOUSE.glob("*.py") if p.name[:10] < first]
    base = ([*discover(ROOT / "bots" / "attackers"),
             *[p for p in base_house if _role_of(p) == "attacker"]],
            [*discover(ROOT / "bots" / "defenders"),
             *[p for p in base_house if _role_of(p) == "defender"]])
    try:
        log = generate(args.nights, args.out, args.max_tokens)
    except OutOfBudget as exc:
        print(f"PARTIAL: {exc}")
        return 3
    persona_bots = [p for n in args.nights for p in real_bots(n)]
    generalist_bots = sorted((args.out / "arm_generalist").glob("*.py"))
    result = dict(
        nights=args.nights,
        slots=sum(len(slots(n)) for n in args.nights),
        persona=evaluate(persona_bots, base, args.out / "t_persona"),
        generalist=evaluate(generalist_bots, base, args.out / "t_generalist"),
        generation=dict(calls=len(log), written=sum(r["status"] == "written" for r in log),
                        outcomes=[r["status"] for r in log],
                        tokens=sum(r.get("tokens") or 0 for r in log)),
        real_league=dict(slots=sum(len(slots(n)) for n in args.nights),
                         written=len(persona_bots)),
    )
    result["retired_persona"] = retired_share(args.nights)
    (args.out / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if args.render:
        args.render.write_text(render(result))
        if args.commit:
            import subprocess
            rel = str(args.render.relative_to(ROOT))
            subprocess.run(["git", "-C", str(ROOT), "add", "--", rel], check=True)
            subprocess.run(["git", "-C", str(ROOT), "-c", "user.name=Swarm Colosseum league",
                            "-c", "user.email=league@localhost", "commit", "-q", "-m",
                            f"research/03: {len(args.nights)}-night persona ablation "
                            "(generated)", "--", rel], check=True)


if __name__ == "__main__":
    sys.exit(main())
