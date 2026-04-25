from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .intent_parser import parse_objective
from .runtime_layout import RuntimeLayout, repo_runtime_layout


@dataclass(frozen=True)
class DispatchResult:
    run_id: str
    workflow_id: str
    objective: str
    category: str
    agents: list[str]
    handoff_chain: list[str]
    acceptance_checks: list[str]
    log_file: Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_workflows(skills_cfg: dict[str, Any], category: str | None = None) -> list[dict[str, Any]]:
    rows = [
        workflow for workflow in skills_cfg.get("workflows", [])
        if isinstance(workflow, dict)
    ]
    if category:
        rows = [row for row in rows if str(row.get("category", "")).strip() == category]
    return sorted(rows, key=lambda row: str(row.get("id", "")))


def workflow_config(skills_cfg: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    workflow = next(
        (
            row for row in skills_cfg.get("workflows", [])
            if isinstance(row, dict) and str(row.get("id", "")).strip() == workflow_id
        ),
        None,
    )
    if workflow is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    return workflow


def dispatch(
    *,
    system_cfg: dict[str, Any],
    skills_cfg: dict[str, Any],
    objective: str,
    root: Path,
    workflow_id: str | None = None,
    runtime_layout: RuntimeLayout | None = None,
) -> DispatchResult:
    intent = parse_objective(objective, workflow_hint=workflow_id)
    workflow = workflow_config(skills_cfg, intent.workflow_id)

    now = _utc_now()
    run_id = f"run-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    layout = runtime_layout or repo_runtime_layout(root)
    layout.ensure_dirs()
    log_file = layout.log_file(run_id)

    payload = {
        "run_id": run_id,
        "timestamp_utc": now.isoformat(),
        "objective": objective,
        "workflow_id": intent.workflow_id,
        "category": workflow.get("category"),
        "routed_operation": intent.operation,
        "intent_entities": intent.entities,
        "acceptance_checks": workflow.get("acceptance_checks", []),
        "default_agents": workflow.get("default_agents", []),
        "handoff_chain": workflow.get("handoff_chain", []),
        "runtime_context": layout.describe(),
    }
    log_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    layout.active_file.write_text(
        "\n".join(
            [
                "# Active Session",
                "",
                f"- run_id: {run_id}",
                f"- workflow_id: {intent.workflow_id}",
                f"- category: {workflow.get('category', '-')}",
                f"- routed_operation: {intent.operation}",
                f"- objective: {objective}",
                f"- handoff_chain: {', '.join(workflow.get('handoff_chain', []))}",
                f"- acceptance_checks: {', '.join(workflow.get('acceptance_checks', []))}",
                f"- log_file: {log_file.as_posix()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return DispatchResult(
        run_id=run_id,
        workflow_id=intent.workflow_id,
        objective=objective,
        category=str(workflow.get("category", "")).strip(),
        agents=list(workflow.get("default_agents", [])),
        handoff_chain=list(workflow.get("handoff_chain", [])),
        acceptance_checks=list(workflow.get("acceptance_checks", [])),
        log_file=log_file,
    )
