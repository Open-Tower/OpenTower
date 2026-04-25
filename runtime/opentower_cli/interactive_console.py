from __future__ import annotations

import argparse
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .anthropic_client import AnthropicMessagesClient, ProviderError
from .intent_parser import parse_objective
from .ollama_client import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from .ollama_client import OllamaMessagesClient
from .openai_compatible_client import DEFAULT_MODEL as OPENAI_COMPATIBLE_DEFAULT_MODEL
from .openai_compatible_client import OpenAICompatibleMessagesClient
from .provider_runtime import normalize_provider_name


CommandRunner = Callable[[Sequence[str] | None], int]
EmitFn = Callable[[str], None]
InputFn = Callable[[str], str]
RouterFactory = Callable[["ConsoleDefaults"], tuple[Any, str]]

_DEFAULT_KEY_ALIASES = {
    "provider": "provider",
    "model": "model",
    "api-base-url": "api_base_url",
    "api_base_url": "api_base_url",
    "api-key": "api_key",
    "api_key": "api_key",
}


@dataclass
class ConsoleDefaults:
    provider: str | None = None
    model: str | None = None
    api_base_url: str | None = None
    api_key: str | None = None

    def display_rows(self) -> list[tuple[str, str]]:
        return [
            ("provider", self.provider or "-"),
            ("model", self.model or "-"),
            ("api_base_url", self.api_base_url or "-"),
            ("api_key", _mask_secret(self.api_key)),
        ]


@dataclass(frozen=True)
class OptionSpec:
    dest: str
    option_strings: tuple[str, ...]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help_text: str
    parser: argparse.ArgumentParser
    options_by_dest: dict[str, OptionSpec]


def _mask_secret(value: str | None) -> str:
    if not value:
        return "-"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * max(len(value) - 4, 4)}{value[-4:]}"


