from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .command_generator import plan_commands
from .confirmation_store import create_confirmation, load_confirmation, mark_confirmation
from .feedback_agent import (
    format_block_response,
    format_confirmation_response,
    format_execution_response,
    parse_preview,
)
from .intent_parser import parse_objective
from .linux_executor import execute_commands
from .ops_types import AgentTurn, CommandPlan, Intent, PlannedCommand
from .runtime_layout import RuntimeLayout, repo_runtime_layout
from .security_agent import assess_intent


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class WorkflowExecutionResult:
    transcript_file: Path
    final_output_file: Path
    group_chat_file: Path
    turns: list[AgentTurn]
    final_output: str
    status: str
    confirmation_id: str | None = None


@dataclass(frozen=True)
class ConfirmationExecutionResult:
    confirmation_id: str
    transcript_file: Path
    final_output_file: Path
    final_output: str
    status: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _emit(progress_callback: ProgressCallback | None, payload: dict[str, Any]) -> None:
    if progress_callback is None:
        return
    progress_callback(payload)


def _agent_turn(agent_id: str, title: str, output_text: str) -> AgentTurn:
    return AgentTurn(agent_id=agent_id, title=title, output_text=output_text)


def _intent_summary(intent: Intent) -> str:
    parts = [
        f"workflow_id: {intent.workflow_id}",
        f"operation: {intent.operation}",
        f"confidence: {intent.confidence:.2f}",
        f"rationale: {intent.rationale}",
    ]
    if intent.entities:
        parts.append(f"entities: {json.dumps(intent.entities, ensure_ascii=False)}")
    return "\n".join(parts)


def _security_summary(decision: Any) -> str:
    lines = [
        f"decision: {decision.decision}",
        f"risk_level: {decision.risk_level}",
        f"reason: {decision.reason}",
    ]
    if decision.impacts:
        lines.append("impacts:")
        lines.extend(f"- {impact}" for impact in decision.impacts)
    if decision.requires_reason:
        lines.append("requires_reason: true")
    return "\n".join(lines)


def _command_summary(plan: CommandPlan) -> str:
    lines = [
        f"summary: {plan.summary}",
        f"parser_kind: {plan.parser_kind}",
    ]
    if plan.preview_commands:
        lines.append("preview_commands:")
        lines.extend(f"- {command.command}" for command in plan.preview_commands)
    if plan.execution_commands:
        lines.append("execution_commands:")
        lines.extend(f"- {command.command}" for command in plan.execution_commands)
    if plan.deferred_action:
        lines.append(f"deferred_action: {plan.deferred_action}")
    return "\n".join(lines)


def _write_transcript(
    *,
    layout: RuntimeLayout,
    run_id: str,
    workflow_id: str,
    objective: str,
    turns: list[AgentTurn],
    status: str,
) -> tuple[Path, Path]:
    transcript_file = layout.transcript_dir / f"{run_id}.md"
    group_chat_file = layout.transcript_dir.parent / "group-chat-recaps" / f"{run_id}.md"
    group_chat_file.parent.mkdir(parents=True, exist_ok=True)

    transcript_lines = [
        f"# Workflow Transcript {run_id}",
        "",
        f"- generated_at_utc: {_utc_now().isoformat()}",
        f"- workflow_id: {workflow_id}",
        f"- objective: {objective}",
        f"- status: {status}",
        "",
    ]
    for turn in turns:
        transcript_lines.extend(
            [
                f"## {turn.agent_id}",
                "",
                turn.output_text.strip(),
                "",
            ]
        )
    transcript_file.write_text("\n".join(transcript_lines).strip() + "\n", encoding="utf-8")

    recap_lines = [
        f"# Group Chat Recap {run_id}",
        "",
        f"- workflow_id: {workflow_id}",
        f"- objective: {objective}",
        f"- status: {status}",
        "",
    ]
    for turn in turns:
        recap_lines.append(f"## {turn.title}")
        recap_lines.append("")
        recap_lines.append(turn.output_text.strip())
        recap_lines.append("")
    group_chat_file.write_text("\n".join(recap_lines).strip() + "\n", encoding="utf-8")
    return transcript_file, group_chat_file


def _append_execution_metadata(layout: RuntimeLayout, run_id: str, payload: dict[str, Any]) -> None:
    log_file = layout.log_file(run_id)
    if not log_file.exists():
        return
    current = json.loads(log_file.read_text(encoding="utf-8"))
    current["execution"] = payload
    log_file.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_confirmation_resolution(
    layout: RuntimeLayout,
    *,
    run_id: str,
    confirmation_id: str,
    status: str,
    answer: str,
    answer_reason: str | None,
    resolved_at_utc: str | None,
    transcript_file: Path,
    final_output_file: Path,
) -> None:
    _append_execution_metadata(
        layout,
        run_id,
        {
            "status": status,
            "confirmation_id": confirmation_id,
            "confirmation_answer": answer,
            "confirmation_reason": answer_reason,
            "resolved_at_utc": resolved_at_utc,
            "transcript_file": transcript_file.as_posix(),
            "final_output_file": final_output_file.as_posix(),
        },
    )


