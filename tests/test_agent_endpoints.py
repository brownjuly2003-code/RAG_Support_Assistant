from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


def _token(tenant: str = "default", role: str = "agent") -> dict[str, str]:
    token = create_access_token("agent-user", role, tenant)
    return {"Authorization": f"Bearer {token}"}


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_agent_page_requires_agent_role(client_with_key: TestClient) -> None:
    forbidden = client_with_key.get("/agent", headers=_token("acme", "viewer"))
    allowed = client_with_key.get("/agent", headers=_token("acme", "agent"))

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_agent_tickets_list_filters_by_tenant_and_status(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    captured: dict[str, str] = {}

    class _Ticket:
        id = uuid.UUID("00000000-0000-0000-0000-000000000106")
        tenant_id = "acme"
        session_id = "session-106"
        user_question = "Нужен оператор"
        ai_draft = "Черновик"
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _ScalarResult:
        def all(self):
            return [_Ticket()]

    class _Result:
        def scalars(self):
            return _ScalarResult()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return _Result()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get(
        "/api/agent/tickets?status=open",
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    assert "escalated_tickets.tenant_id" in captured["sql"]
    assert "escalated_tickets.status" in captured["sql"]
    assert response.json()["tickets"][0]["tenant_id"] == "acme"


def test_agent_ticket_respond_marks_ticket_resolved(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    ticket_id = uuid.UUID("00000000-0000-0000-0000-000000000107")
    captured: dict[str, object] = {}

    class _Ticket:
        id = ticket_id
        tenant_id = "acme"
        session_id = "session-107"
        user_question = "Вопрос"
        ai_draft = "Черновик"
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, model, lookup_id):
            captured["model"] = getattr(model, "__name__", str(model))
            captured["lookup_id"] = lookup_id
            return _Ticket() if lookup_id == ticket_id else None

        async def commit(self):
            captured["committed"] = True

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client_with_key.post(
        f"/api/agent/tickets/{ticket_id}/respond",
        json={"response": "Готово, берём в работу"},
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    assert captured["lookup_id"] == ticket_id
    assert captured["committed"] is True
    assert response.json()["ticket"]["status"] == "resolved"
    assert response.json()["ticket"]["operator_response"] == "Готово, берём в работу"


def test_agent_ticket_detail_returns_context_when_available(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    from tracing import sqlite_trace

    ticket_id = uuid.UUID("00000000-0000-0000-0000-000000000108")
    session_uuid = uuid.UUID("00000000-0000-0000-0000-000000000208")

    class _Ticket:
        id = ticket_id
        tenant_id = "acme"
        session_id = str(session_uuid)
        user_question = "Как сбросить пароль?"
        ai_draft = "Черновик"
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _Message:
        role = "user"
        content = "Как сбросить пароль?"
        created_at = datetime(2026, 4, 20, 12, 1, tzinfo=timezone.utc)

    class _ScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _ScalarResult(self._rows)

    class _Session:
        def __init__(self):
            self.execute_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, model, lookup_id):
            return _Ticket() if lookup_id == ticket_id else None

        async def execute(self, stmt):
            self.execute_count += 1
            if self.execute_count == 1:
                return _Result([_Message()])
            return _Result([])

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(
        sqlite_trace,
        "list_recent_traces",
        lambda limit=50, tenant_id=None: [
            {"trace_id": "trace-wrong-session"},
            {"trace_id": "trace-context"},
        ],
    )

    def _trace_detail(trace_id, tenant_id=None):
        if trace_id == "trace-wrong-session":
            return {
                "steps": [
                    {
                        "state": {
                            "session_id": "00000000-0000-0000-0000-000000000999",
                            "question": "Как сбросить пароль?",
                            "route": "auto",
                            "quality_score": 99,
                            "graded_docs": [
                                {
                                    "page_content": "Неправильный trace для другой сессии.",
                                    "metadata": {"title": "Wrong trace", "source": "kb://wrong"},
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "steps": [
                {
                    "state": {
                        "session_id": str(session_uuid),
                        "question": "Как сбросить пароль?",
                        "route": "human",
                        "quality_score": 42,
                        "factuality_score": 67,
                        "relevance_score": 0.78,
                        "graded_docs": [
                            {
                                "page_content": "Откройте настройки безопасности и выберите сброс пароля.",
                                "metadata": {
                                    "title": "Сброс пароля",
                                    "source": "kb://password-reset",
                                },
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(sqlite_trace, "get_trace_detail", _trace_detail)

    response = client_with_key.get(
        f"/api/agent/tickets/{ticket_id}",
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"] == [
        {
            "role": "user",
            "content": "Как сбросить пароль?",
            "created_at": "2026-04-20T12:01:00+00:00",
        }
    ]
    assert payload["retrieved_docs"] == [
        {
            "title": "Сброс пароля",
            "source": "kb://password-reset",
            "excerpt": "Откройте настройки безопасности и выберите сброс пароля.",
        }
    ]
    assert payload["quality_scores"] == {
        "quality_score": 42,
        "factuality_score": 67,
        "relevance_score": 0.78,
        "route": "human",
    }


def test_agent_similar_orders_by_relevance(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key: TestClient,
) -> None:
    ticket_id = uuid.UUID("00000000-0000-0000-0000-000000000109")

    class _Ticket:
        id = ticket_id
        tenant_id = "acme"
        session_id = "session-109"
        user_question = "Не могу сбросить пароль в аккаунте"
        ai_draft = None
        operator_response = None
        status = "open"
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _Resolved:
        def __init__(self, numeric_id, question, answer, resolved_at):
            self.id = uuid.UUID(f"00000000-0000-0000-0000-{numeric_id:012d}")
            self.user_question = question
            self.operator_response = answer
            self.resolved_at = resolved_at
            self.created_at = resolved_at

    resolved = [
        _Resolved(
            300 + index,
            f"Где мой заказ {index}?",
            "Доставка будет завтра.",
            datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        for index in range(25)
    ]
    resolved.extend(
        [
            _Resolved(401, "Сброс пароля в аккаунте", "Откройте настройки аккаунта.", datetime(2026, 4, 1, tzinfo=timezone.utc)),
            _Resolved(402, "Не работает восстановление доступа", "Используйте форму сброса пароля.", datetime(2026, 3, 31, tzinfo=timezone.utc)),
            _Resolved(403, "Как оплатить счёт?", "Оплата доступна картой.", datetime(2026, 4, 23, tzinfo=timezone.utc)),
        ]
    )

    class _ScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _ScalarResult(self._rows)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, model, lookup_id):
            return _Ticket() if lookup_id == ticket_id else None

        async def execute(self, stmt):
            rows = resolved[:25] if "LIMIT" in str(stmt).upper() else resolved
            return _Result(rows)

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())

    response = client_with_key.get(
        f"/api/agent/similar?ticket_id={ticket_id}",
        headers=_token("acme", "agent"),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["tickets"]] == [
        "00000000-0000-0000-0000-000000000401",
        "00000000-0000-0000-0000-000000000402",
        "00000000-0000-0000-0000-000000000300",
    ]


def test_viewer_cannot_access_agent_ticket_endpoints(client_with_key: TestClient) -> None:
    response = client_with_key.get("/api/agent/tickets", headers=_token("acme", "viewer"))

    assert response.status_code == 403
