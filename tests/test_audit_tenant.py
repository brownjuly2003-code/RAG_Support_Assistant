"""TEN-02 application contracts: tenant-required audit writes and redacted fallback."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from utils import background_tasks


async def _drain_background_tasks() -> None:
    pending = list(background_tasks._background_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def test_log_audit_requires_non_empty_tenant_id() -> None:
    from db.audit import log_audit

    with pytest.raises((TypeError, ValueError)):
        asyncio.run(
            log_audit(
                actor="u1",
                action="ask",
                resource="session:x",
            )
        )

    with pytest.raises(ValueError):
        asyncio.run(
            log_audit(
                actor="u1",
                action="ask",
                resource="session:x",
                tenant_id="",
            )
        )

    with pytest.raises(ValueError):
        asyncio.run(
            log_audit(
                actor="u1",
                action="ask",
                resource="session:x",
                tenant_id="   ",
            )
        )


def test_log_audit_persists_explicit_tenant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from db.audit import log_audit

    captured: dict[str, Any] = {}

    class _FakeDb:
        def add(self, entry: Any) -> None:
            captured["entry"] = entry

        async def commit(self) -> None:
            captured["committed"] = True

    class _Ctx:
        async def __aenter__(self) -> _FakeDb:
            return _FakeDb()

        async def __aexit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr("db.engine.async_session", lambda: _Ctx())

    async def _run() -> None:
        await log_audit(
            actor="agent-1",
            action="ask",
            resource="session:abc",
            tenant_id="acme-corp",
            detail={"question_length": 12},
            ip_address="203.0.113.9",
        )
        await _drain_background_tasks()

    asyncio.run(_run())

    entry = captured.get("entry")
    assert entry is not None, "AuditLog row must be added"
    assert getattr(entry, "tenant_id", None) == "acme-corp"
    assert captured.get("committed") is True


def test_log_audit_fallback_redacts_detail_and_ip(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from db.audit import log_audit

    secret_detail = {"token": "super-secret-token-value", "note": "do-not-log"}
    secret_ip = "198.51.100.77"

    class _BoomCtx:
        async def __aenter__(self) -> Any:
            raise RuntimeError("db-down")

        async def __aexit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr("db.engine.async_session", lambda: _BoomCtx())

    async def _run() -> None:
        await log_audit(
            actor="agent-1",
            action="upload",
            resource="document:x.pdf",
            tenant_id="acme-corp",
            detail=secret_detail,
            ip_address=secret_ip,
        )
        await _drain_background_tasks()

    with caplog.at_level(logging.INFO):
        asyncio.run(_run())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "super-secret-token-value" not in joined
    assert "do-not-log" not in joined
    assert secret_ip not in joined
    assert "198.51.100.77" not in joined
    # Minimal structured warning is fine; payload values are not.
    assert "upload" in joined or any("upload" in r.getMessage() for r in caplog.records)


def test_log_audit_call_sites_pass_tenant_id() -> None:
    """Source invariant: every production log_audit call passes tenant_id=."""
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "db" / "audit.py",
        root / "api" / "routers" / "admin_ops.py",
        root / "api" / "routers" / "agent.py",
        root / "api" / "routers" / "auth_sso.py",
        root / "api" / "routers" / "conversation.py",
        root / "api" / "routers" / "feedback.py",
        root / "api" / "routers" / "session_auth.py",
        root / "api" / "routers" / "upload.py",
    ]

    # Match direct/wrapped call sites: log_audit( / _log_audit(
    call_re = re.compile(
        r"(?:await\s+)?(?:_app\.)?(?:_log_audit|log_audit)\s*\(",
        re.MULTILINE,
    )
    missing: list[str] = []

    for path in targets:
        text = path.read_text(encoding="utf-8")
        # Skip the definition itself in db/audit.py
        for match in call_re.finditer(text):
            start = match.start()
            # Find matching close paren roughly via bracket scan
            depth = 0
            end = start
            for i, ch in enumerate(text[start:], start=start):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            snippet = text[start:end]
            # Definition line: async def log_audit(
            line_start = text.rfind("\n", 0, start) + 1
            line = text[line_start : text.find("\n", start)]
            if line.lstrip().startswith("async def ") or line.lstrip().startswith("def "):
                continue
            # Pass-through wrappers forward kwargs; real call sites must set tenant_id=.
            if "**kwargs" in snippet:
                continue
            if not re.search(r"\btenant_id\s*=", snippet):
                rel = path.relative_to(root).as_posix()
                lineno = text.count("\n", 0, start) + 1
                missing.append(f"{rel}:{lineno}")

    assert missing == [], f"log_audit call sites missing tenant_id: {missing}"

    # Signature contract
    from db.audit import log_audit

    params = inspect.signature(log_audit).parameters
    assert "tenant_id" in params
    assert params["tenant_id"].default is inspect.Parameter.empty
