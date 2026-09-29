"""Submission pipeline: an outside bot's only way into the league. Prepared, not opened.

    python -m colosseum.submit my_bot.py --side attacker --author ada

Nothing listens on the network; this is the path a submission will take once the founder
decides how files arrive. Steps, in order, and the first failure stops everything:

 1. size and encoding: at most MAX_BYTES, UTF-8
 2. static checks with `ast`, on the host, without importing or running anything:
    allowlisted imports only, no forbidden builtins, no dunder or private attribute access,
    top level limited to definitions and constants, NAME/ROLE/act present and well formed
 3. duplicate check: the same file (sha256) already accepted -> no-op
 4. smoke test in the sandbox: one match against one baseline, one seed. Rejected if the
    container stops answering (a busy loop hits the per-tick timeout), or the bot errors on
    every tick, or it cannot even start
 5. accepted: copied to bots/submitted/<side>/<handle>__<NAME>.py with a .meta.json

A rejection prints a plain-English reason and also writes it to
out/submissions/rejected/<time>_<handle>.txt. Rejected code is never kept.

The container is the security boundary (no network, read-only filesystem, capped CPU,
memory and processes, non-root). These static checks are defence in depth, and they give
honest mistakes a readable error instead of a mysterious crash. SUBMITTING.md is the
player-facing version of all of this.
"""
import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .rules import SEASON0
from .sandbox import SandboxedPolicy, SandboxLimits
from .sim import Match
from .tournament import DEFAULT_OUT, ROOT

SUBMITTED = ROOT / "bots" / "submitted"
REJECTED = DEFAULT_OUT / "submissions" / "rejected"
MAX_BYTES = 64 * 1024

ALLOWED_IMPORTS = frozenset({
    "math", "random", "itertools", "functools", "collections", "heapq", "bisect",
    "statistics", "dataclasses", "typing", "enum", "operator",
})
FORBIDDEN_CALLS = frozenset({
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "input", "breakpoint", "help", "exit", "quit",
    "memoryview", "__builtins__",
})
# Attributes that walk from an ordinary object to frames, code or globals.
FORBIDDEN_ATTRS = frozenset({
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code", "f_globals",
    "f_locals", "f_back", "f_builtins", "f_code", "tb_frame", "tb_next", "co_code",
    "func_globals", "func_code", "system", "popen",
})
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,23}$")
BASELINE_OPPONENT = {"attacker": ROOT / "bots" / "defenders" / "layered.py",
                     "defender": ROOT / "bots" / "attackers" / "rush.py"}


class Rejected(Exception):
    """A submission failed a check. The message is shown to the author as-is."""


# --- static checks ------------------------------------------------------------

