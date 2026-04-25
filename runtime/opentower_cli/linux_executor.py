from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Sequence

from .ops_types import CommandExecution, PlannedCommand


@dataclass(frozen=True)
class ExecutionTarget:
    kind: str = "local"
    host: str | None = None
    user: str | None = None


def detect_bash_launcher() -> list[str]:
    if os.name == "nt":
        wsl = shutil.which("wsl.exe")
        if wsl:
            return [wsl, "bash", "-lc"]
    bash = shutil.which("bash")
    if bash:
        return [bash, "-lc"]
    wsl = shutil.which("wsl.exe")
    if wsl:
        return [wsl, "bash", "-lc"]
    raise OSError("No bash-compatible runtime found. Run the tool on Linux or install bash/WSL.")


def _launcher_for_target(target: ExecutionTarget | None) -> list[str]:
    if target is None or target.kind == "local":
        return detect_bash_launcher()
    if target.kind == "ssh":
        if not target.host:
            raise ValueError("SSH target requires a host.")
        remote = f"{target.user}@{target.host}" if target.user else target.host
        return ["ssh", remote, "bash", "-lc"]
    raise ValueError(f"Unsupported execution target: {target.kind}")


def execute_commands(
    commands: Sequence[PlannedCommand],
    *,
    timeout_seconds: int = 30,
    target: ExecutionTarget | None = None,
) -> list[CommandExecution]:
    launcher = _launcher_for_target(target)
    results: list[CommandExecution] = []
    for planned in commands:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [*launcher, planned.command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            timed_out = False
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\nCommand timed out."
            returncode = -1
        duration_seconds = time.perf_counter() - started
        result = CommandExecution(
            name=planned.name,
            command=planned.command,
            description=planned.description,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            duration_seconds=duration_seconds,
            timed_out=timed_out,
        )
        results.append(result)
        if returncode not in planned.allowed_returncodes and not planned.allow_failure:
            break
    return results
