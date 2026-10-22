"""House-league personas: who writes tonight's bot, what evidence it sees, and what it must beat.

A persona is defined by two things and nothing else: the evidence put in front of the
model, and the bot (or field) the new bot is judged against. Four of them:

  exploiter     standings, matrix, the most lopsided pairings with replays.
                Must beat: the opposing bot with the single worst result in the matrix.
  counter_meta  the opposing #1's full source, its matrix row, replays of its best
                pairings and of its closest calls.
                Must beat: the opposing #1. No threshold: it always targets the current #1.
  generalist    the full matrix and every opposing bot's docstring.
                Must beat: the field -- judged on mean score across all opponents.
  contrarian    the docstrings of every bot in its own role, as approaches to avoid.
                Must beat: the opposing #1, with an idea none of those bots use.

A night's plan (plan_night), logged and stored in each bot's metadata:
  1. Escalation: a bot unbeaten by every opponent on each of the last two nights (every
     opponent's mean score against it below 0.5) gets both of the night's slots -- two
     counter_meta bots for the opposite side, aimed at it. (Only one side can have one:
     an attacker that beats every defender rules out a defender that beats every attacker.)
     Escalation stops after 3 straight nights with no bot beating the target (stalled).
  2. HOUSE_LEAGUE_PERSONAS="attacker=counter_meta,defender=generalist" overrides.
  3. Otherwise one attacker and one defender, rotating through all four personas by night
     number (the defender offset by one so the two bots of a night differ).

All prompt wording lives in colosseum/prompts/generator.py; this module supplies the data.
Host safety: other bots' source is read as text and pasted into the prompt. Nothing here
imports or executes a bot.
"""
import ast
import json
from pathlib import Path

from .prompts import generator as P
from .tournament import ROOT

PERSONAS = ("exploiter", "counter_meta", "generalist", "contrarian")
ROTATION = PERSONAS
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
    return ROTATION[(nights + (1 if role == "defender" else 0)) % len(ROTATION)]


def unbeaten(matrix: dict):
    """{role: [names]} of bots no opponent beat on this night's matrix (mean < 0.5)."""
    attackers = sorted(matrix)
    defenders = sorted({d for row in matrix.values() for d in row})
    return dict(
        attacker=[a for a in attackers if all(matrix[a][d] < 0.5 for d in matrix[a])],
        defender=[d for d in defenders if all(matrix[a][d] > 0.5 for a in attackers
                                              if d in matrix[a])])


def escalation(last_two):
    """Bots unbeaten on both of the last two nights' matrices: {role: name}."""
    if len(last_two) < 2:
        return {}
    first, second = (unbeaten(m) for m in last_two)
    found = {}
    for role in ("attacker", "defender"):
        both = [n for n in second[role] if n in first[role]]
        if both:
            found[role] = both[0]
    return found


def stalled(recent_nights, target, n=3):
    """True if each of the last `n` ledger records aimed every house bot at `target`
    and none of them beat it."""
    recent = list(recent_nights)[-n:]
    return len(recent) == n and all(
        (r.get("house_positions") or {}) and all(
            p.get("target") == target and not p.get("beat_target")
            for p in r["house_positions"].values())
        for r in recent)


def plan_night(ctx, nights: int, last_two_matrices=(), override: str = "",
               slots: int = 2, recent_nights=()):
    """[(role, persona, target, note)] for tonight. note is "" or "escalation"."""
    esc = escalation(list(last_two_matrices))
    if esc and not override and not stalled(recent_nights, next(iter(esc.values()))):
        # At most one side can have an unbeaten bot: if an attacker beats every defender,
        # no defender beats every attacker on the same matrix.
        (bot_role, bot), = esc.items()
        return [(opposing(bot_role), "counter_meta", bot, "escalation")] * min(2, slots)
    plan = []
    for role in ["attacker", "defender"][:max(1, min(2, slots))]:
        persona = choose(role, ctx, nights, override)
        plan.append((role, persona, target_for(persona, role, ctx), ""))
    return plan


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


TOP_STANDINGS = 5


