# OpenTower Linux Ops

CLI-first Linux operations system built around a fixed multi-agent workflow:

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

The project is intentionally narrow. The shipped product surface is:

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

## What It Supports

The first release implements the required hackathon baseline:

- Disk and storage inspection
- File and directory search
- Process and port inspection
- Normal user creation / deletion / group updates
- High-risk action blocking
- Secondary confirmation for dangerous but recoverable actions

Examples:

```bash
python -m opentower_cli /workflow
python -m opentower_cli dispatch --objective "查看磁盘使用情况" --execute
python -m opentower_cli dispatch --objective "找到所有 nginx 配置文件" --execute
python -m opentower_cli dispatch --objective "哪些进程占用 80 端口" --execute
python -m opentower_cli dispatch --objective "创建一个名为 dev01 的用户并加入 docker 组" --execute
```

High-risk examples:

```bash
python -m opentower_cli dispatch --objective "删除 /etc 目录" --execute
python -m opentower_cli dispatch --objective "给所有文件 777 权限" --execute
python -m opentower_cli dispatch --objective "删除所有测试用户" --execute
```

If a request requires confirmation, the tool returns a `confirmation_id`. Resolve it with:

```bash
python -m opentower_cli dispatch --confirmation-id <id> --answer yes --reason "approved maintenance"
python -m opentower_cli dispatch --confirmation-id <id> --answer no
```

## Setup

```bash
python -m pip install -e .[dev]
```

Prepare local provider configuration first:

```bash
cp auth.example.json auth.json
```

Then edit the repository-root `auth.json` and fill the active provider, model, `api_base_url`, and `api_key`.

Notes:

- `auth.example.json` is the committed template
- `auth.json` is the local runtime file actually used by the CLI
- `auth.json` is ignored by Git and should not be pushed
- If `auth.json` is missing, the CLI can also generate a template automatically on first launch

Verify configuration with:

```bash
python -m opentower_cli /auth
python -m opentower_cli /provider-status
```

Competition design document:

- `比赛版设计说明文档.md`

## Fastest Path

The top-level CLI is natural-language-first. You can run common tasks directly:

```bash
python -m opentower_cli 查看磁盘使用情况
python -m opentower_cli 找到所有 nginx 配置文件
python -m opentower_cli 哪些进程占用 80 端口
python -m opentower_cli 创建一个名为 dev01 的用户并加入 docker 组
```

Use slash-prefixed input only when you want explicit command mode:

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

## Console

```bash
python -m opentower_cli console
```

The console prefers local routing for common Linux ops requests and can fall back to the configured provider router when needed.
Natural language is the default input mode. Use slash commands such as `/workflow`, `/provider-status`, and `/auth` only when you want explicit CLI control.

## GitHub Upload Notes

- Keep `auth.example.json` in the repository and keep `auth.json` local only
- Do not push local runtime artifacts under `production/`
- The primary Chinese entry points for reviewers are [README_CN.md](README_CN.md) and [比赛版设计说明文档.md](比赛版设计说明文档.md)

## Provider Check

```bash
python -m opentower_cli provider-status
```

Provider configuration is still supported for console routing or future prompt-based extensions, but the core Linux execution path is deterministic and rule-driven.

## Verification

```bash
python -m pytest -q
```
