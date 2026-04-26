# OpenTower Linux Ops

OpenTower Linux Ops is a CLI-first Linux operations assistant. It accepts natural-language requests, routes them into a fixed multi-stage workflow, applies safety checks before execution, and returns structured, human-readable results.

This repository keeps the runtime surface intentionally narrow and audited. It focuses on a small set of Linux inspection and user-management tasks, model-assisted recovery for in-scope paraphrases, and structured handling for requests that fall outside the shipped workflow set or cross safety boundaries.

## What It Does

Current workflow surface:

- `disk-inspection`
  - `disk_usage`
  - `disk_usage_with_logs`
- `file-search`
  - `filename_search`
  - `content_search`
  - `inspect_permissions`
  - `tail_log` via read-only fallback
  - `recent_error_scan` via read-only fallback
  - `delete_path` and `chmod_recursive` remain guarded by the security layer
- `process-port-inspection`
  - `port_lookup`
  - `top_memory`
  - `service_status`
  - `top_cpu` via read-only fallback
  - `load_average` via read-only fallback
  - `uptime_summary` via read-only fallback
- `user-management`
  - `list_users`
  - `inspect_user`
  - `create_user`
  - `add_user_to_group`
  - `delete_user`
  - `batch_delete_users`

The fixed agent chain is:

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

## Current Scope

OpenTower keeps the runtime surface intentionally narrow and explicit.

Today it focuses on:

- Linux inspection and troubleshooting requests that map onto the shipped workflow catalog
- confirmation-gated user and permission operations
- structured routing, safety checks, command planning, and readable result summaries
- structured handling when a request does not map onto the current workflow set

## Routing Model

Every request goes through a three-stage routing chain:

1. `local_rule`
   Deterministic parsing for the shipped Linux ops workflows.
2. `llm_normalizer`
   Maps in-scope paraphrases back onto already-implemented operations.
3. `fallback_research`
   Read-only recovery for a small set of low-risk inspection tasks.

Every dispatch result exposes:

- `resolution_status`
- `resolution_source`
- `resolution_reason`

Current resolution sources are:

- `local_rule`
- `llm_normalizer`
- `fallback_research`

## Safety Model

- High-risk writes are either blocked or forced through explicit confirmation.
- `create_user` and `add_user_to_group` now go through the confirmation flow instead of executing immediately.
- Critical destructive requests such as deleting core system paths are blocked before command generation.
- Fallback behavior is read-only by design.

The current architecture also centralizes operation metadata and confirmation replay context. The normalizer, fallback path, and confirmation resolution now share the same operation catalog and persisted execution context, which reduces drift across routing and replay stages.

## CLI Surface

User-facing commands:

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

Natural-language input is the default entrypoint. These are equivalent ways to use the tool:

```bash
python -m opentower_cli "show disk usage"
python -m opentower_cli "find nginx config files"
python -m opentower_cli "check sshd service status"
python -m opentower_cli "show cpu usage"
```

```bash
python -m opentower_cli dispatch --objective "show disk usage" --execute
```

With no arguments, the CLI starts the interactive console:

```bash
python -m opentower_cli
```

Slash-prefixed commands are also accepted:

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

## Installation

Requires Python `3.11+`.

Install in editable mode:

```bash
python -m pip install -e .[dev]
```

## Provider Configuration

Create a local provider profile:

```bash
cp auth.example.json auth.json
```

On PowerShell:

```powershell
Copy-Item auth.example.json auth.json
```

Then edit `auth.json` and set the provider, model, API base URL, and API key you want to use.

Supported providers:

- `anthropic`
- `openai-compatible`
- `ollama`

For `openai-compatible` endpoints, OpenTower can auto-select a chat-capable model when `model` is omitted and the provider exposes `/models`.

Useful checks:

```bash
python -m opentower_cli auth
python -m opentower_cli provider-status
```

## Example Requests

Read-only inspection:

```bash
python -m opentower_cli "show disk usage"
python -m opentower_cli "search for database in /etc"
python -m opentower_cli "check sshd service status"
python -m opentower_cli "show load average"
python -m opentower_cli "tail the latest syslog log"
```

Confirmation-gated requests:

```bash
python -m opentower_cli "create user dev01"
python -m opentower_cli "add user dev01 to docker group"
python -m opentower_cli "chmod 777 /tmp/demo"
```

## Evaluation and Verification

Current local verification for the `2026-04-26` snapshot:

- `python -m pytest -q` -> `95 passed`
- `python scripts/run_nl_eval.py --fixture-profile extended` -> `2009/2009 passed`
- `python scripts/run_nl_eval.py --fixture-profile core` -> `416/416 passed`
- `python scripts/run_nl_eval.py --fixture-profile model` -> `228/228 passed`
- `python scripts/run_nl_eval.py --fixture-profile model --with-model --limit 20` -> `20/20 passed`
- `python scripts/run_wsl_smoke.py` -> `10/10 passed`
- a local rounded WSL real-execution report derived from a completed 543-case run reached `499/500 passed`

The NL evaluation corpus is layered into:

- `extended`
- `core`
- `model`

`--with-model` keeps the same replay harness but enables the configured normalizer and fallback model chain.

## Repository Notes

- Commit `auth.example.json`, not `auth.json`.
- Runtime outputs under `production/` are local artifacts unless you intentionally want to version them.
- Evaluation corpus expansion is PR-able as test coverage. New runtime behavior should still land through reviewed parser, normalizer, fallback, planner, or safety changes.
- Chinese documentation lives in [README_CN.md](README_CN.md).
- The judge-facing overview lives in [比赛版设计说明文档.md](比赛版设计说明文档.md).