def standings(lb, keep=()):
    """Top TOP_STANDINGS per side, plus any bot named in `keep` (the target)."""
    def fmt(r):
        return (f"  {r['name']}: elo {r['elo']:.0f}, win rate {r['win_rate']:.0%}, "
                f"mean CER {r['mean_cer']}")

    def side(rows):
        shown = [r for i, r in enumerate(rows) if i < TOP_STANDINGS or r["name"] in keep]
        more = len(rows) - len(shown)
        return "\n".join(map(fmt, shown)) + (f"\n  ... and {more} more" if more else "")
    return "Attackers:\n" + side(lb["attackers"]) + "\n\nDefenders:\n" + side(lb["defenders"])


def est_tokens(text: str) -> int:
    """Same deliberately crude estimate the league's pre-call cap uses (3.5 chars/token)."""
    return int(len(text) / 3.5) + 1


def _item(name, persona, role, target, ctx, out):
    lb, matrix = ctx["leaderboard"], ctx["matrix"]
    trole = opposing(role)
    if name == "source":
        return P.ITEMS["source"].substitute(target=target, target_role=trole,
                                            source=bot_path(target).read_text())
    if name == "closest":
        reps = target_replays(out, target, trole, matrix, k=2)
        return P.ITEMS["closest"].substitute(closest=json.dumps(reps["closest_calls"]))
    if name == "row":
        row = {a: matrix[a][target] for a in matrix} if trole == "defender" else matrix[target]
        return P.ITEMS["row"].substitute(row=json.dumps({k: round(v, 2) for k, v in row.items()}))
    if name == "lopsided":
        if role == "attacker":                    # the target defender's worst pairing
            a = min(matrix, key=lambda x: matrix[x][target])
            d = target
        else:                                     # the target attacker's best pairing
            a = target
            d = min(matrix[target], key=lambda x: matrix[target][x])
        rep = replay_summary(out, a, d, 0)
        return P.ITEMS["lopsided"].substitute(attacker=a, defender=d,
                                              score=round(matrix[a][d], 3),
                                              match=json.dumps(rep))
    if name == "target_doc":
        return P.ITEMS["target_doc"].substitute(target=target, doc=docstring(bot_path(target)))
    if name == "matrix":
        compact = {a: {d: round(v, 2) for d, v in row.items()} for a, row in matrix.items()}
        return P.ITEMS["matrix"].substitute(matrix=json.dumps(compact))
    if name == "top_three":
        def head(name, n=600):            # the Idea line and the gist, not the essay
            d = docstring(bot_path(name))
            return d if len(d) <= n else d[:n].rsplit(" ", 1)[0] + " ..."
        docs = "\n\n".join(f"### {r['name']}\n{head(r['name'])}"
                            for r in lb[trole + "s"][:3])
        return P.ITEMS["top_three"].substitute(opponent_role=trole, docs=docs)
    raise ValueError(f"unknown evidence item {name!r}")


def evidence_with_budget(persona, role, target, ctx, out: Path):
    """(text, info). Items go in, most informative first, until the persona's budget is used.
    The first item always goes in, cut at the budget if it has to be."""
    budget, order = P.BUDGETS[persona]
    keep = () if target == "field" else (target,)
    parts = [P.STANDINGS.substitute(standings=standings(ctx["leaderboard"], keep))]
    used, included, dropped = 0, [], []
    for name in order:
        if target == "field" and name in ("source", "closest", "row", "target_doc"):
            continue
        text = _item(name, persona, role, target, ctx, out)
        cost = est_tokens(text)
        if used + cost <= budget:
            parts.append(text)
            used += cost
            included.append(name)
        elif not included:
            cut = int((budget - used) * 3.5)
            parts.append(text[:cut] + "\n[... cut to fit the evidence budget]\n")
            used = budget
            included.append(name + " (cut)")
        else:
            dropped.append(name)
    return "".join(parts), dict(budget=budget, used=used, included=included, dropped=dropped)


def evidence(persona, role, target, ctx, out: Path) -> str:
    return evidence_with_budget(persona, role, target, ctx, out)[0]


def task(persona, role, target, second_of_two=False) -> str:
    fill = dict(article="an" if role == "attacker" else "a", role=role, target=target,
                opponent_role=opposing(role))
    extra = P.SECOND_OF_TWO.substitute(target=target) if second_of_two else ""
    return P.TASK.substitute(one=P.ONE_BOT.substitute(fill),
                             goal=P.GOALS[persona].substitute(fill),
                             idea=P.IDEA_LINE, extra=extra)
