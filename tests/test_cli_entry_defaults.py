from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from opentower_cli import cli as cli_mod
from opentower_cli import interactive_console as console_mod
from opentower_cli.provider_runtime import ProviderStatus


def local_test_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_pytest"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_startup_defaults(root: Path, *lines: str) -> Path:
    path = root / ".opentower" / "defaults.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    path.write_text(payload, encoding="utf-8")
    return path


def test_main_without_subcommand_starts_console_and_seeds_provider_defaults(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=local_test_root()) as temp_dir:
        repo_root = Path(temp_dir)
        write_startup_defaults(repo_root, "provider=ollama")
        observed: dict[str, Any] = {}

        def fake_run_console(*, parser, command_runner, defaults, auth_path=None, emit=None, input_fn=None, router_factory=None):
            observed["defaults"] = defaults
            observed["command_runner"] = command_runner
            return 0

        monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
        monkeypatch.setattr(console_mod, "run_console", fake_run_console)

        rc = cli_mod.main([])

        assert rc == 0
        assert observed["defaults"].provider == "ollama"


def test_flag_only_console_startup_uses_console_defaults(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=local_test_root()) as temp_dir:
        repo_root = Path(temp_dir)
        write_startup_defaults(repo_root, "provider=openai-compatible")
        observed: dict[str, Any] = {}

        def fake_run_console(*, parser, command_runner, defaults, auth_path=None, emit=None, input_fn=None, router_factory=None):
            observed["defaults"] = defaults
            return 0

        monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
        monkeypatch.setattr(console_mod, "run_console", fake_run_console)

        rc = cli_mod.main(["--provider", "ollama", "--model", "qwen3:8b"])

        assert rc == 0
        assert observed["defaults"].provider == "ollama"
        assert observed["defaults"].model == "qwen3:8b"


def test_provider_status_uses_startup_defaults_provider(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=local_test_root()) as temp_dir:
        repo_root = Path(temp_dir)
        write_startup_defaults(repo_root, "provider=openai")
        observed: dict[str, str | None] = {}

        def fake_provider_status() -> ProviderStatus:
            observed["provider"] = os.environ.get("OPENTOWER_MODEL_PROVIDER")
            return ProviderStatus(
                provider="openai-compatible",
                api_url="https://example.invalid/v1/chat/completions",
                api_version="chat-completions",
                api_key_present=False,
                configured_model="gpt-4o-mini",
                configured_opus_model="",
                execute_ready=False,
            )

        monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
        monkeypatch.delenv("OPENTOWER_MODEL_PROVIDER", raising=False)
        monkeypatch.setattr(cli_mod, "provider_status", fake_provider_status)

        rc = cli_mod.main(["provider-status"])

        assert rc == 0
        assert observed["provider"] == "openai-compatible"
