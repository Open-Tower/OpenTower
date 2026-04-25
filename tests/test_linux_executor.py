from __future__ import annotations

from types import SimpleNamespace

from opentower_cli import linux_executor
from opentower_cli.ops_types import PlannedCommand


def test_detect_bash_launcher_prefers_wsl_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(linux_executor.os, "name", "nt", raising=False)

    def fake_which(name: str) -> str | None:
        if name == "wsl.exe":
            return r"C:\Windows\System32\wsl.exe"
        if name == "bash":
            return r"C:\Program Files\Git\bin\bash.exe"
        return None

    monkeypatch.setattr(linux_executor.shutil, "which", fake_which)

    assert linux_executor.detect_bash_launcher() == [r"C:\Windows\System32\wsl.exe", "bash", "-lc"]


def test_execute_commands_uses_utf8_decoding(monkeypatch) -> None:
    observed: dict[str, object] = {}

    monkeypatch.setattr(linux_executor, "_launcher_for_target", lambda target: ["bash", "-lc"])

    def fake_run(argv, *, capture_output, text, encoding, errors, timeout, check):
        observed["argv"] = argv
        observed["capture_output"] = capture_output
        observed["text"] = text
        observed["encoding"] = encoding
        observed["errors"] = errors
        observed["timeout"] = timeout
        observed["check"] = check
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(linux_executor.subprocess, "run", fake_run)

    results = linux_executor.execute_commands(
        [PlannedCommand(name="demo", description="demo", command="echo ok")],
        timeout_seconds=9,
    )

    assert len(results) == 1
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"
    assert observed["text"] is True
