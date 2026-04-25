from __future__ import annotations

import shlex

from .ops_types import CommandPlan, Intent, PlannedCommand, SecurityAssessment


def _q(value: str) -> str:
    return shlex.quote(str(value))


def plan_commands(intent: Intent, assessment: SecurityAssessment) -> CommandPlan:
    if assessment.decision == "block":
        return CommandPlan(
            workflow_id=intent.workflow_id,
            operation=intent.operation,
            summary="Execution blocked before command generation.",
            parser_kind="blocked",
        )

    if intent.workflow_id == "disk-inspection":
        commands = [
            PlannedCommand(
                name="disk-usage",
                description="Inspect mounted filesystem usage.",
                command="df -h",
            ),
            PlannedCommand(
                name="block-devices",
                description="Inspect block devices and mount points.",
                command="lsblk",
                allow_failure=True,
            ),
        ]
        if intent.operation == "disk_usage_with_logs":
            commands.append(
                PlannedCommand(
                    name="log-usage",
                    description="Inspect /var/log usage.",
                    command="du -sh /var/log/* 2>/dev/null | sort -h",
                    allow_failure=True,
                )
            )
        return CommandPlan(
            workflow_id=intent.workflow_id,
            operation=intent.operation,
            summary="Inspect filesystem usage and related storage signals.",
            parser_kind="disk",
            execution_commands=commands,
        )

    if intent.workflow_id == "file-search":
        if intent.operation == "inspect_permissions":
            path = str(intent.entities.get("path") or "/")
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Inspect file or directory permissions.",
                parser_kind="file-search",
                execution_commands=[
                    PlannedCommand(
                        name="inspect-permissions",
                        description="Inspect permissions for the requested path.",
                        command=f"ls -ld -- {_q(path)}",
                    )
                ],
            )

        if intent.operation == "content_search":
            path = str(intent.entities.get("path") or "/etc")
            pattern = str(intent.entities.get("pattern") or "database")
            command = f"grep -R -n -i -- {_q(pattern)} {_q(path)} 2>/dev/null"
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Search file contents for the requested term.",
                parser_kind="file-search",
                execution_commands=[
                    PlannedCommand(
                        name="content-search",
                        description="Search file contents.",
                        command=command,
                        allowed_returncodes=(0, 1),
                    )
                ],
            )

        if intent.operation == "delete_path":
            path = str(intent.entities.get("path") or "/")
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Delete the requested path after confirmation.",
                parser_kind="destructive-path",
                execution_commands=[
                    PlannedCommand(
                        name="delete-path",
                        description="Delete the requested path recursively.",
                        command=f"rm -rf -- {_q(path)}",
                    )
                ],
            )

        if intent.operation == "chmod_recursive":
            path = str(intent.entities.get("path") or "/")
            mode = str(intent.entities.get("mode") or "777")
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Change permissions recursively after confirmation.",
                parser_kind="chmod",
                execution_commands=[
                    PlannedCommand(
                        name="chmod-recursive",
                        description="Apply recursive permissions.",
                        command=f"chmod -R {shlex.quote(mode)} -- {_q(path)}",
                    )
                ],
            )

        path = str(intent.entities.get("path") or "/")
        pattern = str(intent.entities.get("pattern") or "nginx.conf")
        search_kind = str(intent.entities.get("search_kind") or "file")
        find_type = "d" if search_kind == "directory" else "f"
        command = f"find {_q(path)} -type {find_type} -name {_q(pattern)} 2>/dev/null"
        return CommandPlan(
            workflow_id=intent.workflow_id,
            operation=intent.operation,
            summary="Search for matching files or directories.",
            parser_kind="file-search",
            execution_commands=[
                PlannedCommand(
                    name="filename-search",
                    description="Find files or directories by name.",
                    command=command,
                    allowed_returncodes=(0, 1),
                )
            ],
        )

    if intent.workflow_id == "process-port-inspection":
        if intent.operation == "port_lookup":
            port = int(intent.entities.get("port") or 80)
            command = f"lsof -i :{port} 2>/dev/null || ss -ltnp 2>/dev/null | grep ':{port} ' || netstat -tulnp 2>/dev/null | grep ':{port}'"
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Inspect which process is using the requested port.",
                parser_kind="process",
                execution_commands=[
                    PlannedCommand(
                        name="port-lookup",
                        description="Inspect listeners on a port.",
                        command=command,
                        allowed_returncodes=(0, 1),
                    )
                ],
            )
        if intent.operation == "top_memory":
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Inspect memory-heavy processes.",
                parser_kind="process",
                execution_commands=[
                    PlannedCommand(
                        name="top-memory",
                        description="List top memory consumers.",
                        command="ps aux --sort=-%mem | head -6",
                    )
                ],
            )

        service = str(intent.entities.get("service") or "nginx")
        command = f"systemctl status {_q(service)} --no-pager 2>/dev/null || ps aux | grep -i -- {_q(service)} | grep -v grep"
        return CommandPlan(
            workflow_id=intent.workflow_id,
            operation=intent.operation,
            summary="Inspect process or service status.",
            parser_kind="process",
            execution_commands=[
                PlannedCommand(
                    name="service-status",
                    description="Inspect service status.",
                    command=command,
                    allowed_returncodes=(0, 1),
                )
            ],
        )

    if intent.workflow_id == "user-management":
        username = str(intent.entities.get("username") or "")
        group = str(intent.entities.get("group") or "")
        if intent.operation == "list_users":
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="List local users and basic account metadata.",
                parser_kind="user-management",
                execution_commands=[
                    PlannedCommand(
                        name="list-users",
                        description="List local users.",
                        command="getent passwd | cut -d: -f1,3,6 | sort",
                    )
                ],
            )

        if intent.operation == "create_user":
            commands = [
                PlannedCommand(
                    name="create-user",
                    description="Create the requested user.",
                    command=f"useradd -m -s /bin/bash -- {_q(username)}",
                ),
            ]
            if group:
                commands.append(
                    PlannedCommand(
                        name="add-group",
                        description="Add the user to the requested group.",
                        command=f"usermod -aG {_q(group)} -- {_q(username)}",
                    )
                )
            commands.extend(
                [
                    PlannedCommand(
                        name="inspect-user-id",
                        description="Inspect the created user identity.",
                        command=f"id {_q(username)}",
                    ),
                    PlannedCommand(
                        name="inspect-user-groups",
                        description="Inspect the created user group membership.",
                        command=f"groups {_q(username)}",
                    ),
                ]
            )
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Create the requested user and inspect the result.",
                parser_kind="user-management",
                execution_commands=commands,
            )

        if intent.operation == "add_user_to_group":
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Add the requested user to the requested group.",
                parser_kind="user-management",
                execution_commands=[
                    PlannedCommand(
                        name="add-user-to-group",
                        description="Add the user to the group.",
                        command=f"usermod -aG {_q(group)} -- {_q(username)}",
                    ),
                    PlannedCommand(
                        name="inspect-user-groups",
                        description="Inspect group membership after the update.",
                        command=f"groups {_q(username)}",
                    ),
                ],
            )

        if intent.operation == "delete_user":
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Delete the requested user.",
                parser_kind="user-management",
                execution_commands=[
                    PlannedCommand(
                        name="inspect-user-before-delete",
                        description="Inspect the user before deletion.",
                        command=f"id {_q(username)}",
                        allowed_returncodes=(0, 1),
                        allow_failure=True,
                    ),
                    PlannedCommand(
                        name="delete-user",
                        description="Delete the user and home directory.",
                        command=f"userdel -r -- {_q(username)}",
                    ),
                ],
            )

        if intent.operation == "batch_delete_users":
            user_filter = str(intent.entities.get("user_filter") or "test")
            preview = PlannedCommand(
                name="preview-batch-delete",
                description="Preview users that match the deletion filter.",
                command=f"getent passwd | grep -i -- {_q(user_filter)} | cut -d: -f1,3,6",
                allowed_returncodes=(0, 1),
            )
            return CommandPlan(
                workflow_id=intent.workflow_id,
                operation=intent.operation,
                summary="Preview candidate users before bulk deletion.",
                parser_kind="user-management",
                preview_parser_kind="user-batch-preview",
                preview_commands=[preview],
                deferred_action="batch-delete-users",
                metadata={"user_filter": user_filter},
            )

        return CommandPlan(
            workflow_id=intent.workflow_id,
            operation=intent.operation,
            summary="Inspect the requested user.",
            parser_kind="user-management",
            execution_commands=[
                PlannedCommand(
                    name="inspect-user",
                    description="Inspect the requested user.",
                    command=f"id {_q(username)} && groups {_q(username)}",
                )
            ],
        )

    raise ValueError(f"Unsupported workflow: {intent.workflow_id}")
