"""Every word the house-league generator is shown, in one file.

Change this file and you change what the league produces, so every change gets a new
PROMPT_VERSION (recorded in each bot's .meta.json) and a line in PROGRESS.md.

The code that fills these in with data lives in colosseum/personas.py (evidence: standings,
matrices, replays, source) and colosseum/house_league.py (assembly and the model call).
Templates use string.Template ($name), so the JSON braces in the API text need no escaping.

History
  2026-09-28.1  first persona prompts (moved here verbatim from house_league.py/personas.py)
  2026-09-29.1  docstring must start with "Idea: <one sentence>" (quoted in the weekly
                report); second-of-two note for escalation nights
"""
from string import Template

PROMPT_VERSION = "2026-09-29.1"

SYSTEM = ("You write Python bot files for a game benchmark. Answer with exactly the "
          "fenced code blocks requested and nothing else.")

INTRO = """You are writing a bot for Swarm Colosseum, an abstract strategy benchmark on a
blank 2D plane with made-up units. It is a game, not a model of anything real.

A protected asset sits at the origin. An attacker launches cheap drones from a ring; a
defender has a limited magazine of interceptors, a short-range gun, and a radar that sees
position but only reveals a drone's type inside a close range. Everything is made-up units.
"""

API = """## The policy API

A bot is one Python file with module-level `NAME` (str), `ROLE` ("attacker" or
"defender"), `act(obs) -> dict`, and optionally `reset(seed)`. Standard library only.
It is loaded fresh for every match, so module state does not leak between matches.

Attacker obs: tick, budget, asset{pos,hp,radius}, drones[{id,type,pos,vel,waypoint}],
interceptors[[x,y]], rules.
Attacker action: {"launch": [{"type": "striker"|"decoy", "bearing": float}],
                  "steer": {drone_id: [x,y] or None}}
A drone flies to its waypoint if it has one, then heads for the asset.

Defender obs: tick, asset, tracks[{id,pos,vel,range,cls}] where cls is
"unknown"/"striker"/"decoy", interceptors[{id,target,pos,age}], stock, ammo, rules.
Defender action: {"intercept": [track_id], "retarget": {interceptor_id: track_id},
                  "gun": track_id or None}

Launch caps are per tick and enforced by the engine; exceeding them wastes the request.

Requirements:
- Standard library only. No file, network or subprocess access.
- Fast: `act` is called up to 600 times per match, with a per-tick timeout.
- Deterministic given the same observations. If you need randomness, seed it in `reset`.
- Do not raise. Return a well-formed action every tick.
"""

RULES = Template("## Current rules\n\n$rules\n")

STANDINGS = Template("## Current standings\n\n$standings\n")

EVIDENCE = {
    "exploiter": Template("""
## Mean score_defender per pairing (high = defender did well)

$matrix

## The most lopsided pairings, with one match each

$lopsided
"""),
    "counter_meta": Template("""
## The bot you must beat: $target ($target_role)

Its full source:

```python
$source
```

Its mean score_defender against each opponent (high = defender did well):

$row

Its best pairings, one match each:

$best

Its closest calls -- the matches where it came nearest to losing:

$closest
"""),
    "generalist": Template("""
## Mean score_defender per pairing (high = defender did well)

$matrix

## Every $opponent_role you will face, by its own description

$docs
"""),
    "contrarian": Template("""
## Every existing $role, by its own description -- approaches you must NOT reuse

$docs
"""),
}

ONE_BOT = Template("Write exactly ONE bot: $article $role. Return exactly one fenced Python "
                   "code block and nothing else.")

GOALS = {
    "exploiter": Template("It must beat $target, the $opponent_role with the single worst "
                          "result in the matrix. The docstring must name the weakness and the "
                          "pairing that shows it."),
    "counter_meta": Template("It must beat $target, the current #1 $opponent_role, "
                             "specifically. You have its source: find what it cannot handle. "
                             "The docstring must say which part of its logic you are "
                             "attacking and what in the replays shows that is where it "
                             "breaks."),
    "generalist": Template("It must do well against the whole field of ${opponent_role}s, "
                           "judged on mean score across all of them, not by beating one. The "
                           "docstring must say why the approach holds up against every "
                           "opponent described above."),
    "contrarian": Template("It must beat $target, the current #1 $opponent_role, with a core "
                           "idea that none of the existing ${role}s described above use. The "
                           "docstring must name the idea and say how it differs from each."),
}

IDEA_LINE = ("The docstring's first line must be `Idea: <one sentence>` saying what this bot "
             "does that others don't. It is quoted verbatim in the league's weekly report.")

SECOND_OF_TWO = Template("Tonight two bots are being written against $target, and this is "
                         "the second. Take a different approach from the most obvious "
                         "counter.\n")

TASK = Template("## Your task\n\n$one\n\n$goal\n\n$idea\n$extra")