def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def check_source(source: str, side: str) -> str:
    """Raise Rejected with a readable reason, or return the bot's NAME. Never executes."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Rejected(f"Python can't read this file: {exc.msg} on line {exc.lineno}.")

    top = {"NAME": None, "ROLE": None}
    has_act = False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue                                         # docstring
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef,
                             ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in top:
                        if not isinstance(node.value, ast.Constant):
                            raise Rejected(f"{t.id} must be a plain string, like "
                                           f"{t.id} = \"...\".")
                        top[t.id] = node.value.value
            if isinstance(node, ast.FunctionDef) and node.name == "act":
                has_act = True
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            raise Rejected(f"Line {node.lineno}: async code is not supported; act() is "
                           "called as a plain function.")
        raise Rejected(f"Line {node.lineno}: the top level of the file may only hold "
                       f"imports, constants, functions and classes, not a "
                       f"{type(node).__name__}. Put the code inside a function.")

    if not has_act:
        raise Rejected("There is no `def act(obs):` at the top level of the file.")
    name, role = top["NAME"], top["ROLE"]
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise Rejected("NAME must be 2-40 characters: lowercase letters, digits and _, "
                       "starting with a letter (e.g. NAME = \"slow_pincer\").")
    if role != side:
        raise Rejected(f"ROLE is {role!r} but you submitted it as --side {side}. They "
                       "must match.")

    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    raise Rejected(f"Line {line}: `import {alias.name}` is not allowed. "
                                   f"Allowed modules: {', '.join(sorted(ALLOWED_IMPORTS))}.")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORTS:
                raise Rejected(f"Line {line}: `from {node.module} import ...` is not "
                               f"allowed. Allowed modules: "
                               f"{', '.join(sorted(ALLOWED_IMPORTS))}.")
            for alias in node.names:
                if alias.name.startswith("_") or alias.name == "*":
                    raise Rejected(f"Line {line}: importing `{alias.name}` is not allowed "
                                   "(no private names, no `import *`).")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_CALLS:
                raise Rejected(f"Line {line}: `{node.id}` is not allowed in a bot.")
            if _is_dunder(node.id):
                raise Rejected(f"Line {line}: names like `{node.id}` (double underscores "
                               "on both sides) are off limits.")
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr):
                raise Rejected(f"Line {line}: `.{node.attr}` is off limits -- no double-"
                               "underscore attributes.")
            if node.attr in FORBIDDEN_ATTRS:
                raise Rejected(f"Line {line}: `.{node.attr}` is not allowed in a bot.")
            owner = node.value.id if isinstance(node.value, ast.Name) else None
            if node.attr.startswith("_") and owner not in ("self", "cls"):
                raise Rejected(f"Line {line}: `.{node.attr}` reaches into something "
                               "private. Only your own self._x / cls._x are allowed.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"__\w+__", node.value):
                raise Rejected(f"Line {line}: the string {node.value!r} looks like an "
                               "attempt to reach a hidden attribute.")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor,
                               ast.AsyncWith)):
            raise Rejected(f"Line {line}: async code is not supported; act() is called "
                           "as a plain function.")
    return name


# --- sandbox smoke test -------------------------------------------------------

def smoke(path: Path, side: str, limits: SandboxLimits = SandboxLimits()) -> str:
    """One sandboxed match against a baseline. Returns a summary or raises Rejected."""
    opponent = BASELINE_OPPONENT[side]
    try:
        mine = SandboxedPolicy(path, side, limits)
    except Exception as exc:
        raise Rejected(f"The bot could not start in the sandbox: {exc}")
    try:
        other = SandboxedPolicy(opponent, "defender" if side == "attacker" else "attacker",
                                limits)
    except Exception:
        mine.close()
        raise
    try:
        a, d = (mine, other) if side == "attacker" else (other, mine)
        meta = Match(a, d, 0, rules=SEASON0, record=False).run()["meta"]
    finally:
        mine.close()
        other.close()
    if mine.restarts or mine.dead:
        raise Rejected(f"The bot stopped answering: at least one act() call took longer "
                       f"than {limits.tick_timeout:g} s, so the sandbox restarted it "
                       f"({mine.restarts} restart(s)). Every call must return quickly.")
    if mine.policy_errors >= meta["ticks"]:
        raise Rejected(f"The bot raised an error on every tick. Last error: "
                       f"{mine.last_error or 'unknown'}")
    return (f"{meta['ticks']} ticks against {opponent.stem}, {mine.policy_errors} errors, "
            f"outcome {meta['outcome']}")


# --- the pipeline -------------------------------------------------------------

def find_by_sha(sha: str):
    for meta in SUBMITTED.glob("*/*.meta.json"):
        if json.loads(meta.read_text()).get("sha256") == sha:
            return meta
    return None


def reject(handle: str, reason: str) -> dict:
    REJECTED.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    safe = handle if HANDLE_RE.match(handle or "") else "unknown"
    note = REJECTED / f"{stamp}_{safe}.txt"
    note.write_text(f"Submission from {safe} was rejected.\n\n{reason}\n")
    return dict(status="rejected", reason=reason, note=str(note))


def submit(path: Path, side: str, author: str, limits: SandboxLimits = SandboxLimits()):
    if side not in ("attacker", "defender"):
        return reject(author, "--side must be attacker or defender.")
    if not HANDLE_RE.match(author or ""):
        return reject(author, "Your handle must be 2-24 characters: lowercase letters, "
                              "digits, _ and -, starting with a letter or digit.")
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        return reject(author, f"The file is {len(raw):,} bytes; the limit is "
                              f"{MAX_BYTES:,}.")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        return reject(author, "The file is not UTF-8 text.")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        name = check_source(source, side)
    except Rejected as exc:
        return reject(author, str(exc))

    existing = find_by_sha(sha)
    if existing:
        return dict(status="duplicate", sha256=sha,
                    message=f"Already accepted as {existing.name[:-len('.meta.json')]}; "
                            "nothing to do.")

    with tempfile.TemporaryDirectory(prefix="submission_") as tmp:
        staged = Path(tmp) / f"{author}__{name}.py"
        staged.write_bytes(raw)
        try:
            detail = smoke(staged, side, limits)
        except Rejected as exc:
            return reject(author, str(exc))
        dest_dir = SUBMITTED / side
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / staged.name
        meta_path = dest.with_suffix(".meta.json")
        replaced = (json.loads(meta_path.read_text()).get("sha256")
                    if meta_path.exists() else None)
        shutil.copyfile(staged, dest)
    meta = dict(name=dest.stem, bot_name=name, side=side, author=author,
                submitted=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                sha256=sha, bytes=len(raw), replaces_sha256=replaced,
                validation=dict(static="passed", smoke=detail))
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return dict(status="accepted", path=str(dest), **meta)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path)
    ap.add_argument("--side", required=True, choices=("attacker", "defender"))
    ap.add_argument("--author", required=True)
    args = ap.parse_args()
    result = submit(args.path, args.side, args.author)
    if result["status"] == "rejected":
        print(f"REJECTED: {result['reason']}")
        return 1
    if result["status"] == "duplicate":
        print(result["message"])
        return 0
    print(f"ACCEPTED as {result['name']} ({result['validation']['smoke']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
