from __future__ import annotations

import ast
from pathlib import Path


ROUTER_FILES = [
    Path("api/routers/auth_sso.py"),
    Path("api/routers/feedback.py"),
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
    for router_file in ROUTER_FILES:
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
