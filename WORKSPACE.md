# OpenTower Linux Ops

## Source of truth

- Runtime config: `org/system.yaml`
- Workflow catalog: `org/skills.yaml`
- Agent definitions: `.opentower/agents/*.md`
- Workflow definitions: `.opentower/skills/*/SKILL.md`
- CLI entrypoint: `python -m opentower_cli ...`

## Product surface

Only these user-facing commands are shipped:

- `workflow`
- `dispatch`
- `console`
- `provider-status`

## Operating model

The repository is scoped to a fixed Linux operations workflow:

- `intent-parser`
- `security-guard`
- `command-planner`
- `result-analyst`

Keep the repo aligned with that narrow surface. Do not reintroduce extra entrypoints or legacy governance/runtime layers.
