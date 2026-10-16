"""PostToolUse hook (Write|Edit): the repo's formatter, deliberately minimal.

No formatter is installed and adding one would reformat whole files, so this only strips
trailing whitespace and makes sure a text file ends with one newline. It reads the hook's
JSON on stdin, touches only files inside the repo with a known text suffix, and never fails
the tool call (exit 0 always).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = {".py", ".md", ".sh", ".json", ".css", ".js", ".html", ".txt", ".toml", ".cff", ".yml"}


def tidy(text: str) -> str:
    lines = [l.rstrip() for l in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def main() -> int:
    try:
        path = Path(json.load(sys.stdin)["tool_input"]["file_path"]).resolve()
    except Exception:
        return 0
    if path.suffix not in TEXT or not path.is_file() or not path.is_relative_to(ROOT):
        return 0
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return 0
    new = tidy(text)
    if new != text:
        path.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