def _preview_to_commands(preview: dict[str, Any]) -> list[PlannedCommand]:
    commands: list[PlannedCommand] = []
    for candidate in preview.get("candidates", []):
        username = str(candidate.get("username", "")).strip()
        if not username:
            continue
        commands.append(
            PlannedCommand(
                name=f"delete-{username}",
                description=f"Delete user {username}.",
                command=f"userdel -r -- {username}",
            )
        )
    return commands


def execute_workflow(
    *,
    repo_root: Path,
    system_cfg: dict[str, Any],
    workflow_cfg: dict[str, Any],
    objective: str,
    run_id: str,
    runtime_layout: RuntimeLayout | None = None,
    progress_callback: ProgressCallback | None = None,
    **_: Any,
) -> WorkflowExecutionResult:
    layout = runtime_layout or repo_runtime_layout(repo_root)
    layout.ensure_dirs()
    warning_threshold = int(system_cfg.get("execution", {}).get("disk_warning_threshold", 80))
    timeout_seconds = int(system_cfg.get("execution", {}).get("default_timeout_seconds", 30))
    handoff = list(workflow_cfg.get("handoff_chain", []))
    turns: list[AgentTurn] = []

    _emit(
        progress_callback,
        {
            "event": "workflow_started",
            "run_id": run_id,
            "workflow_id": workflow_cfg.get("id"),
            "turn_count": len(handoff),
        },
    )

    intent = parse_objective(objective, workflow_hint=str(workflow_cfg.get("id", "")).strip() or None)
    _emit(progress_callback, {"event": "turn_started", "run_id": run_id, "turn_index": 1, "turn_count": len(handoff), "agent_id": handoff[0]})
    turns.append(_agent_turn("intent-parser", "Intent Parser", _intent_summary(intent)))
    _emit(progress_callback, {"event": "turn_completed", "run_id": run_id, "turn_index": 1, "turn_count": len(handoff), "agent_id": handoff[0]})

    assessment = assess_intent(intent)
    _emit(progress_callback, {"event": "turn_started", "run_id": run_id, "turn_index": 2, "turn_count": len(handoff), "agent_id": handoff[1]})
    turns.append(_agent_turn("security-guard", "Security Guard", _security_summary(assessment)))
    _emit(progress_callback, {"event": "turn_completed", "run_id": run_id, "turn_index": 2, "turn_count": len(handoff), "agent_id": handoff[1]})

    plan = plan_commands(intent, assessment)
    _emit(progress_callback, {"event": "turn_started", "run_id": run_id, "turn_index": 3, "turn_count": len(handoff), "agent_id": handoff[2]})
    turns.append(_agent_turn("command-planner", "Command Planner", _command_summary(plan)))
    _emit(progress_callback, {"event": "turn_completed", "run_id": run_id, "turn_index": 3, "turn_count": len(handoff), "agent_id": handoff[2]})

    confirmation_id: str | None = None
    status = "completed"
    if assessment.decision == "block":
        final_output = format_block_response(intent, assessment)
    elif assessment.decision == "confirm":
        preview_results = execute_commands(plan.preview_commands, timeout_seconds=timeout_seconds) if plan.preview_commands else []
        preview = parse_preview(plan, preview_results) if plan.preview_commands else {}
        commands = list(plan.execution_commands)
        if plan.deferred_action == "batch-delete-users":
            commands = _preview_to_commands(preview)
            if not commands:
                final_output = "没有找到匹配的用户，未创建确认请求。"
                status = "completed"
            else:
                record = create_confirmation(
                    layout=layout,
                    run_id=run_id,
                    intent=intent,
                    assessment=assessment,
                    plan=plan,
                    commands=commands,
                    preview=preview,
                )
                confirmation_id = record.confirmation_id
                status = "pending_confirmation"
                final_output = format_confirmation_response(
                    intent=intent,
                    assessment=assessment,
                    confirmation_id=confirmation_id,
                    preview=preview,
                )
        else:
            record = create_confirmation(
                layout=layout,
                run_id=run_id,
                intent=intent,
                assessment=assessment,
                plan=plan,
                commands=commands,
                preview=preview,
            )
            confirmation_id = record.confirmation_id
            status = "pending_confirmation"
            final_output = format_confirmation_response(
                intent=intent,
                assessment=assessment,
                confirmation_id=confirmation_id,
                preview=preview,
            )
    else:
        execution_results = execute_commands(plan.execution_commands, timeout_seconds=timeout_seconds)
        final_output = format_execution_response(
            intent=intent,
            assessment=assessment,
            plan=plan,
            results=execution_results,
            warning_threshold=warning_threshold,
        )

    _emit(progress_callback, {"event": "turn_started", "run_id": run_id, "turn_index": 4, "turn_count": len(handoff), "agent_id": handoff[3]})
    turns.append(_agent_turn("result-analyst", "Result Analyst", final_output))
    _emit(progress_callback, {"event": "turn_completed", "run_id": run_id, "turn_index": 4, "turn_count": len(handoff), "agent_id": handoff[3]})

    transcript_file, group_chat_file = _write_transcript(
        layout=layout,
        run_id=run_id,
        workflow_id=str(workflow_cfg.get("id", "")),
        objective=objective,
        turns=turns,
        status=status,
    )
    final_output_file = layout.output_dir / f"{run_id}.md"
    final_output_file.write_text(final_output.strip() + "\n", encoding="utf-8")

    _append_execution_metadata(
        layout,
        run_id,
        {
            "status": status,
            "transcript_file": transcript_file.as_posix(),
            "group_chat_file": group_chat_file.as_posix(),
            "final_output_file": final_output_file.as_posix(),
            "confirmation_id": confirmation_id,
        },
    )

    _emit(
        progress_callback,
        {
            "event": "workflow_completed",
            "run_id": run_id,
            "workflow_id": workflow_cfg.get("id"),
            "status": status,
        },
    )

    return WorkflowExecutionResult(
        transcript_file=transcript_file,
        final_output_file=final_output_file,
        group_chat_file=group_chat_file,
        turns=turns,
        final_output=final_output,
        status=status,
        confirmation_id=confirmation_id,
    )


