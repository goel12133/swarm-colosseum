"""Host side of the sandbox: run a submitted policy inside a container.

`SandboxedPolicy` is interface-compatible with `PolicyRunner`, so the engine cannot tell
the difference and a bot behaves identically in either mode. The container gets no network,
a CPU share, a memory cap, a pid cap, a read-only filesystem, no capabilities and a
non-root user; the host enforces a wall-clock timeout on every single call.

**A timeout or a crash is a no-op plus a `policy_errors` increment** -- the same treatment an
in-process exception gets. A container that has stopped answering (a busy loop, or an
out-of-memory kill) is restarted, up to `max_restarts` times; after that the policy is
treated as dead and every remaining call is a counted no-op. The match always finishes.

One container per match, not per tick: a container start costs roughly a second, which would
be 600 seconds a match.
"""
import json
import os
import select
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "sandbox_runner.py"


class SandboxUnavailable(RuntimeError):
    pass


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True,
                              timeout=20).returncode == 0
    except Exception:
        return False


@dataclass(frozen=True)
class SandboxLimits:
    image: str = "python:3.12-slim"
    cpus: str = "0.5"
    memory: str = "128m"
    pids: int = 64
    tick_timeout: float = 2.0        # seconds the host waits for one act()
    start_timeout: float = 25.0      # seconds to get the first response after launch
    max_restarts: int = 3


class SandboxedPolicy:
    def __init__(self, path, expected_role=None, limits=SandboxLimits()):
        self.path = Path(path).resolve()
        self.limits = limits
        self.expected_role = expected_role
        self.policy_errors = 0
        self.invalid_actions = 0
        self.last_error = ""
        self.restarts = 0
        self.dead = False
        self.proc = None
        self.container = f"colosseum-{uuid.uuid4().hex[:12]}"
        self._seed = 0
        self._start()
        meta = self._request({"cmd": "meta"}, timeout=limits.start_timeout) or {}
        self.name = meta.get("name") or self.path.stem
        self.role = meta.get("role") or (expected_role or "")
        if expected_role and self.role != expected_role:
            self.close()
            raise SandboxUnavailable(
                f"{self.path.name} reports ROLE {self.role!r}, expected {expected_role!r}")

    # --- container lifecycle ------------------------------------------------
    def _docker_cmd(self):
        lim = self.limits
        return [
            "docker", "run", "--rm", "-i",
            "--name", self.container,
            "--network=none",                       # no sockets, no DNS, no exfiltration
            f"--cpus={lim.cpus}",
            f"--memory={lim.memory}", f"--memory-swap={lim.memory}",   # no swap: OOM kills
            f"--pids-limit={lim.pids}",
            "--read-only", "--tmpfs", "/tmp:size=8m",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user", "65534:65534",
            "-e", "PYTHONHASHSEED=0",               # determinism across the boundary
            "-v", f"{RUNNER}:/sandbox/runner.py:ro",
            "-v", f"{self.path}:/bot/bot.py:ro",
            lim.image, "python", "-B", "-u", "/sandbox/runner.py", "/bot/bot.py",
        ]

    def _start(self):
        self.proc = subprocess.Popen(
            self._docker_cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def _kill(self):
        if self.proc is None:
            return
        try:
            self.proc.kill()
        except Exception:
            pass
        subprocess.run(["docker", "rm", "-f", self.container],
                       capture_output=True, timeout=20)
        self.proc = None

    def _restart(self):
        self._kill()
        if self.restarts >= self.limits.max_restarts:
            self.dead = True
            return False
        self.restarts += 1
        self._start()
        # a restarted container has forgotten everything, so replay the reset
        self._request({"cmd": "reset", "seed": self._seed},
                      timeout=self.limits.start_timeout, allow_restart=False)
        return True

    def close(self):
        self._kill()

    # --- transport ----------------------------------------------------------
    def _read_line(self, deadline):
        """Read one line, or return None if the deadline passes first."""
        buf = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if self.proc is None or self.proc.stdout is None:
                return None
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                return None
            chunk = self.proc.stdout.readline()
            if chunk == "":
                return None                          # container exited (crash or OOM kill)
            buf += chunk
            if buf.endswith("\n"):
                return buf

    def _request(self, payload, timeout=None, allow_restart=True):
        if self.dead or self.proc is None:
            return None
        timeout = self.limits.tick_timeout if timeout is None else timeout
        try:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()
        except Exception as exc:
            self.last_error = f"sandbox write: {type(exc).__name__}"
            if allow_restart:
                self._restart()
            return None

        line = self._read_line(time.monotonic() + timeout)
        if line is None:
            self.last_error = "sandbox: timeout or container exit"
            if allow_restart:
                self._restart()
            return None
        try:
            reply = json.loads(line)
        except Exception:
            self.last_error = "sandbox: unparseable reply"
            return None
        if not reply.get("ok"):
            self.last_error = str(reply.get("error", "sandbox error"))[:200]
            return None
        return reply

    # --- PolicyRunner-compatible surface ------------------------------------
    def reset(self, seed: int):
        self._seed = seed
        if self._request({"cmd": "reset", "seed": seed},
                         timeout=self.limits.start_timeout) is None:
            self.policy_errors += 1

    def act(self, obs: dict) -> dict:
        reply = self._request({"cmd": "act", "obs": obs})
        if reply is None:
            self.policy_errors += 1
            return {}
        action = reply.get("action")
        if not isinstance(action, dict):
            self.invalid_actions += 1
            return {}
        return action

    @property
    def stats(self) -> dict:
        return dict(policy_errors=self.policy_errors,
                    invalid_actions=self.invalid_actions,
                    last_error=self.last_error)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
