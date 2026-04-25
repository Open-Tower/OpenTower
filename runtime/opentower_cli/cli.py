from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .anthropic_client import ProviderError
from .auth_config import auth_env_overrides, load_auth_profile
from .config_loader import ConfigError
from .engine import list_workflows
from . import interactive_console as console_mod
from .interactive_console import ConsoleDefaults
from .provider_runtime import normalize_provider_name, provider_status
from .runtime_service import dispatch_and_maybe_execute, load_repo_configs, load_runtime_bundle
from .workflow_executor import resolve_confirmation


_STARTUP_DEFAULT_KEYS = {
    "provider": "provider",
}
_CLI_COMMANDS = {"workflow", "dispatch", "console", "provider-status", "auth"}


@dataclass(frozen=True)
class StartupDefaults:
    provider: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _startup_defaults_path(root: Path) -> Path:
    return root / ".opentower" / "defaults.txt"


def _preferred_option_name(option_strings: Sequence[str]) -> str:
    for option in option_strings:
        if option.startswith("--"):
            return option
    return option_strings[0] if option_strings else ""


def _argv_has_option(argv: Sequence[str], option_strings: Sequence[str]) -> bool:
    normalized = [str(option) for option in option_strings if str(option)]
    for token in argv:
        text = str(token)
        if text in normalized:
            return True
        if any(text.startswith(f"{option}=") for option in normalized):
            return True
    return False


def _subparser_map(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {
                str(name): subparser
                for name, subparser in action.choices.items()
                if isinstance(subparser, argparse.ArgumentParser)
            }
    return {}


def _load_startup_defaults(root: Path) -> StartupDefaults:
    path = _startup_defaults_path(root)
    if not path.exists():
        return StartupDefaults()
    seen: set[str] = set()
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid startup defaults line {path}:{line_number}; expected key=value")
        raw_key, raw_value = line.split("=", 1)
        key = _STARTUP_DEFAULT_KEYS.get(raw_key.strip().lower())
        if key is None:
            raise ConfigError(f"Unsupported startup defaults key '{raw_key.strip()}' in {path}:{line_number}")
        if key in seen:
            raise ConfigError(f"Duplicate startup defaults key '{raw_key.strip()}' in {path}:{line_number}")
        value = raw_value.strip()
        if not value:
            raise ConfigError(f"Startup defaults key '{raw_key.strip()}' requires a value in {path}:{line_number}")
        seen.add(key)
        values[key] = value
    provider = values.get("provider")
    if provider:
        provider = normalize_provider_name(provider)
    return StartupDefaults(provider=provider)


def _normalize_cli_argv(argv: Sequence[str] | None, *, default_to_console: bool) -> list[str]:
    tokens = [str(item) for item in (sys.argv[1:] if argv is None else argv)]
    if not tokens:
        return ["console"] if default_to_console else []
    first = str(tokens[0]).strip()
    if first in {"/help", "/commands", "help", "commands"}:
        return []
    if first.startswith("/") and len(first) > 1:
        return [first[1:], *tokens[1:]]
    if default_to_console and tokens[0].startswith("-") and tokens[0] not in {"-h", "--help"}:
        return ["console", *tokens]
    if first not in _CLI_COMMANDS and first not in {"-h", "--help"} and not first.startswith("-"):
        return ["dispatch", "--objective", " ".join(tokens), "--execute"]
    return tokens


def _prepare_argv(
    argv: Sequence[str] | None,
    *,
    parser: argparse.ArgumentParser,
    root: Path,
    apply_startup_defaults: bool,
) -> list[str]:
    command = _normalize_cli_argv(argv, default_to_console=apply_startup_defaults)
    if not apply_startup_defaults:
        return command
    defaults = _load_startup_defaults(root)
    if defaults == StartupDefaults() or not command:
        return command
    subparser = _subparser_map(parser).get(command[0])
    if subparser is None:
        return command
    options_by_dest = {
        str(action.dest): tuple(str(item) for item in action.option_strings)
        for action in subparser._actions
        if action.option_strings
    }
    if defaults.provider and "provider" in options_by_dest and not _argv_has_option(command, options_by_dest["provider"]):
        command.extend([_preferred_option_name(options_by_dest["provider"]), defaults.provider])
    return command


def _add_provider_override_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", help="Temporary provider override for this command")
    parser.add_argument("--model", help="Temporary model override for this command")
    parser.add_argument("--api-base-url", dest="api_base_url", help="Temporary provider API endpoint or base URL")
    parser.add_argument("--api-key", help="Temporary provider API key or token")


def _provider_override_env(args: argparse.Namespace) -> dict[str, str]:
    provider_arg = str(getattr(args, "provider", "") or "").strip()
    model_arg = str(getattr(args, "model", "") or "").strip()
    api_base_url_arg = str(getattr(args, "api_base_url", "") or "").strip()
    api_key_arg = str(getattr(args, "api_key", "") or "").strip()
    if not any((provider_arg, model_arg, api_base_url_arg, api_key_arg)):
        return {}
    provider = normalize_provider_name(provider_arg) if provider_arg else normalize_provider_name()
    overrides: dict[str, str] = {"OPENTOWER_MODEL_PROVIDER": provider}
    if provider == "anthropic":
        if model_arg:
            overrides["OPENTOWER_CLAUDE_MODEL"] = model_arg
        if api_base_url_arg:
            overrides["OPENTOWER_ANTHROPIC_API_URL"] = api_base_url_arg
        if api_key_arg:
            overrides["OPENTOWER_ANTHROPIC_API_KEY"] = api_key_arg
            overrides["ANTHROPIC_API_KEY"] = api_key_arg
        return overrides
    if provider == "ollama":
        if model_arg:
            overrides["OPENTOWER_OLLAMA_MODEL"] = model_arg
        if api_base_url_arg:
            overrides["OPENTOWER_OLLAMA_BASE_URL"] = api_base_url_arg
        if api_key_arg:
            overrides["OLLAMA_API_KEY"] = api_key_arg
        return overrides
    if model_arg:
        overrides["OPENTOWER_OPENAI_MODEL"] = model_arg
    if api_base_url_arg:
        overrides["OPENTOWER_OPENAI_BASE_URL"] = api_base_url_arg
    if api_key_arg:
        overrides["OPENTOWER_OPENAI_API_KEY"] = api_key_arg
        overrides["OPENAI_API_KEY"] = api_key_arg
    return overrides


@contextmanager
def _temporary_env(overrides: dict[str, str]):
    if not overrides:
        yield
        return
    sentinel = object()
    previous: dict[str, object] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key, sentinel)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)