def _plan_for_confirmation(operation: str, workflow_id: str) -> CommandPlan:
    parser_kind = "user-management"
    if operation == "chmod_recursive":
        parser_kind = "chmod"
    elif operation == "delete_path":
        parser_kind = "destructive-path"
    return CommandPlan(
        workflow_id=workflow_id,
        operation=operation,
        summary="Confirmation execution",
        parser_kind=parser_kind,
    )


def resolve_confirmation(
    *,
    repo_root: Path,
    confirmation_id: str,
    answer: str,
    reason: str | None = None,
    runtime_layout: RuntimeLayout | None = None,
) -> ConfirmationExecutionResult:
    layout = runtime_layout or repo_runtime_layout(repo_root)
    layout.ensure_dirs()
    record = load_confirmation(layout, confirmation_id)
    if record.status != "pending":
        raise ValueError(f"Confirmation {confirmation_id} is already {record.status}.")

    answer_clean = str(answer or "").strip().lower()
    if answer_clean not in {"yes", "no"}:
        raise ValueError("Confirmation answer must be yes or no.")
    if answer_clean == "yes" and record.requires_reason and not str(reason or "").strip():
        raise ValueError("This confirmation requires a reason.")

    transcript_file = layout.transcript_dir / f"{record.run_id}-{confirmation_id}.md"
    final_output_file = layout.output_dir / f"{record.run_id}-{confirmation_id}.md"

    if answer_clean == "no":
        updated = mark_confirmation(layout, record, answer=answer_clean, answer_reason=reason, status="rejected")
        final_output = "操作已取消，未执行任何高风险命令。"
        transcript_file.write_text(final_output + "\n", encoding="utf-8")
        final_output_file.write_text(final_output + "\n", encoding="utf-8")
        _append_confirmation_resolution(
            layout,
            run_id=record.run_id,
            confirmation_id=confirmation_id,
            status="rejected",
            answer=answer_clean,
            answer_reason=reason,
            resolved_at_utc=updated.resolved_at_utc,
            transcript_file=transcript_file,
            final_output_file=final_output_file,
        )
        return ConfirmationExecutionResult(
            confirmation_id=confirmation_id,
            transcript_file=transcript_file,
            final_output_file=final_output_file,
            final_output=final_output,
            status="rejected",
        )

    commands = [PlannedCommand(**command) for command in record.commands]
    results = execute_commands(commands)
    plan = _plan_for_confirmation(record.operation, record.workflow_id)
    intent = Intent(
        workflow_id=record.workflow_id,
        operation=record.operation,
        objective=record.objective,
        entities={},
        confidence=1.0,
        rationale="Confirmed execution path.",
    )
    final_output = format_execution_response(
        intent=intent,
        assessment=type("Assessment", (), {"risk_level": record.risk_level})(),
        plan=plan,
        results=results,
    )
    updated = mark_confirmation(layout, record, answer=answer_clean, answer_reason=reason, status="executed")
    transcript_file.write_text(final_output + "\n", encoding="utf-8")
    final_output_file.write_text(final_output + "\n", encoding="utf-8")
    _append_confirmation_resolution(
        layout,
        run_id=record.run_id,
        confirmation_id=confirmation_id,
        status="executed",
        answer=answer_clean,
        answer_reason=reason,
        resolved_at_utc=updated.resolved_at_utc,
        transcript_file=transcript_file,
        final_output_file=final_output_file,
    )
    return ConfirmationExecutionResult(
        confirmation_id=confirmation_id,
        transcript_file=transcript_file,
        final_output_file=final_output_file,
        final_output=final_output,
        status="executed",
    )


__all__ = [
    "ConfirmationExecutionResult",
    "WorkflowExecutionResult",
    "execute_workflow",
    "resolve_confirmation",
]