def _tokenize(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    return [str(token) for token in lexer if str(token).strip()]


def _preferred_option_name(option_strings: Sequence[str]) -> str:
    for option in option_strings:
        if option.startswith("--"):
            return option
    return option_strings[0] if option_strings else ""


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {
                str(name): subparser
                for name, subparser in action.choices.items()
                if isinstance(subparser, argparse.ArgumentParser)
            }
    return {}


def _build_command_specs(parser: argparse.ArgumentParser) -> dict[str, CommandSpec]:
    specs: dict[str, CommandSpec] = {}
    for name, subparser in _subparsers(parser).items():
        options_by_dest: dict[str, OptionSpec] = {}
        for action in subparser._actions:
            if not action.option_strings or isinstance(action, argparse._HelpAction):
                continue
            options_by_dest[str(action.dest)] = OptionSpec(dest=str(action.dest), option_strings=tuple(action.option_strings))
        specs[name] = CommandSpec(
            name=name,
            help_text=str(getattr(subparser, "description", "") or "").strip() or str(getattr(subparser, "prog", "")).strip(),
            parser=subparser,
            options_by_dest=options_by_dest,
        )
    return specs


def _default_router_factory(defaults: ConsoleDefaults) -> tuple[Any, str]:
    provider = normalize_provider_name(defaults.provider) if defaults.provider else normalize_provider_name()
    if provider == "ollama":
        return (
            OllamaMessagesClient(api_url=defaults.api_base_url or None, api_key=defaults.api_key or None),
            defaults.model or os.environ.get("OPENTOWER_OLLAMA_MODEL", "").strip() or OLLAMA_DEFAULT_MODEL,
        )
    if provider == "openai-compatible":
        return (
            OpenAICompatibleMessagesClient(api_url=defaults.api_base_url or None, api_key=defaults.api_key or None),
            defaults.model or os.environ.get("OPENTOWER_OPENAI_MODEL", "").strip() or OPENAI_COMPATIBLE_DEFAULT_MODEL,
        )
    return (
        AnthropicMessagesClient(api_key=defaults.api_key or os.environ.get("ANTHROPIC_API_KEY")),
        defaults.model or os.environ.get("OPENTOWER_CLAUDE_MODEL", "").strip() or "claude-sonnet-4-20250514",
    )


def _extract_json_payload(text: str) -> dict[str, Any]:
    candidate = str(text).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("Router did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Router JSON must be an object.")
    return payload


def _normalize_routed_command(command: Any) -> list[str]:
    if isinstance(command, str):
        tokens = _tokenize(command)
    elif isinstance(command, list):
        tokens = [str(token).strip() for token in command if str(token).strip()]
    else:
        raise ValueError("Router command must be a string or list.")
    if not tokens:
        raise ValueError("Command is empty.")
    if tokens[0].startswith("/"):
        tokens[0] = tokens[0][1:]
    if tokens and tokens[0] in {"python", "py"} and len(tokens) > 2 and tokens[1] == "-m":
        tokens = tokens[3:]
    if tokens and tokens[0] in {"opentower", "opentower_cli"}:
        tokens = tokens[1:]
    if not tokens:
        raise ValueError("Command is empty.")
    return tokens


def _redacted_command(tokens: Sequence[str]) -> str:
    rendered: list[str] = []
    redact_next = False
    for token in tokens:
        text = str(token)
        if redact_next:
            rendered.append(_mask_secret(text))
            redact_next = False
            continue
        if text.startswith("--api-key="):
            rendered.append(f"--api-key={_mask_secret(text.split('=', 1)[1])}")
            continue
        rendered.append(text)
        if text == "--api-key":
            redact_next = True
    return " ".join(rendered)


class InteractiveConsole:
    def __init__(
        self,
        *,
        parser: argparse.ArgumentParser,
        command_runner: CommandRunner,
        defaults: ConsoleDefaults | None = None,
        auth_path: Path | None = None,
        emit: EmitFn | None = None,
        input_fn: InputFn | None = None,
        router_factory: RouterFactory | None = None,
    ) -> None:
        self.parser = parser
        self.command_runner = command_runner
        self.defaults = defaults or ConsoleDefaults()
        self.auth_path = auth_path
        self.emit = emit or (lambda text: print(text, flush=True))
        self.input_fn = input_fn or input
        self.router_factory = router_factory or _default_router_factory
        self.command_specs = _build_command_specs(parser)

    def run(self) -> int:
        self.emit("OpenTower Linux Ops console")
        self.emit("Natural language is the default input mode. Use / commands only for explicit CLI instructions.")
        if self.auth_path is not None:
            self.emit(f"LLM auth file: {self.auth_path}")
        self._print_defaults()
        while True:
            try:
                line = self.input_fn("opentower> ")
            except EOFError:
                self.emit("Interactive console closed.")
                return 0
            except KeyboardInterrupt:
                self.emit("")
                self.emit("Use /exit to quit.")
                continue
            if not self.handle_line(line):
                return 0

    def handle_line(self, line: str) -> bool:
        text = str(line or "").strip()
        if not text:
            return True
        if text.startswith("/"):
            return self._handle_slash(text[1:].strip())
        return self._handle_natural_language(text)

    def _print_defaults(self) -> None:
        self.emit("Current defaults:")
        for key, value in self.defaults.display_rows():
            self.emit(f"- {key}: {value}")

    def _handle_slash(self, text: str) -> bool:
        if text in {"help", "commands", ""}:
            self._print_commands()
            return True
        tokens = _tokenize(text)
        if not tokens:
            self._print_commands()
            return True
        verb = tokens[0].lower()
        if verb in {"exit", "quit"}:
            self.emit("Interactive console closed.")
            return False
        if verb == "show":
            if len(tokens) != 2:
                self.emit("Usage: /show <command>")
                return True
            spec = self.command_specs.get(tokens[1].lstrip("/"))
            if spec is None:
                self.emit(f"Unknown command: {tokens[1]}")
                return True
            self.emit(spec.parser.format_help().rstrip())
            return True
        if verb == "defaults":
            self._print_defaults()
            return True
        if verb == "set":
            if len(tokens) < 3:
                self.emit("Usage: /set <provider|model|api-base-url|api-key> <value>")
                return True
            self._set_default(tokens[1], " ".join(tokens[2:]).strip())
            return True
        if verb in {"clear", "unset"}:
            if len(tokens) != 2:
                self.emit("Usage: /clear <provider|model|api-base-url|api-key|all>")
                return True
            self._clear_default(tokens[1])
            return True
        if verb == "run":
            if len(tokens) < 2:
                self.emit("Usage: /run <existing CLI args...>")
                return True
            return self._execute_command(tokens[1:])
        return self._execute_command(tokens)

    def _handle_natural_language(self, text: str) -> bool:
        local_payload = self._local_route(text)
        if local_payload is not None:
            if local_payload["action"] == "answer":
                self.emit(str(local_payload["message"]))
                return True
            command = _normalize_routed_command(local_payload["command"])
            return self._execute_command(command, announce_route=True)
        try:
            payload = self._route_text(text)
        except (ProviderError, ValueError) as exc:
            self.emit(f"Routing error: {exc}")
            self.emit("Use /dispatch --objective \"...\" --execute or /workflow directly.")
            return True
        if str(payload.get("action", "")).strip().lower() == "answer":
            self.emit(str(payload.get("message", "")).strip() or "No answer returned.")
            return True
        command = _normalize_routed_command(payload.get("command"))
        return self._execute_command(command, announce_route=True)

    def _local_route(self, text: str) -> dict[str, Any] | None:
        lowered = text.lower()
        if any(token in text for token in ("工作流", "支持什么", "有哪些能力")) or "workflow" in lowered:
            return {"action": "run_command", "command": ["workflow"]}
        if "provider" in lowered or "模型状态" in text or "api key" in lowered:
            return {"action": "run_command", "command": ["provider-status"]}
        try:
            parse_objective(text)
        except ValueError:
            return None
        else:
            return {"action": "run_command", "command": ["dispatch", "--objective", text, "--execute"]}

    def _route_text(self, text: str) -> dict[str, Any]:
        client, model = self.router_factory(self.defaults)
        response = client.create_message(
            system=self._routing_system_prompt(),
            user_text=text,
            model=model,
            max_tokens=500,
            temperature=0,
        )
        return _extract_json_payload(response.text)

    def _routing_system_prompt(self) -> str:
        return "\n".join(
            [
                "You are the OpenTower Linux Ops terminal router.",
                "Map the user request to one command: workflow, dispatch, or provider-status.",
                "Use dispatch for concrete Linux operations requests.",
                "Return JSON only.",
                'Schema: {"action":"run_command"|"answer","command":["dispatch","--objective","...","--execute"],"message":"..."}',
            ]
        )

    def _print_commands(self) -> None:
        self.emit("Console slash commands:")
        self.emit("- /auth")
        self.emit("- /workflow")
        self.emit("- /dispatch --objective \"...\" --execute")
        self.emit("- /provider-status")
        self.emit("- /show <command>")
        self.emit("- /defaults")
        self.emit("- /set <provider|model|api-base-url|api-key> <value>")
        self.emit("- /clear <provider|model|api-base-url|api-key|all>")
        self.emit("- /exit")

    def _set_default(self, key: str, value: str) -> None:
        normalized = _DEFAULT_KEY_ALIASES.get(str(key).strip().lower())
        if normalized is None:
            self.emit(f"Unknown default key: {key}")
            return
        if not value:
            self.emit(f"Default {normalized} requires a value.")
            return
        if normalized == "provider":
            value = normalize_provider_name(value)
        setattr(self.defaults, normalized, value)
        self.emit(f"Updated default {normalized}.")

    def _clear_default(self, key: str) -> None:
        clean = str(key).strip().lower()
        if clean == "all":
            self.defaults = ConsoleDefaults()
            self.emit("Cleared all defaults.")
            return
        normalized = _DEFAULT_KEY_ALIASES.get(clean)
        if normalized is None:
            self.emit(f"Unknown default key: {key}")
            return
        setattr(self.defaults, normalized, None)
        self.emit(f"Cleared default {normalized}.")

    def _execute_command(self, argv: Sequence[str], *, announce_route: bool = False) -> bool:
        try:
            command = self._prepare_command(argv)
        except ValueError as exc:
            self.emit(f"Input error: {exc}")
            return True
        if announce_route:
            self.emit(f"route: {_redacted_command(command)}")
        rc = self.command_runner(command)
        if rc != 0:
            self.emit(f"Command exited with code {rc}.")
        return True

    def _prepare_command(self, argv: Sequence[str]) -> list[str]:
        command = _normalize_routed_command(list(argv))
        if not command:
            raise ValueError("Command is empty.")
        if command[0] == "console":
            raise ValueError("Nested console sessions are not supported.")
        spec = self.command_specs.get(command[0])
        if spec is None:
            raise ValueError(f"Unknown command: {command[0]}")
        return self._apply_defaults(command, spec)

    def _apply_defaults(self, argv: list[str], spec: CommandSpec) -> list[str]:
        for dest in ("provider", "model", "api_base_url", "api_key"):
            value = getattr(self.defaults, dest)
            option = spec.options_by_dest.get(dest)
            if not value or option is None:
                continue
            if any(token == preferred or token.startswith(f"{preferred}=") for preferred in option.option_strings for token in argv):
                continue
            argv.extend([_preferred_option_name(option.option_strings), value])
        return argv


def run_console(
    *,
    parser: argparse.ArgumentParser,
    command_runner: CommandRunner,
    defaults: ConsoleDefaults | None = None,
    auth_path: Path | None = None,
    emit: EmitFn | None = None,
    input_fn: InputFn | None = None,
    router_factory: RouterFactory | None = None,
) -> int:
    return InteractiveConsole(
        parser=parser,
        command_runner=command_runner,
        defaults=defaults,
        auth_path=auth_path,
        emit=emit,
        input_fn=input_fn,
        router_factory=router_factory,
    ).run()


__all__ = [
    "ConsoleDefaults",
    "InteractiveConsole",
    "run_console",
]
