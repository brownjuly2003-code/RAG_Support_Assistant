from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_parallel_requests_keep_sessions_isolated_by_tenant(
    monkeypatch: pytest.MonkeyPatch,
    integration_api_app,
    integration_headers,
    integration_store,
) -> None:
    lock = threading.Lock()

    class FakeSession:
        def __init__(self, tenant_id: str) -> None:
            self._tenant_id = tenant_id
            self._history: list[dict[str, str]] = []

        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default") -> dict:
            _ = trace_id
            return {
                "answer": f"{tenant_id}:{question}",
                "quality_score": 85,
                "route": "auto",
                "graded_docs": [],
                "trace_id": f"trace-{tenant_id}",
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        normalized = session_id or uuid.uuid4().hex
        key = (tenant_id, normalized)
        with lock:
            sessions = integration_store["sessions"]
            if key not in sessions:
                sessions[key] = FakeSession(tenant_id)
            session = sessions[key]
        return normalized, session

    monkeypatch.setattr(integration_api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(integration_api_app, "log_audit", _fake_log_audit)

    shared_session = uuid.uuid4().hex
    requests = [
        ("acme", shared_session, "Q1"),
        ("megacorp", shared_session, "Q2"),
        ("acme", uuid.uuid4().hex, "Q3"),
        ("megacorp", uuid.uuid4().hex, "Q4"),
        ("default", uuid.uuid4().hex, "Q5"),
    ]

    def _send(tenant: str, session_id: str, question: str) -> dict:
        with TestClient(integration_api_app.app) as client:
            response = client.post(
                "/api/ask",
                json={"question": question, "session_id": session_id},
                headers=integration_headers(tenant, "admin"),
            )
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda args: _send(*args), requests))

    assert {item["answer"] for item in results} == {
        "acme:Q1",
        "megacorp:Q2",
        "acme:Q3",
        "megacorp:Q4",
        "default:Q5",
    }
    assert len(integration_store["sessions"]) == 5
