from __future__ import annotations

import json
from typing import Any

from opentower_cli import cli as cli_mod
from opentower_cli.anthropic_client import AnthropicMessageResponse
from opentower_cli.interactive_console import ConsoleDefaults, InteractiveConsole


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv or []))
        return 0


class FakeRouterClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def create_message(
        self,
        *,
        system: str,
        user_text: str,
        model: str | None = None,
        max_tokens: int = 1400,
        temperature: float = 0.2,
    ) -> AnthropicMessageResponse:
        return AnthropicMessageResponse(
            id="msg-console-route",
            model=model or "gpt-4o-mini",
            text=json.dumps(self.payload),
            stop_reason="end_turn",
            usage={"input_tokens": 80, "output_tokens": 20},
            raw={},
        )


def build_console(
    *,
    defaults: ConsoleDefaults | None = None,
    router_payload: dict[str, Any] | None = None,
) -> tuple[InteractiveConsole, RecordingRunner, list[str]]:
    runner = RecordingRunner()
    output: list[str] = []

    def _router_factory(_defaults: ConsoleDefaults):
        payload = router_payload or {"action": "answer", "message": "noop"}
        return FakeRouterClient(payload), "gpt-4o-mini"

    console = InteractiveConsole(
        parser=cli_mod.build_parser(),
        command_runner=runner,
        defaults=defaults,
        emit=output.append,
        router_factory=_router_factory,
    )
    return console, runner, output


def test_console_local_natural_language_route_dispatches_linux_request() -> None:
    console, runner, output = build_console()

    assert console.handle_line("查看磁盘使用情况") is True
    assert runner.calls == [["dispatch", "--objective", "查看磁盘使用情况", "--execute"]]
    assert any(message.startswith("route: dispatch") for message in output)


def test_console_provider_defaults_apply_to_provider_status() -> None:
    console, runner, _output = build_console(
        defaults=ConsoleDefaults(
            provider="openai-compatible",
            model="gpt-4o-mini",
            api_base_url="https://example.com/v1",
            api_key="sk-test-secret",
        )
    )

    assert console.handle_line("/provider-status") is True
    assert runner.calls == [
        [
            "provider-status",
            "--provider",
            "openai-compatible",
            "--model",
            "gpt-4o-mini",
            "--api-base-url",
            "https://example.com/v1",
            "--api-key",
            "sk-test-secret",
        ]
    ]


def test_console_show_command_prints_help() -> None:
    console, _runner, output = build_console()

    assert console.handle_line("/show dispatch") is True
    rendered = "\n".join(output)
    assert "usage: opentower dispatch" in rendered
    assert "--objective" in rendered


def test_console_startup_message_prefers_natural_language_and_shows_auth_file() -> None:
    output: list[str] = []
    runner = RecordingRunner()
    console = InteractiveConsole(
        parser=cli_mod.build_parser(),
        command_runner=runner,
        emit=output.append,
        input_fn=lambda _prompt: (_ for _ in ()).throw(EOFError()),
        auth_path=cli_mod._repo_root() / "auth.json",
    )

    assert console.run() == 0
    rendered = "\n".join(output)
    assert "Natural language is the default input mode." in rendered
    assert "LLM auth file:" in rendered


def test_console_local_route_dispatches_supported_deterministic_requests() -> None:
    console, runner, _output = build_console()

    assert console.handle_line("创建一个名为 dev01 的用户并加入 docker 组") is True
    assert console.handle_line("删除 /tmp/foo") is True
    assert console.handle_line("给所有文件 777 权限") is True

    assert runner.calls == [
        ["dispatch", "--objective", "创建一个名为 dev01 的用户并加入 docker 组", "--execute"],
        ["dispatch", "--objective", "删除 /tmp/foo", "--execute"],
        ["dispatch", "--objective", "给所有文件 777 权限", "--execute"],
    ]
