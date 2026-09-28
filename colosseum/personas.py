"""House-league personas: who writes tonight's bot, what evidence it sees, and what it must beat.

A persona is defined by two things and nothing else: the evidence put in front of the
model, and the bot (or field) the new bot is judged against. Four of them:

  exploiter     standings, matrix, the most lopsided pairings with replays.
                Must beat: the opposing bot with the single worst result in the matrix.
  counter_meta  the opposing #1's full source, its matrix row, replays of its best
                pairings and of its closest calls.
                Must beat: the opposing #1.
  generalist    the full matrix and every opposing bot's docstring.
                Must beat: the field -- judged on mean score across all opponents.
  contrarian    the docstrings of every bot in its own role, as approaches to avoid.
                Must beat: the opposing #1, with an idea none of those bots use.

Choice, per role, logged and stored in the bot's metadata:
  1. HOUSE_LEAGUE_PERSONAS="attacker=counter_meta,defender=generalist" overrides.
  2. If the opposing #1 wins >= 90% of its matches, counter_meta: a dominant bot gets
     answered before anything else happens.
  3. Otherwise rotate exploiter -> generalist -> contrarian by night number (the defender
     is offset by one so the two bots of a night differ).

Host safety: other bots' source is read as text and pasted into the prompt. Nothing here
imports or executes a bot.
"""
import ast
import json
from pathlib import Path

from .tournament import ROOT

PERSONAS = ("exploiter", "counter_meta", "generalist", "contrarian")
ROTATION = ("exploiter", "generalist", "contrarian")
DOMINANT_WIN_RATE = 0.90
# house/RETIRED last: retirement runs after the tournament, so the leaderboard a night reads
# can still list a bot that was retired at the end of the previous night.
BOT_DIRS = ("attackers", "defenders", "house", "house/RETIRED")


def opposing(role):
    return "defender" if role == "attacker" else "attacker"


def bot_path(name: str) -> Path:
    for d in BOT_DIRS:
        p = ROOT / "bots" / d / f"{name}.py"
        if p.exists():
            return p
    raise FileNotFoundError(f"no bot named {name}")


def docstring(path: Path) -> str:
    try:
        return ast.get_docstring(ast.parse(path.read_text())) or "(no docstring)"
    except SyntaxError:
        return "(unparseable)"


def score_for(role, a, d, matrix):
    """Mean score from `role`'s point of view in pairing (a, d)."""
    s = matrix[a][d]
    return 1.0 - s if role == "attacker" else s


# --- targets --------------------------------------------------------------------

def target_for(persona, role, ctx):
    lb, matrix = ctx["leaderboard"], ctx["matrix"]
    if persona in ("counter_meta", "contrarian"):
        return lb[opposing(role) + "s"][0]["name"]
    if persona == "generalist":
        return "field"
    # exploiter: the opponent with the single worst result anywhere in the matrix
    if role == "attacker":
        worst = {d: min(matrix[a][d] for a in matrix) for d in next(iter(matrix.values()))}
        return min(worst, key=worst.get)
    worst = {a: max(matrix[a].values()) for a in matrix}       # high = defenders do well
    return max(worst, key=worst.get)


def choose(role, ctx, nights: int, override: str = "") -> str:
    wanted = dict(kv.strip().split("=", 1) for kv in override.split(",") if "=" in kv)
    if wanted.get(role):
        if wanted[role] not in PERSONAS:
            raise ValueError(f"unknown persona {wanted[role]!r}; choose from {PERSONAS}")
        return wanted[role]
    top = ctx["leaderboard"][opposing(role) + "s"][0]
    if top["win_rate"] >= DOMINANT_WIN_RATE:
        return "counter_meta"
    return ROTATION[(nights + (1 if role == "defender" else 0)) % len(ROTATION)]


# --- evidence -------------------------------------------------------------------

def replay_summary(out: Path, a: str, d: str, seed: int):
    p = out / "replays" / f"{a}__{d}__s{seed}.json"
    if not p.exists():
        return None
    rep = json.loads(p.read_text())
    m = rep["meta"]
    kills, impacts = {}, []
    for e in rep.get("events", []):
        if e["kind"] == "kill":
            k = f"{e['dtype']}_by_{e['by']}"
            kills[k] = kills.get(k, 0) + 1
        elif e["kind"] == "impact":
            impacts.append([e["t"], e["dtype"]])
    return dict(attacker=a, defender=d, seed=seed, outcome=m["outcome"],
                score_defender=m["score_defender"], asset_hp=m["asset_hp"], ticks=m["ticks"],
                drones_launched=m["drones_launched"], kills=kills,
                impacts_tick_type=impacts, interceptors_launched=m["interceptors_launched"],
                stock_left=m["stock_left"], shots_fired=m["shots_fired"],
                ammo_left=m["ammo_left"], cost_exchange_ratio=m["cost_exchange_ratio"])


