"""Runs inside the container. Never imported by the host.

Reads one JSON request per line on stdin and writes one JSON response per line on stdout:

    {"cmd":"meta"}                  -> {"ok":true,"name":...,"role":...}
    {"cmd":"reset","seed":7}        -> {"ok":true}
    {"cmd":"act","obs":{...}}       -> {"ok":true,"action":{...}}

Any failure is reported as {"ok":false,"error":"..."} rather than a crash, so the host can
count it exactly as it counts an in-process exception. An import-time failure is remembered
and reported against every later request instead of killing the process, because the host
needs the stream to stay alive to keep the match running.
"""
import importlib.util
import json
import sys


def _load(path):
    spec = importlib.util.spec_from_file_location("submitted_bot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ("NAME", "ROLE", "act"):
        if not hasattr(module, attr):
            raise AttributeError(f"bot is missing {attr}")
    return module


def main():
    path = sys.argv[1]
    module, load_error = None, None
    try:
        module = _load(path)
    except BaseException as exc:                     # noqa: BLE001 - report anything
        load_error = f"import: {type(exc).__name__}: {exc}"[:300]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:                     # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"bad request: {exc}"}), flush=True)
            continue

        if load_error:
            print(json.dumps({"ok": False, "error": load_error}), flush=True)
            continue

        cmd = req.get("cmd")
        try:
            if cmd == "meta":
                out = {"ok": True, "name": str(module.NAME), "role": str(module.ROLE)}
            elif cmd == "reset":
                fn = getattr(module, "reset", None)
                if fn is not None:
                    fn(req.get("seed", 0))
                out = {"ok": True}
            elif cmd == "act":
                action = module.act(req.get("obs", {}))
                if not isinstance(action, dict):
                    out = {"ok": False, "error": "act did not return a dict"}
                else:
                    out = {"ok": True, "action": action}
            else:
                out = {"ok": False, "error": f"unknown cmd {cmd!r}"}
        except BaseException as exc:                 # noqa: BLE001 - bots may raise anything
            out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}

        try:
            print(json.dumps(out), flush=True)
        except BaseException as exc:                 # noqa: BLE001 - unserialisable action
            print(json.dumps({"ok": False,
                              "error": f"unserialisable action: {exc}"[:300]}), flush=True)


if __name__ == "__main__":
    main()
