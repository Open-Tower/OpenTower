from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    """Raised when a required config cannot be loaded or is invalid."""


REQUIRED_WORKFLOW_KEYS = {
    "id",
    "category",
    "summary",
    "default_agents",
    "handoff_chain",
    "acceptance_checks",
}
DEFINITION_DIRNAME = ".opentower"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a mapping: {path}")
    return data


def _require_string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"{label} must be a non-empty list of strings")
    return value


def _agent_doc_exists(root: Path, agent_id: str, extra_definition_roots: list[Path]) -> bool:
    if (root / DEFINITION_DIRNAME / "agents" / f"{agent_id}.md").exists():
        return True
    return any((definition_root / "agents" / f"{agent_id}.md").exists() for definition_root in extra_definition_roots)


def _workflow_doc_exists(root: Path, workflow_id: str, extra_definition_roots: list[Path]) -> bool:
    if (root / DEFINITION_DIRNAME / "skills" / workflow_id / "SKILL.md").exists():
        return True
    return any((definition_root / "skills" / workflow_id / "SKILL.md").exists() for definition_root in extra_definition_roots)


def load_system_config(root: Path) -> dict[str, Any]:
    data = _load_yaml(root / "org" / "system.yaml")
    system = data.get("system")
    agents = data.get("agents")
    execution = data.get("execution")
    if not isinstance(system, dict):
        raise ConfigError("org/system.yaml must contain a system mapping")
    if not isinstance(agents, list) or not agents:
        raise ConfigError("org/system.yaml must contain a non-empty agents list")
    if not isinstance(execution, dict):
        raise ConfigError("org/system.yaml must contain an execution mapping")

    seen_agents: set[str] = set()
    for agent in agents:
        if not isinstance(agent, dict):
            raise ConfigError("Each agent entry must be a mapping")
        agent_id = str(agent.get("id", "")).strip()
        if not agent_id:
            raise ConfigError("Each agent must define a non-empty id")
        if agent_id in seen_agents:
            raise ConfigError(f"Duplicate agent id: {agent_id}")
        seen_agents.add(agent_id)
        if not str(agent.get("role", "")).strip():
            raise ConfigError(f"Agent '{agent_id}' must define a role")
    return data


def load_workflows_catalog(root: Path) -> dict[str, Any]:
    data = _load_yaml(root / "org" / "skills.yaml")
    workflows = data.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise ConfigError("org/skills.yaml must contain a non-empty workflows list")
    seen_ids: set[str] = set()
    for workflow in workflows:
        if not isinstance(workflow, dict):
            raise ConfigError("Each workflow entry must be a mapping")
        missing = sorted(REQUIRED_WORKFLOW_KEYS - set(workflow))
        if missing:
            raise ConfigError(f"Workflow entry missing required keys: {', '.join(missing)}")
        workflow_id = workflow["id"]
        if not isinstance(workflow_id, str) or not workflow_id:
            raise ConfigError("Each workflow must define a non-empty id")
        if workflow_id in seen_ids:
            raise ConfigError(f"Duplicate workflow id: {workflow_id}")
        seen_ids.add(workflow_id)
        for key in ("default_agents", "handoff_chain", "acceptance_checks"):
            _require_string_list(workflow.get(key), label=f"Workflow '{workflow_id}' field '{key}'")
    return data


def load_skills_catalog(root: Path) -> dict[str, Any]:
    return load_workflows_catalog(root)


def validate_repository_integrity(
    root: Path,
    system_cfg: dict[str, Any],
    skills_cfg: dict[str, Any],
    extra_definition_roots: list[Path] | None = None,
) -> None:
    errors: list[str] = []
    declared_agents: set[str] = set()
    definition_roots = extra_definition_roots or []
    for agent in system_cfg.get("agents", []):
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id", "")).strip()
        if not agent_id:
            continue
        declared_agents.add(agent_id)
        if not _agent_doc_exists(root, agent_id, definition_roots):
            errors.append(f"Missing agent definition: {DEFINITION_DIRNAME}/agents/{agent_id}.md")

    workflow_rows = skills_cfg.get("workflows", [])
    for workflow in workflow_rows:
        workflow_id = str(workflow.get("id", "")).strip()
        if not workflow_id:
            continue
        referenced_agents = set()
        for key in ("default_agents", "handoff_chain"):
            referenced_agents.update(workflow.get(key, []))
        unknown_agents = sorted(agent for agent in referenced_agents if agent not in declared_agents)
        if unknown_agents:
            errors.append(f"Workflow '{workflow_id}' references unknown agents: {', '.join(unknown_agents)}")
        if not _workflow_doc_exists(root, workflow_id, definition_roots):
            errors.append(f"Missing workflow definition: {DEFINITION_DIRNAME}/skills/{workflow_id}/SKILL.md")

    if errors:
        joined = "\n- ".join(errors)
        raise ConfigError(f"Repository integrity check failed:\n- {joined}")
