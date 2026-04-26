# OpenTower Linux Ops

OpenTower Linux Ops 是一个面向 Linux 运维场景的 CLI-first 自然语言助手。它接收自然语言请求，把请求路由到固定工作流，在执行前完成安全判断，并返回结构化、可读的结果。

这个仓库刻意保持收敛，运行面保持在可审计、可验证的范围内。它围绕少量已审计的 Linux 运维操作构建：支持固定范围的检查类任务和用户管理任务，对范围内但表达方式不同的请求做模型辅助归一化，并对超出当前工作流集合或触发安全边界的请求返回结构化处理结果。

## 当前能做什么

当前工作流能力如下：

- `disk-inspection`
  - `disk_usage`
  - `disk_usage_with_logs`
- `file-search`
  - `filename_search`
  - `content_search`
  - `inspect_permissions`
  - `tail_log`，通过只读 fallback 提供
  - `recent_error_scan`，通过只读 fallback 提供
  - `delete_path` 与 `chmod_recursive` 仍然受安全层约束
- `process-port-inspection`
  - `port_lookup`
  - `top_memory`
  - `service_status`
  - `top_cpu`，通过只读 fallback 提供
  - `load_average`，通过只读 fallback 提供
  - `uptime_summary`，通过只读 fallback 提供
- `user-management`
  - `list_users`
  - `inspect_user`
  - `create_user`
  - `add_user_to_group`
  - `delete_user`
  - `batch_delete_users`

固定 agent 链路为：

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

## 当前范围

OpenTower 当前保持一个明确、可控的运行范围。

目前重点覆盖：

- 能映射到已内置 workflow catalog 的 Linux 检查与排障请求
- 需要显式确认的用户与权限类操作
- 结构化路由、安全判断、命令规划和可读结果摘要
- 对未命中当前工作流集合的请求返回结构化处理结果

## 路由模型

每个请求都会经过三层路由链：

1. `local_rule`
   本地确定性规则，负责命中仓库当前正式支持的工作流。
2. `llm_normalizer`
   把范围内的同义改写重新映射回已实现操作。
3. `fallback_research`
   只处理少量低风险、只读的补救型观察任务。

每次 dispatch 都会返回：

- `resolution_status`
- `resolution_source`
- `resolution_reason`

当前 `resolution_source` 只会来自：

- `local_rule`
- `llm_normalizer`
- `fallback_research`

## 安全模型

- 高风险写操作要么被直接阻断，要么进入显式确认流。
- `create_user` 和 `add_user_to_group` 现在统一进入确认流，不再直接执行。
- 删除关键系统路径这类破坏性请求会在命令规划之前直接被阻断。
- fallback 路径按设计只允许只读行为。

当前架构还进一步统一了 operation 元数据和 confirmation replay 上下文。normalizer、fallback 和确认执行现在共享同一份 operation catalog，并在确认记录中持久化原始执行上下文，从而降低路由与回放之间的能力漂移。

## CLI 命令面

对外命令只有：

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

自然语言是默认入口。下面两种写法都可以：

```bash
python -m opentower_cli "查看磁盘使用情况"
python -m opentower_cli "找到所有 nginx 配置文件"
python -m opentower_cli "检查 sshd 服务状态"
python -m opentower_cli "show cpu usage"
```

```bash
python -m opentower_cli dispatch --objective "show disk usage" --execute
```

不带参数启动时，会进入交互式 console：

```bash
python -m opentower_cli
```

也支持 `/` 开头的显式命令：

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

## 安装

需要 Python `3.11+`。

开发模式安装：

```bash
python -m pip install -e .[dev]
```

## Provider 配置

先复制本地配置模板：

```bash
cp auth.example.json auth.json
```

PowerShell 下：

```powershell
Copy-Item auth.example.json auth.json
```

然后编辑 `auth.json`，填写实际使用的 provider、model、API base URL 和 API key。

当前支持的 provider：

- `anthropic`
- `openai-compatible`
- `ollama`

对 `openai-compatible` 端点，如果没有显式填写 `model` 且 provider 提供了 `/models`，OpenTower 会自动选择一个可用的 chat 模型。

常用检查命令：

```bash
python -m opentower_cli auth
python -m opentower_cli provider-status
```

## 示例请求

只读检查类：

```bash
python -m opentower_cli "查看磁盘使用情况"
python -m opentower_cli "搜索 /etc 下包含 database 的文件"
python -m opentower_cli "检查 sshd 服务状态"
python -m opentower_cli "show load average"
python -m opentower_cli "tail the latest syslog log"
```

需要确认的请求：

```bash
python -m opentower_cli "create user dev01"
python -m opentower_cli "add user dev01 to docker group"
python -m opentower_cli "chmod 777 /tmp/demo"
```

## 评测与验证

针对 `2026-04-26` 快照，当前本地验证结果为：

- `python -m pytest -q` -> `95 passed`
- `python scripts/run_nl_eval.py --fixture-profile extended` -> `2009/2009 passed`
- `python scripts/run_nl_eval.py --fixture-profile core` -> `416/416 passed`
- `python scripts/run_nl_eval.py --fixture-profile model` -> `228/228 passed`
- `python scripts/run_nl_eval.py --fixture-profile model --with-model --limit 20` -> `20/20 passed`
- `python scripts/run_wsl_smoke.py` -> `10/10 passed`
- 一轮已完成的 543 条 WSL 真实执行结果裁出的整数版 500 条本地报告达到 `499/500 passed`

当前自然语言评测集分为三层：

- `extended`
- `core`
- `model`

`--with-model` 会在相同回放框架下启用已配置的 normalizer 与 fallback 模型链路。

## 仓库说明

- 提交时保留 `auth.example.json`，不要提交 `auth.json`。
- `production/` 下的运行输出默认视为本地产物，除非你明确要版本化它们。
- 扩充评测语料可以直接作为测试覆盖提交。新的运行时行为仍应通过 parser、normalizer、fallback、planner 或 safety 相关代码变更进入主线。
- 英文说明见 [README.md](README.md)。
- 面向评委的说明见 [比赛版设计说明文档.md](比赛版设计说明文档.md)。
