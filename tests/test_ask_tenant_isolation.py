"""TEN-01 application contracts: tenant-safe /api/ask session ownership.

Covers cold-cache real ``_get_or_create_session`` path through ``/api/ask``.
Does not replace ``_get_or_create_session``; fakes only the DB session factory.
"""

from __future__ import annotations

import importlib
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
SECRET_CONTENT = "SECRET-CROSS-TENANT-PAYLOAD-NEVER-LEAK"
SESSION_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SESSION_HEX = SESSION_UUID.hex


def _auth(tenant: str, role: str = "agent") -> dict[str, str]:
    token = create_access_token("u-" + tenant, role, tenant)
    return {"Authorization": f"Bearer {token}"}


class _OwnedSession:
    """In-memory ConversationSession-like object with tenant ownership."""

    def __init__(self, tenant_id: str, history: list[dict[str, str]] | None = None) -> None:
        self._tenant_id = tenant_id
        self._history = list(history or [])
        self._max_history = 20

    def ask(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "should-not-run",
            "quality_score": 0,
            "route": "auto",
            "graded_docs": [],
            "citations": [],
            "trace_id": "",
            "suggested_questions": [],
        }


class _FakeResult:
    def __init__(self, rows: Any = None, scalar: Any = None) -> None:
        self._rows = rows if rows is not None else []
        self._scalar = scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def all(self) -> list[Any]:
        return list(self._rows)


class _CrossTenantDbSession:
    """Controlled async DB: session row owned by a fixed tenant, with secret msgs."""

    def __init__(
        self,
        tracker: dict[str, Any],
        *,
        owner_tenant: str = TENANT_A,
        session_uuid: uuid.UUID = SESSION_UUID,
        secret: str = SECRET_CONTENT,
    ) -> None:
        self.tracker = tracker
        self.owner_tenant = owner_tenant
        self.session_uuid = session_uuid
        self.secret = secret
        self.db_session = type(
            "DBSess",
            (),
            {
                "id": session_uuid,
                "tenant_id": owner_tenant,
                "last_access": None,
            },
        )()

    async def __aenter__(self) -> "_CrossTenantDbSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def _compile_params(self, stmt: Any) -> dict[str, Any]:
        try:
            return dict(stmt.compile().params)
        except Exception:
            return {}

    async def execute(self, stmt: Any) -> _FakeResult:
        sql = str(stmt).lower()
        self.tracker.setdefault("execute_sql", []).append(sql)
        # Session lookup (no message columns) vs history read.
        if "from messages" in sql or "join messages" in sql or ".messages" in sql:
            self.tracker["message_reads"] = self.tracker.get("message_reads", 0) + 1
            return _FakeResult(
                rows=[("user", self.secret), ("assistant", "reply-a")]
            )

        self.tracker["session_lookups"] = self.tracker.get("session_lookups", 0) + 1
        params = self._compile_params(stmt)
        tenant_binds = [
            v for k, v in params.items() if "tenant" in str(k).lower()
        ]

        # Tenant-scoped ownership: only return the row when the bound tenant matches.
        if tenant_binds:
            if tenant_binds[0] != self.owner_tenant:
                return _FakeResult(scalar=None)
            return _FakeResult(scalar=self.db_session)

        # ID-only existence / legacy id lookup — never expose foreign history here.
        # Prefer returning just the id when the SELECT list is id-only.
        if "messages" not in sql and sql.count("tenant_id") == 0:
            return _FakeResult(scalar=self.session_uuid)
        return _FakeResult(scalar=self.db_session)

    def add(self, obj: Any) -> None:
        self.tracker.setdefault("adds", []).append(obj)
        # Track tenant rewrites via attribute assignment on our fake session.
        if obj is self.db_session:
            self.tracker["session_readded"] = True

    async def commit(self) -> None:
        self.tracker["commits"] = self.tracker.get("commits", 0) + 1
        # Capture tenant after potential rewrite.
        self.tracker["tenant_after_commit"] = self.db_session.tenant_id


