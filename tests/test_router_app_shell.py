from __future__ import annotations

import ast
from pathlib import Path

APP_MODULE_ROUTER_FILES = [
    Path("api/routers/auth_sso.py"),
    Path("api/routers/feedback.py"),
    Path("api/routers/agent.py"),
    Path("api/routers/analytics.py"),
    Path("api/routers/misc.py"),
    Path("api/routers/admin_experiments.py"),
    Path("api/routers/admin_evaluations.py"),
    Path("api/routers/admin_ops.py"),
    Path("api/routers/admin_kb.py"),
    Path("api/routers/conversation.py"),
    Path("api/routers/session_auth.py"),
    Path("api/routers/root_pages.py"),
    Path("api/routers/system.py"),
]


def test_selected_routers_use_shared_app_module() -> None:
    for router_file in APP_MODULE_ROUTER_FILES:
        tree = ast.parse(router_file.read_text(encoding="utf-8"))

        assert not any(
            isinstance(node, ast.FunctionDef) and node.name == "_app_module"
            for node in tree.body
        ), router_file
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "api._shared"
            and any(alias.name == "app_module" and alias.asname == "_app_module" for alias in node.names)
            for node in tree.body
        ), router_file


def test_admin_review_uses_shared_review_helpers_directly() -> None:
    router_file = Path("api/routers/admin_review.py")
    tree = ast.parse(router_file.read_text(encoding="utf-8"))

    imported_helpers = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "api._shared"
        for alias in node.names
    }

    assert "app_module" not in imported_helpers
    assert {
        "_REVIEW_QUEUE_REASONS",
        "_REVIEW_QUEUE_STATUSES",
        "_load_review_queue_trace_details",
        "_refresh_review_queue_metrics",
        "_review_queue_enabled",
        "_reviewed_by_uuid",
        "_serialize_timestamp",
    } <= imported_helpers
