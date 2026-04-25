from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_loader import load_system_config, load_workflows_catalog, validate_repository_integrity
from .engine import DispatchResult, dispatch, workflow_config
from .runtime_layout import repo_runtime_layout
from .workflow_executor import WorkflowExecutionResult, execute_workflow


@dataclass(frozen=True)
class RuntimeBundle:
    system_cfg: dict[str, Any]
    skills_cfg: dict[str, Any]


@dataclass(frozen=True)
class DispatchExecutionBundle:
    runtime: RuntimeBundle
    dispatch_result: DispatchResult
    execution_result: WorkflowExecutionResult | None = None


def load_repo_configs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    validate_repository_integrity(root, system, workflows)
    return system, workflows


def load_runtime_bundle(*, root: Path) -> RuntimeBundle:
    system_cfg, skills_cfg = load_repo_configs(root)
    return RuntimeBundle(system_cfg=system_cfg, skills_cfg=skills_cfg)


def skill_config(skills_cfg: dict[str, Any], *, workflow_id: str) -> dict[str, Any]:
    return workflow_config(skills_cfg, workflow_id)


def dispatch_and_maybe_execute(
    *,
    root: Path,
    objective: str,
    workflow_id: str | None = None,
    runtime: RuntimeBundle | None = None,
    execute: bool = False,
    progress_callback: Any | None = None,
    dispatch_impl: Any | None = None,
    execute_workflow_impl: Any | None = None,
) -> DispatchExecutionBundle:
    dispatch_fn = dispatch_impl or dispatch
    execute_fn = execute_workflow_impl or execute_workflow
    loaded_runtime = runtime or load_runtime_bundle(root=root)
    layout = repo_runtime_layout(root)

    dispatch_result = dispatch_fn(
        system_cfg=loaded_runtime.system_cfg,
        skills_cfg=loaded_runtime.skills_cfg,
        objective=objective,
        workflow_id=workflow_id,
        root=root,
        runtime_layout=layout,
    )

    execution_result = None
    if execute:
        execution_result = execute_fn(
            repo_root=root,
            system_cfg=loaded_runtime.system_cfg,
            workflow_cfg=workflow_config(loaded_runtime.skills_cfg, dispatch_result.workflow_id),
            objective=objective,
            run_id=dispatch_result.run_id,
            runtime_layout=layout,
            progress_callback=progress_callback,
        )

    return DispatchExecutionBundle(
        runtime=loaded_runtime,
        dispatch_result=dispatch_result,
        execution_result=execution_result,
    )


__all__ = [
    "DispatchExecutionBundle",
    "RuntimeBundle",
    "dispatch_and_maybe_execute",
    "load_repo_configs",
    "load_runtime_bundle",
    "skill_config",
]
