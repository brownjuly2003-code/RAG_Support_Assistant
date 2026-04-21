from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from auth.jwt_handler import create_access_token
from config.settings import Settings

agent_graph = importlib.import_module("agent.graph")
agent_tools = importlib.import_module("agent.tools")
api_app = importlib.import_module("api.app")


AGENT_HEADERS = {
    "Authorization": f"Bearer {create_access_token('agent-1', 'agent', 'acme')}"
}


def test_agentic_mode_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_AGENTIC_MODE", raising=False)

    settings = Settings()

    assert settings.agentic_mode is False


def test_check_order_status_returns_mock_status() -> None:
    result = agent_tools.check_order_status("42", "acme")

    assert "42" in result
    assert "статус" in result.lower()


def test_agentic_multi_step_flow_combines_kb_and_order_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(agentic_mode=True),
    )
    monkeypatch.setattr(
        agent_tools,
        "search_kb",
        lambda query, tenant_id, retriever=None: "KB: доставка в Москву стоит 500 ₽.",
    )
    monkeypatch.setattr(
        agent_tools,
        "check_order_status",
        lambda order_id, tenant_id: "Заказ #42: статус 'в пути'.",
    )

    session = agent_graph.ConversationSession(retriever=object(), llm=None)

    result = session.ask(
        "Сколько стоит доставка в Москву для заказа #42?",
        tenant_id="acme",
        user_id="agent-1",
        session_id="session-42",
    )

    assert result["tool_calls"] == ["search_kb", "check_order_status"]
    assert "500" in result["answer"]
    assert "в пути" in result["answer"]


def test_agentic_ticket_flow_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, str] = {}

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(agentic_mode=True),
    )

    def _fake_create_ticket(summary, priority, tenant_id, user_id, session_id=""):
        created["summary"] = summary
        created["priority"] = priority
        created["tenant_id"] = tenant_id
        created["user_id"] = user_id
        created["session_id"] = session_id
        return "Создан тикет #T-107."

    monkeypatch.setattr(agent_tools, "create_ticket", _fake_create_ticket)

    session = agent_graph.ConversationSession(retriever=object(), llm=None)

    pending = session.ask(
        "Создай тикет по проблеме с оплатой заказа",
        tenant_id="acme",
        user_id="agent-1",
        session_id="session-107",
    )

    assert pending["requires_confirmation"] is True
    assert "Подтвердите" in pending["answer"]

    confirmed = session.ask(
        "Подтверждаю",
        tenant_id="acme",
        user_id="agent-1",
        session_id="session-107",
        confirm=True,
    )

    assert confirmed["requires_confirmation"] is False
    assert "Создан тикет" in confirmed["answer"]
    assert created["tenant_id"] == "acme"
    assert created["session_id"] == "session-107"


def test_api_ask_passes_confirm_flag_into_session(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    captured: dict[str, object] = {}

    class _FakeSession:
        def ask(
            self,
            question: str,
            trace_id: str | None = None,
            tenant_id: str = "default",
            confirm: bool | None = None,
            user_id: str | None = None,
            session_id: str | None = None,
        ) -> dict:
            captured["question"] = question
            captured["trace_id"] = trace_id
            captured["tenant_id"] = tenant_id
            captured["confirm"] = confirm
            captured["user_id"] = user_id
            captured["session_id"] = session_id
            return {
                "answer": "ok",
                "quality_score": 80,
                "route": "auto",
                "graded_docs": [],
                "trace_id": "trace-agentic",
                "suggested_questions": [],
                "requires_confirmation": False,
                "action_summary": "",
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        _ = session_id, tenant_id
        return "session-agentic", _FakeSession()

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)

    response = client_with_key.post(
        "/api/ask",
        json={"question": "Подтверждаю", "confirm": True},
        headers=AGENT_HEADERS,
    )

    assert response.status_code == 200
    assert captured["confirm"] is True
    assert captured["tenant_id"] == "acme"