def target_replays(out: Path, target: str, target_role: str, matrix, seeds=10, k=3):
    """The target's best pairings (seed 0 each) and its closest calls (any seed)."""
    if target_role == "defender":
        pairs = [(a, target) for a in matrix]
    else:
        pairs = [(target, d) for d in matrix[target]]
    best = sorted(pairs, key=lambda p: -score_for(target_role, p[0], p[1], matrix))[:k]
    runs = [replay_summary(out, a, d, s) for a, d in pairs for s in range(seeds)]
    runs = [r for r in runs if r]
    if target_role == "defender":
        closest = sorted(runs, key=lambda r: r["score_defender"])[:k]
    else:
        closest = sorted(runs, key=lambda r: -r["score_defender"])[:k]
    return dict(best_pairings=[r for a, d in best if (r := replay_summary(out, a, d, 0))],
                closest_calls=closest)


def standings(lb):
    def fmt(r):
        return (f"  {r['name']}: elo {r['elo']:.0f}, win rate {r['win_rate']:.0%}, "
                f"mean CER {r['mean_cer']}")
    return ("Attackers:\n" + "\n".join(map(fmt, lb["attackers"]))
            + "\n\nDefenders:\n" + "\n".join(map(fmt, lb["defenders"])))


def evidence(persona, role, target, ctx, out: Path) -> str:
    lb, matrix = ctx["leaderboard"], ctx["matrix"]
    base = f"## Current standings\n\n{standings(lb)}\n"
    if persona == "exploiter":
        return base + f"""
## Mean score_defender per pairing (high = defender did well)

{json.dumps(matrix, indent=2)}

## The most lopsided pairings, with one match each

{json.dumps(ctx['lopsided'], indent=2)}
"""
    if persona == "counter_meta":
        trole = opposing(role)
        row = {a: matrix[a][target] for a in matrix} if trole == "defender" else matrix[target]
        reps = target_replays(out, target, trole, matrix)
        return base + f"""
## The bot you must beat: {target} ({trole})

Its full source:

```python
{bot_path(target).read_text()}
```

Its mean score_defender against each opponent (high = defender did well):

{json.dumps(row, indent=2)}

Its best pairings, one match each:

{json.dumps(reps['best_pairings'], indent=2)}

Its closest calls -- the matches where it came nearest to losing:

{json.dumps(reps['closest_calls'], indent=2)}
"""
    if persona == "generalist":
        docs = "\n\n".join(f"### {r['name']}\n{docstring(bot_path(r['name']))}"
                           for r in lb[opposing(role) + "s"])
        return base + f"""
## Mean score_defender per pairing (high = defender did well)

{json.dumps(matrix, indent=2)}

## Every {opposing(role)} you will face, by its own description

{docs}
"""
    if persona == "contrarian":
        docs = "\n\n".join(f"### {r['name']}\n{docstring(bot_path(r['name']))}"
                           for r in lb[role + "s"])
        return base + f"""
## Every existing {role}, by its own description -- approaches you must NOT reuse

{docs}
"""
    raise ValueError(f"unknown persona {persona!r}")


def task(persona, role, target) -> str:
    article = "an" if role == "attacker" else "a"
    one = (f"Write exactly ONE bot: {article} {role}. Return exactly one fenced Python code "
           "block and nothing else.")
    goal = {
        "exploiter": f"It must beat {target}, the {opposing(role)} with the single worst "
                     "result in the matrix. The docstring must name the weakness and the "
                     "pairing that shows it.",
        "counter_meta": f"It must beat {target}, the current #1 {opposing(role)}, "
                        "specifically. You have its source: find what it cannot handle. "
                        "The docstring must say which part of its logic you are attacking "
                        "and what in the replays shows that is where it breaks.",
        "generalist": f"It must do well against the whole field of {opposing(role)}s, "
                      "judged on mean score across all of them, not by beating one. The "
                      "docstring must say why the approach holds up against every opponent "
                      "described above.",
        "contrarian": f"It must beat {target}, the current #1 {opposing(role)}, with a "
                      f"core idea that none of the existing {role}s described above use. "
                      "The docstring must name the idea and say how it differs from each.",
    }[persona]
    return f"## Your task\n\n{one}\n\n{goal}\n"