def _print_provider_status(status: Any) -> None:
    print(f"provider: {status.provider}")
    print(f"api_url: {status.api_url}")
    print(f"api_version: {status.api_version}")
    print(f"api_key_present: {str(status.api_key_present).lower()}")
    print(f"configured_model: {status.configured_model}")
    print(f"execute_ready: {str(status.execute_ready).lower()}")
    if getattr(status, "model_available", None) is not None:
        print(f"model_available: {str(status.model_available).lower()}")
    if getattr(status, "available_models", None):
        print(f"available_models: {', '.join(status.available_models)}")
    if getattr(status, "status_detail", None):
        print(f"status_detail: {status.status_detail}")


def _print_auth_file_status(*, root: Path) -> None:
    profile = load_auth_profile(root)
    print(f"auth_file: {profile.path}")
    print(f"auth_provider: {profile.provider}")
    print(f"auth_model: {profile.model or '-'}")
    print(f"auth_api_base_url: {profile.api_base_url or '-'}")
    print(f"auth_api_key_present: {str(bool(profile.api_key)).lower()}")
    if profile.created:
        print("auth_status: template_created")
        print("auth_note: Edit auth.json and fill api_key or local model settings.")


def _make_execution_progress_callback() -> Any:
    def _callback(event: dict[str, Any]) -> None:
        event_name = str(event.get("event", "")).strip()
        if event_name == "workflow_started":
            print(f"execution: workflow={event.get('workflow_id', '-')} turns={event.get('turn_count', 0)}", flush=True)
            return
        if event_name == "turn_started":
            print(
                f"progress: [{event.get('turn_index', 0)}/{event.get('turn_count', 0)}] {event.get('agent_id', '-')}",
                flush=True,
            )
            return
        if event_name == "workflow_completed":
            print(f"execution_status: {event.get('status', '-')}", flush=True)

    return _callback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opentower", description="OpenTower Linux Ops CLI")
    sub = parser.add_subparsers(dest="command")

    p_workflow = sub.add_parser("workflow", help="List supported Linux operations workflows")
    p_workflow.add_argument("--workflow", help="Show one workflow in detail")

    p_dispatch = sub.add_parser("dispatch", help="Route and execute a Linux operations request")
    p_dispatch.add_argument("--workflow", help="Optional explicit workflow id")
    p_dispatch.add_argument("--objective", help="Natural-language objective to route and execute")
    p_dispatch.add_argument("--execute", action="store_true", help="Execute the workflow after dispatch")
    p_dispatch.add_argument("--confirmation-id", help="Resolve a pending confirmation request")
    p_dispatch.add_argument("--answer", choices=["yes", "no"], help="Answer for a pending confirmation request")
    p_dispatch.add_argument("--reason", help="Reason required by some high-risk confirmations")

    p_console = sub.add_parser("console", help="Start the interactive Linux operations console")
    _add_provider_override_args(p_console)

    p_provider_status = sub.add_parser("provider-status", help="Show active model provider readiness")
    _add_provider_override_args(p_provider_status)

    sub.add_parser("auth", help="Show the repository auth.json path and active provider settings")

    return parser