def test_ask_cross_tenant_cold_cache_returns_opaque_404(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Tenant B must not load/mutate tenant A's session via /api/ask (cold cache)."""
    tracker: dict[str, Any] = {}
    fake_db = _CrossTenantDbSession(tracker)

    monkeypatch.setattr("db.engine.async_session", lambda: fake_db)
    api_app._session_llm_state.clear()
    api_app._session_last_access.clear()
    api_app._db_retry_after = 0.0

    response = client.post(
        "/api/ask",
        json={
            "question": "What is the secret?",
            "session_id": str(SESSION_UUID),
            "tenant_id": TENANT_A,  # must be ignored; auth tenant is authority
        },
        headers=_auth(TENANT_B),
    )

    assert response.status_code == 404, response.text
    body_text = response.text
    assert SECRET_CONTENT not in body_text
    assert "should-not-run" not in body_text

    # Ownership must not be rewritten (including default hijack).
    assert fake_db.db_session.tenant_id == TENANT_A
    assert tracker.get("tenant_after_commit") in (None, TENANT_A)

    # No Message rows written for the foreign session.
    added_types = [type(obj).__name__ for obj in tracker.get("adds", [])]
    assert "Message" not in added_types

    # Cross-tenant path must not read foreign Message rows at all.
    assert tracker.get("message_reads", 0) == 0

    # In-memory owner must not become tenant B.
    mem = api_app._session_llm_state.get(SESSION_HEX) or api_app._session_llm_state.get(
        str(SESSION_UUID)
    )
    if mem is not None:
        if hasattr(mem, "_tenant_id"):
            assert mem._tenant_id != TENANT_B
        elif isinstance(mem, dict):
            assert mem.get("tenant_id") != TENANT_B


def test_ask_malformed_session_id_rejected_without_db_cooldown(
    client: TestClient,
) -> None:
    """Malformed session_id is rejected at the API boundary; cooldown stays clean."""
    api_app._db_retry_after = 0.0

    response = client.post(
        "/api/ask",
        json={"question": "hello", "session_id": "not-a-uuid"},
        headers=_auth(TENANT_A),
    )

    assert response.status_code == 422, response.text
    assert api_app._db_retry_after == 0.0, "malformed input must not poison DB cooldown"


def test_ask_rejects_in_memory_tenant_mismatch_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Caller must not replace an in-memory session owned by another tenant."""
    # Skip DB so only the in-memory ownership branch is exercised.
    api_app._db_retry_after = time.monotonic() + 3600.0
    owned = _OwnedSession(
        TENANT_A,
        history=[{"role": "user", "content": SECRET_CONTENT}],
    )
    api_app._session_llm_state[SESSION_HEX] = owned
    api_app._session_last_access[SESSION_HEX] = time.monotonic()

    response = client.post(
        "/api/ask",
        json={"question": "hijack?", "session_id": SESSION_HEX},
        headers=_auth(TENANT_B),
    )

    assert response.status_code == 404, response.text
    assert SECRET_CONTENT not in response.text
    assert api_app._session_llm_state.get(SESSION_HEX) is owned
    assert owned._tenant_id == TENANT_A


def test_ask_cooldown_supplied_uncached_uuid_returns_503_without_cache_write(
    client: TestClient,
) -> None:
    """Caller-supplied UUID + active cooldown + cold cache => 503, no new entry."""
    api_app._db_retry_after = time.monotonic() + 3600.0
    api_app._session_llm_state.clear()
    api_app._session_last_access.clear()
    cooldown_before = api_app._db_retry_after

    supplied = uuid.uuid4()
    supplied_hex = supplied.hex

    response = client.post(
        "/api/ask",
        json={"question": "hello during outage", "session_id": str(supplied)},
        headers=_auth(TENANT_A),
    )

    assert response.status_code == 503, response.text
    # Must not create, overwrite, or touch session caches for the supplied id.
    assert supplied_hex not in api_app._session_llm_state
    assert str(supplied) not in api_app._session_llm_state
    assert supplied_hex not in api_app._session_last_access
    assert str(supplied) not in api_app._session_last_access
    # 503 path itself must not extend the circuit breaker.
    assert api_app._db_retry_after == cooldown_before


def test_ask_primary_ownership_query_is_tenant_scoped(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """First Session ownership lookup must constrain both id and tenant_id."""
    tracker: dict[str, Any] = {}
    fake_db = _CrossTenantDbSession(tracker)

    monkeypatch.setattr("db.engine.async_session", lambda: fake_db)
    api_app._session_llm_state.clear()
    api_app._session_last_access.clear()
    api_app._db_retry_after = 0.0

    response = client.post(
        "/api/ask",
        json={"question": "probe ownership sql", "session_id": str(SESSION_UUID)},
        headers=_auth(TENANT_B),
    )

    assert response.status_code == 404, response.text
    sqls = tracker.get("execute_sql") or []
    assert sqls, "expected at least one Session ownership SQL execute"
    first = sqls[0]
    assert "where" in first, first
    where_part = first.split("where", 1)[1]
    # Behavior contract: primary ownership query is scoped by (id, tenant_id).
    assert "tenant_id" in where_part, f"primary WHERE lacks tenant_id: {first}"
    assert "id" in where_part, f"primary WHERE lacks id: {first}"
    assert tracker.get("message_reads", 0) == 0


def test_ask_foreign_default_session_not_rebound(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Historical tenant_id='default' Session must not be rebound to another tenant."""
    tracker: dict[str, Any] = {}
    fake_db = _CrossTenantDbSession(tracker, owner_tenant="default")

    monkeypatch.setattr("db.engine.async_session", lambda: fake_db)
    api_app._session_llm_state.clear()
    api_app._session_last_access.clear()
    api_app._db_retry_after = 0.0

    response = client.post(
        "/api/ask",
        json={
            "question": "rebind default?",
            "session_id": str(SESSION_UUID),
            "tenant_id": "default",  # body tenant is not authoritative
        },
        headers=_auth(TENANT_B),
    )

    assert response.status_code == 404, response.text
    assert SECRET_CONTENT not in response.text
    # Must remain owned by historical default; never rewritten to caller tenant.
    assert fake_db.db_session.tenant_id == "default"
    assert tracker.get("tenant_after_commit") in (None, "default")
    added_types = [type(obj).__name__ for obj in tracker.get("adds", [])]
    assert "Message" not in added_types
    assert tracker.get("message_reads", 0) == 0

    mem = api_app._session_llm_state.get(SESSION_HEX)
    if mem is not None:
        if hasattr(mem, "_tenant_id"):
            assert mem._tenant_id != TENANT_B
        elif isinstance(mem, dict):
            assert mem.get("tenant_id") != TENANT_B
