from __future__ import annotations

import pytest

from opentower_cli.intent_parser import parse_objective


def test_parse_objective_routes_number_before_port_to_port_lookup() -> None:
    intent = parse_objective("哪些进程占用 80 端口")

    assert intent.workflow_id == "process-port-inspection"
    assert intent.operation == "port_lookup"
    assert intent.entities["port"] == 80


def test_parse_objective_prefers_explicit_file_search_over_memory_keyword() -> None:
    intent = parse_objective('搜索包含 "memory" 的文件')

    assert intent.workflow_id == "file-search"
    assert intent.operation == "content_search"
    assert intent.entities["pattern"] == "memory"


def test_parse_objective_still_routes_process_status_requests_to_process_workflow() -> None:
    intent = parse_objective("查看 nginx 进程是否在运行")

    assert intent.workflow_id == "process-port-inspection"
    assert intent.operation == "service_status"
    assert intent.entities["service"] == "nginx"


def test_parse_objective_routes_chinese_service_phrases_to_process_workflow() -> None:
    intent = parse_objective("查看 nginx 服务状态")

    assert intent.workflow_id == "process-port-inspection"
    assert intent.operation == "service_status"
    assert intent.entities["service"] == "nginx"


def test_parse_objective_rejects_conflicting_workflow_hint() -> None:
    with pytest.raises(ValueError, match="does not match workflow 'disk-inspection'"):
        parse_objective("找到所有 nginx 配置文件", workflow_hint="disk-inspection")


def test_parse_objective_accepts_matching_workflow_hint() -> None:
    intent = parse_objective("找到所有 nginx 配置文件", workflow_hint="file-search")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "filename_search"


def test_parse_objective_defaults_config_searches_to_etc_scope() -> None:
    intent = parse_objective("找到所有 nginx 配置文件")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "filename_search"
    assert intent.entities["path"] == "/etc"
    assert intent.entities["pattern"] == "*nginx*"


def test_parse_objective_treats_permission_checks_as_read_only() -> None:
    intent = parse_objective("查看 /etc/passwd 权限")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "inspect_permissions"
    assert intent.entities["path"] == "/etc/passwd"


def test_parse_objective_requires_target_for_permission_checks() -> None:
    with pytest.raises(ValueError, match="Could not determine the path to inspect permissions"):
        parse_objective("查看权限")


def test_parse_objective_requires_delete_verb_for_batch_user_deletion() -> None:
    intent = parse_objective("查看所有用户")

    assert intent.workflow_id == "user-management"
    assert intent.operation == "list_users"


def test_parse_objective_extracts_explicit_filename_pattern() -> None:
    intent = parse_objective("找到所有 hosts 文件")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "filename_search"
    assert intent.entities["path"] == "/etc"
    assert intent.entities["pattern"] == "*hosts*"
    assert intent.entities["search_kind"] == "file"


def test_parse_objective_marks_directory_searches() -> None:
    intent = parse_objective("查找 cache 目录")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "filename_search"
    assert intent.entities["pattern"] == "*cache*"
    assert intent.entities["search_kind"] == "directory"


def test_parse_objective_treats_give_me_permissions_as_read_only_inspection() -> None:
    intent = parse_objective("给我看 /etc/passwd 权限")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "inspect_permissions"
    assert intent.entities["path"] == "/etc/passwd"


def test_parse_objective_prefers_content_search_over_group_keyword() -> None:
    intent = parse_objective('搜索包含 "group" 的文件')

    assert intent.workflow_id == "file-search"
    assert intent.operation == "content_search"
    assert intent.entities["pattern"] == "group"


def test_parse_objective_prefers_file_search_over_passwd_keyword() -> None:
    intent = parse_objective("查找 passwd 配置文件")

    assert intent.workflow_id == "file-search"
    assert intent.operation == "filename_search"
    assert intent.entities["pattern"] == "*passwd*"