def main(argv: Sequence[str] | None = None, *, apply_startup_defaults: bool = True) -> int:
    root = _repo_root()
    parser = build_parser()
    try:
        auth_profile = load_auth_profile(root)
        command = _prepare_argv(argv, parser=parser, root=root, apply_startup_defaults=apply_startup_defaults)
        args = parser.parse_args(command)
        auth_overrides = auth_env_overrides(auth_profile)

        if args.command == "provider-status":
            merged = dict(auth_overrides)
            merged.update(_provider_override_env(args))
            with _temporary_env(merged):
                _print_provider_status(provider_status())
                _print_auth_file_status(root=root)
            return 0

        if args.command == "console":
            defaults = ConsoleDefaults(
                provider=str(getattr(args, "provider", "") or "").strip() or auth_profile.provider or None,
                model=str(getattr(args, "model", "") or "").strip() or auth_profile.model or None,
                api_base_url=str(getattr(args, "api_base_url", "") or "").strip() or auth_profile.api_base_url or None,
                api_key=str(getattr(args, "api_key", "") or "").strip() or auth_profile.api_key or None,
            )
            merged = dict(auth_overrides)
            merged.update(_provider_override_env(args))
            with _temporary_env(merged):
                return console_mod.run_console(
                    parser=parser,
                    command_runner=lambda nested_argv: main(nested_argv, apply_startup_defaults=False),
                    defaults=defaults,
                    auth_path=auth_profile.path,
                )

        if args.command == "auth":
            _print_auth_file_status(root=root)
            return 0

        if args.command == "workflow":
            _system_cfg, workflows_cfg = load_repo_configs(root)
            if args.workflow:
                workflow = next(
                    (
                        row for row in workflows_cfg.get("workflows", [])
                        if isinstance(row, dict) and str(row.get("id", "")).strip() == str(args.workflow).strip()
                    ),
                    None,
                )
                if workflow is None:
                    raise ValueError(f"Unknown workflow: {args.workflow}")
                print(f"id: {workflow['id']}")
                print(f"category: {workflow.get('category', '-')}")
                print(f"summary: {workflow.get('summary', '-')}")
                print(f"handoff: {' -> '.join(workflow.get('handoff_chain', []))}")
                print(f"checks: {', '.join(workflow.get('acceptance_checks', []))}")
                if workflow.get("example_prompts"):
                    print("examples:")
                    for prompt in workflow["example_prompts"]:
                        print(f"- {prompt}")
                return 0
            for workflow in list_workflows(workflows_cfg):
                print(f"{workflow['id']} [{workflow.get('category', '-')}] - {workflow.get('summary', '-')}")
            return 0

        if args.command == "dispatch":
            if args.confirmation_id:
                if not args.answer:
                    raise ValueError("--answer is required with --confirmation-id")
                result = resolve_confirmation(
                    repo_root=root,
                    confirmation_id=args.confirmation_id,
                    answer=args.answer,
                    reason=args.reason,
                )
                print(f"confirmation_id: {result.confirmation_id}")
                print(f"status: {result.status}")
                print(f"transcript_file: {result.transcript_file}")
                print(f"final_output_file: {result.final_output_file}")
                print("")
                print(result.final_output)
                return 0

            if not args.objective:
                raise ValueError("--objective is required unless you are resolving a confirmation.")

            runtime = load_runtime_bundle(root=root)
            bundle = dispatch_and_maybe_execute(
                root=root,
                objective=args.objective,
                workflow_id=args.workflow,
                runtime=runtime,
                execute=bool(args.execute),
                progress_callback=_make_execution_progress_callback() if args.execute else None,
            )
            result = bundle.dispatch_result
            print(f"run_id: {result.run_id}")
            print(f"workflow_id: {result.workflow_id}")
            print(f"category: {result.category}")
            print(f"agents: {', '.join(result.agents)}")
            print(f"handoff: {' -> '.join(result.handoff_chain)}")
            print(f"checks: {', '.join(result.acceptance_checks)}")
            print(f"log_file: {result.log_file}")
            if bundle.execution_result is not None:
                execution = bundle.execution_result
                print(f"status: {execution.status}")
                if execution.confirmation_id:
                    print(f"confirmation_id: {execution.confirmation_id}")
                print(f"transcript_file: {execution.transcript_file}")
                print(f"final_output_file: {execution.final_output_file}")
                print(f"group_chat_file: {execution.group_chat_file}")
                print("")
                print(execution.final_output)
            return 0

        if args.command is None:
            parser.print_help()
            return 0

        raise ValueError(f"Unknown command: {args.command}")
    except ValueError as exc:
        print(f"Input error: {exc}")
        return 2
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 2
    except ProviderError as exc:
        print(f"Provider error: {exc}")
        return 2
    except OSError as exc:
        print(f"Runtime error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
