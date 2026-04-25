# OpenTower Linux Ops

这是一个面向 Linux 运维场景的 CLI 多 agent 系统，当前只保留固定的多 agent 工作流：

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

项目当前只保留面向 Linux 运维的 5 个命令面：

- `workflow`
- `dispatch`
- `console`
- `provider-status`
- `auth`

## 已实现能力

- 磁盘与存储空间检查
- 文件 / 目录 / 内容检索
- 进程、服务、端口检查
- 普通用户创建、删除、加组
- 高危操作阻断
- 高风险操作二次确认

## 快速开始

```bash
python -m pip install -e .[dev]
```

推荐先准备本地 provider 配置：

```bash
cp auth.example.json auth.json
```

如果使用 PowerShell，也可以执行：

```powershell
Copy-Item auth.example.json auth.json
```

然后编辑仓库根目录的 `auth.json`，填写实际使用的 provider、model、`api_base_url` 和 `api_key`。

说明：

- 仓库提交的是 `auth.example.json` 模板文件
- 真正生效的是根目录本地文件 `auth.json`
- `auth.json` 已加入 `.gitignore`，不会进入版本库
- 如果 `auth.json` 不存在，CLI 首次启动时也会自动生成模板

可用下面两条命令检查配置是否生效：

```bash
python -m opentower_cli /auth
python -m opentower_cli /provider-status
```

比赛版设计说明文档：

- `比赛版设计说明文档.md`

## 最短使用路径

顶层 CLI 默认优先按自然语言任务处理，不需要先写 `dispatch`。

```bash
python -m opentower_cli 查看磁盘使用情况
python -m opentower_cli 找到所有 nginx 配置文件
python -m opentower_cli 哪些进程占用 80 端口
python -m opentower_cli 创建一个名为 dev01 的用户并加入 docker 组
```

显式命令模式只在输入以 `/` 开头时启用：

```bash
python -m opentower_cli /workflow
python -m opentower_cli /provider-status
python -m opentower_cli /auth
```

如果需要显式指定 `dispatch`，仍然支持：

```bash
python -m opentower_cli dispatch --objective "查看磁盘使用情况" --execute
python -m opentower_cli dispatch --objective "找到所有 nginx 配置文件" --execute
python -m opentower_cli dispatch --objective "哪些进程占用 80 端口" --execute
python -m opentower_cli dispatch --objective "创建一个名为 dev01 的用户并加入 docker 组" --execute
```

高危场景示例：

```bash
python -m opentower_cli dispatch --objective "删除 /etc 目录" --execute
python -m opentower_cli dispatch --objective "给所有文件 777 权限" --execute
python -m opentower_cli dispatch --objective "删除所有测试用户" --execute
```

如果系统要求二次确认，会返回 `confirmation_id`。继续执行或取消执行：

```bash
python -m opentower_cli dispatch --confirmation-id <id> --answer yes --reason "approved maintenance"
python -m opentower_cli dispatch --confirmation-id <id> --answer no
```

## 交互式控制台

```bash
python -m opentower_cli console
```

控制台优先使用本地规则把常见自然语言请求路由到真实 CLI 命令；必要时可以再使用配置的 provider 做兜底路由。
控制台默认就是自然语言输入，只有以 `/` 开头时才按显式命令处理，例如 `/workflow`、`/provider-status`、`/auth`。

## GitHub 上传说明

- 上传仓库时保留 `auth.example.json`，不要提交 `auth.json`
- 如果本地生成过运行日志、转录或确认记录，也不要把 `production/` 下的运行产物提交上去
- 当前仓库默认以 [README_CN.md](README_CN.md) 和 [比赛版设计说明文档.md](比赛版设计说明文档.md) 作为中文说明入口

## Provider 状态检查

```bash
python -m opentower_cli provider-status
```

## 测试

```bash
python -m pytest -q
```
