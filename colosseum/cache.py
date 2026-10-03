"""Match result cache: a match that has been played is never played again.

Key = (attacker file sha256, defender file sha256, seed, rules hash, engine version).

  rules hash      sha256 of the canonical JSON of the Rules object the match runs under --
                  not of rules.py's bytes, so season-two candidates that pass tuned Rules
                  objects never get season-one results back
  engine version  sha256 over the files that decide what a match does: sim.py, policy.py,
                  sandbox.py, sandbox_runner.py. Change any of them and every key changes,
                  which is the intended invalidation; nothing has to be deleted

Value = the match's full meta dict (scores, CER, outcome, counts of kills, impacts and
launches) and the replay's file name. The tournament still consumes results in its fixed
job order, so Elo and every other output are byte-identical whether a result came from the
cache or from a fresh match. A cache is not reuse: every match that does run gets its own
fresh container, exactly as before.

Retired bots keep their entries. Storage is one SQLite file (standard library), written
only by the tournament's main process.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_FILES = ("sim.py", "policy.py", "sandbox.py", "sandbox_runner.py")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def engine_version() -> str:
    h = hashlib.sha256()
    for name in ENGINE_FILES:
        h.update(name.encode() + b"\0" + (HERE / name).read_bytes() + b"\0")
    return h.hexdigest()[:16]


def rules_hash(rules) -> str:
    return _sha_bytes(json.dumps(rules.as_dict(), sort_keys=True).encode())[:16]


class ResultCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, "
                        "attacker TEXT, defender TEXT, seed INTEGER, meta TEXT, "
                        "replay TEXT)")
        self.db.commit()
        self._file_sha = {}
        self.engine = engine_version()

    def file_sha(self, path) -> str:
        path = str(path)
        if path not in self._file_sha:
            self._file_sha[path] = _sha_bytes(Path(path).read_bytes())
        return self._file_sha[path]

    def key(self, attacker, defender, seed, rules) -> str:
        return ":".join([self.file_sha(attacker), self.file_sha(defender), str(seed),
                         rules_hash(rules), self.engine])

    def get(self, key):
        row = self.db.execute("SELECT meta FROM results WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, attacker, defender, seed, meta, replay=None):
        self.db.execute("INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?, ?)",
                        (key, Path(attacker).stem, Path(defender).stem, int(seed),
                         json.dumps(meta), replay))

    def commit(self):
        self.db.commit()

    def size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM results").fetchone()[0]

    def close(self):
        self.db.commit()
        self.db.close()
