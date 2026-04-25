from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Decision = Literal["allow", "confirm", "block"]


@dataclass(frozen=True)
class Intent:
    workflow_id: str
    operation: str
    objective: str
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    rationale: str = ""


@dataclass(frozen=True)
class SecurityAssessment:
    decision: Decision
    risk_level: str
    reason: str
    impacts: list[str] = field(default_factory=list)
    requires_reason: bool = False


@dataclass(frozen=True)
class PlannedCommand:
    name: str
    command: str
    description: str
    allowed_returncodes: tuple[int, ...] = (0,)
    allow_failure: bool = False


@dataclass(frozen=True)
class CommandPlan:
    workflow_id: str
    operation: str
    summary: str
    parser_kind: str
    preview_parser_kind: str | None = None
    preview_commands: list[PlannedCommand] = field(default_factory=list)
    execution_commands: list[PlannedCommand] = field(default_factory=list)
    deferred_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandExecution:
    name: str
    command: str
    description: str
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    timed_out: bool = False


@dataclass(frozen=True)
class AgentTurn:
    agent_id: str
    title: str
    output_text: str

