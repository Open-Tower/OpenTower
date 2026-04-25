from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opentower_cli import cli as cli_mod
from opentower_cli.config_loader import load_system_config, load_workflows_catalog, validate_repository_integrity
from opentower_cli.engine import dispatch
from opentower_cli.ops_types import CommandExecution
from opentower_cli.runtime_layout import repo_runtime_layout
from opentower_cli.workflow_executor import execute_workflow, resolve_confirmation


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _seed_run_log(layout, run_id: str, objective: str) -> None:
    payload = {
        "run_id": run_id,
        "objective": objective,
        "workflow_id": "file-search",
    }
    layout.log_file(run_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_load_configs() -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    validate_repository_integrity(root, system, workflows)
    assert system["system"]["name"] == "OpenTower Linux Ops"
    assert len(workflows["workflows"]) == 4


def test_dispatch_writes_log(tmp_path) -> None:
    source_root = repo_root()
    system = load_system_config(source_root)
    workflows = load_workflows_catalog(source_root)

    result = dispatch(
        system_cfg=system,
        skills_cfg=workflows,
        objective="找到所有 nginx 配置文件",
        root=tmp_path,
    )
    assert result.log_file.exists()
    assert result.workflow_id == "file-search"
    payload = json.loads(result.log_file.read_text(encoding="utf-8"))
    assert payload["workflow_id"] == "file-search"
    assert payload["routed_operation"] == "filename_search"


def test_execute_workflow_blocks_critical_delete(tmp_path) -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "file-search"),
        objective="删除 /etc 目录",
        run_id="run-block",
        runtime_layout=layout,
    )

    assert result.status == "completed"
    assert "操作已拦截" in result.final_output
    assert result.confirmation_id is None


def test_execute_workflow_creates_confirmation_for_high_risk_request(tmp_path) -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "file-search"),
        objective="给所有文件 777 权限",
        run_id="run-confirm",
        runtime_layout=layout,
    )

    assert result.status == "pending_confirmation"
    assert result.confirmation_id is not None
    assert layout.confirmation_file(result.confirmation_id).exists()


def test_resolve_confirmation_can_reject_request(tmp_path) -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()
    _seed_run_log(layout, "run-confirm-reject", "给所有文件 777 权限")

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "file-search"),
        objective="给所有文件 777 权限",
        run_id="run-confirm-reject",
        runtime_layout=layout,
    )

    confirmation = resolve_confirmation(
        repo_root=tmp_path,
        confirmation_id=result.confirmation_id,
        answer="no",
        runtime_layout=layout,
    )

    assert confirmation.status == "rejected"
    assert "操作已取消" in confirmation.final_output
    payload = json.loads(layout.log_file("run-confirm-reject").read_text(encoding="utf-8"))
    assert payload["execution"]["status"] == "rejected"
    assert payload["execution"]["confirmation_answer"] == "no"


def test_resolve_confirmation_updates_run_log_after_execution(monkeypatch, tmp_path) -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()
    _seed_run_log(layout, "run-confirm-execute", "删除 /tmp/foo")

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "file-search"),
        objective="删除 /tmp/foo",
        run_id="run-confirm-execute",
        runtime_layout=layout,
    )

    monkeypatch.setattr(
        "opentower_cli.workflow_executor.execute_commands",
        lambda commands, *args, **kwargs: [
            CommandExecution(
                name="delete-path",
                command="rm -rf -- /tmp/foo",
                description="Delete the requested path recursively.",
                stdout="",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
            )
        ],
    )

    confirmation = resolve_confirmation(
        repo_root=tmp_path,
        confirmation_id=result.confirmation_id,
        answer="yes",
        reason="cleanup test path",
        runtime_layout=layout,
    )

    assert confirmation.status == "executed"
    payload = json.loads(layout.log_file("run-confirm-execute").read_text(encoding="utf-8"))
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["confirmation_answer"] == "yes"
    assert payload["execution"]["confirmation_reason"] == "cleanup test path"


def test_execute_workflow_formats_disk_summary(monkeypatch, tmp_path) -> None:
    root = repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()

    fake_results = [
        CommandExecution(
            name="disk-usage",
            command="df -h",
            description="Inspect mounted filesystem usage.",
            stdout="Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       100G   45G   55G  45% /\n/dev/sda2       200G  170G   30G  85% /home\n",
            stderr="",
            returncode=0,
            duration_seconds=0.1,
        ),
        CommandExecution(
            name="block-devices",
            command="lsblk",
            description="Inspect block devices and mount points.",
            stdout="",
            stderr="",
            returncode=0,
            duration_seconds=0.1,
        ),
    ]

    monkeypatch.setattr("opentower_cli.workflow_executor.execute_commands", lambda commands, timeout_seconds=30: fake_results)

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "disk-inspection"),
        objective="查看磁盘使用情况",
        run_id="run-disk",
        runtime_layout=layout,
    )

    assert result.status == "completed"
    assert "/dev/sda2 (/home) 已用 85%" in result.final_output


def test_provider_status_cli(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli_mod, "_repo_root", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = cli_mod.main(["provider-status"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "provider: anthropic" in captured.out
    assert "execute_ready: false" in captured.out
    assert "auth_file:" in captured.out


def test_main_prefers_natural_language_cli_input(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(cli_mod, "_repo_root", lambda: tmp_path)

    fake_bundle = SimpleNamespace(
        dispatch_result=SimpleNamespace(
            run_id="run-nl",
            workflow_id="disk-inspection",
            category="inspect",
            agents=["intent-parser", "security-guard", "command-planner", "result-analyst"],
            handoff_chain=["intent-parser", "security-guard", "command-planner", "result-analyst"],
            acceptance_checks=["df_parsed"],
            log_file=tmp_path / "run-nl.json",
        ),
        execution_result=SimpleNamespace(
            status="completed",
            confirmation_id=None,
            transcript_file=tmp_path / "run-nl.md",
            final_output_file=tmp_path / "run-nl-out.md",
            group_chat_file=tmp_path / "run-nl-group.md",
            final_output="done",
        ),
    )
    captured_call: dict[str, object] = {}

    monkeypatch.setattr(cli_mod, "load_runtime_bundle", lambda *, root: SimpleNamespace())

    def _fake_dispatch_and_maybe_execute(**kwargs):
        captured_call.update(kwargs)
        return fake_bundle

    monkeypatch.setattr(cli_mod, "dispatch_and_maybe_execute", _fake_dispatch_and_maybe_execute)

    rc = cli_mod.main(["查看磁盘使用情况"], apply_startup_defaults=False)
    output = capsys.readouterr().out

    assert rc == 0
    assert captured_call["objective"] == "查看磁盘使用情况"
    assert captured_call["execute"] is True
    assert "workflow_id: disk-inspection" in output


def test_main_accepts_slash_prefixed_provider_status(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(cli_mod, "_repo_root", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    rc = cli_mod.main(["/provider-status"], apply_startup_defaults=False)
    output = capsys.readouterr().out

    assert rc == 0
    assert "provider: anthropic" in output
    assert "auth_file:" in output
