"""Content check for generated bots: game terms only.

A generated bot whose source, comments, docstring or metadata uses real-world vocabulary is
rejected before validation, logged with the CONTENT: flag, and the night continues with
whatever else was produced.

The list is deliberately generic (categories of real-world things, not names of any real
system), plus the shape of a model or designation code, so this file itself names nothing
real. Words the game's own API and rules use (drones, radar, interceptor, gun, striker,
decoy, asset, launch, blast) are not on it.
"""
import re

REAL_WORLD_TERMS = (
    "military", "army", "navy", "air force", "marines", "soldier", "troops", "battalion",
    "brigade", "regiment", "squadron", "warship", "aircraft carrier", "airbase", "missile",
    "warhead", "munition", "ordnance", "artillery", "nuclear", "war", "warfare",
    "battlefield", "combat", "invasion", "frontline", "casualties",
)
_TERMS = re.compile(r"\b(" + "|".join(re.escape(t) for t in REAL_WORLD_TERMS) + r")s?\b",
                    re.IGNORECASE)
# e.g. "AB-12", "XYZ-300": the usual shape of a real model or designation code
_DESIGNATION = re.compile(r"\b[A-Z]{1,4}-\d{1,4}[A-Z]?\b")


# Code-shaped strings that are not designations
_NOT_DESIGNATIONS = re.compile(r"^(UTF|ISO|PEP|RFC|SHA|MD|CP|CC|BY)-", re.IGNORECASE)   # incl. licence ids


def findings(text: str):
    """Every match, as (term, line number)."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        out += [(m.group(0), n) for m in _TERMS.finditer(line)]
        out += [(m.group(0), n) for m in _DESIGNATION.finditer(line)
                if not _NOT_DESIGNATIONS.match(m.group(0))]
    return out


def check(source: str, meta: dict = None):
    """(ok, reason). Checks the whole file -- code, comments and docstring -- and metadata."""
    hits = findings(source)
    if meta:
        hits += [(t, "meta") for t, _ in findings(" ".join(str(v) for v in meta.values()))]
    if not hits:
        return True, ""
    shown = ", ".join(f"{t!r} (line {n})" for t, n in hits[:5])
    return False, f"real-world reference: {shown}"
