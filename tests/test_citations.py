from __future__ import annotations

import importlib
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

api_app = importlib.import_module("api.app")
graph_module = importlib.import_module("agent.graph")


async def _fake_log_audit(**kwargs) -> None:
    _ = kwargs


def test_generate_node_collects_citations_from_docs() -> None:
    from agent.graph import make_generate_node
    from agent.state import create_initial_state

    llm_fast = MagicMock()
    llm_fast.invoke.return_value = "Сбросьте пароль в настройках [1], затем обновите MFA [2]."
    llm_strong = MagicMock()

    state = create_initial_state(question="Как восстановить доступ?", trace_id="cit-1")
    state["complexity"] = "simple"
    state["graded_docs"] = [
        {
            "page_content": "Инструкция по сбросу пароля через настройки профиля.",
            "metadata": {"doc_id": "doc-reset", "title": "Сброс пароля", "source": "reset.md"},
        },
        {
            "page_content": "Инструкция по обновлению MFA через раздел безопасности.",
            "metadata": {"file_name": "mfa.pdf"},
        },
    ]

    out = make_generate_node(llm_fast, llm_strong)(state)

    assert out["citations"] == [
        {
            "index": 1,
            "doc_id": "doc-reset",
            "title": "Сброс пароля",
            "excerpt": "Инструкция по сбросу пароля через настройки профиля.",
        },
        {
            "index": 2,
            "doc_id": "mfa.pdf",
            "title": "mfa.pdf",
            "excerpt": "Инструкция по обновлению MFA через раздел безопасности.",
        },
    ]


def test_evaluate_node_strips_inline_citations_before_prompt(monkeypatch) -> None:
    from agent.graph import make_evaluate_node
    from agent.state import create_initial_state

    captured: dict[str, object] = {}

    def _fake_build_self_eval_prompt(question: str, answer: str, context_docs):
        captured["question"] = question
        captured["answer"] = answer
        captured["context_docs"] = context_docs
        return "judge prompt"

    monkeypatch.setattr(graph_module, "build_self_eval_prompt", _fake_build_self_eval_prompt)

    llm_fast = MagicMock()
    llm_fast.invoke.return_value = "88"
    llm_strong = MagicMock()

    state = create_initial_state(question="Как восстановить доступ?", trace_id="cit-2")
    state["complexity"] = "simple"
    state["answer"] = "Сбросьте пароль [1], затем обновите MFA [2]."
    state["graded_docs"] = [
        {"page_content": "Reset doc", "metadata": {"source": "reset.md"}},
        {"page_content": "MFA doc", "metadata": {"source": "mfa.md"}},
    ]

    out = make_evaluate_node(llm_fast, llm_strong)(state)

    assert captured["answer"] == "Сбросьте пароль, затем обновите MFA."
    assert out["quality_score"] == 88


def test_ask_endpoint_returns_citations_and_ignores_orphans(
    monkeypatch,
    client: TestClient,
) -> None:
    class FakeSession:
        def ask(self, question: str, trace_id: str | None = None, tenant_id: str = "default", **kwargs):
            _ = question, trace_id, tenant_id, kwargs
            return {
                "answer": "Откройте раздел безопасности [1], затем проверьте несуществующую ссылку [3].",
                "quality_score": 83,
                "route": "auto",
                "graded_docs": [
                    {
                        "page_content": "Раздел безопасности находится в профиле пользователя.",
                        "metadata": {"doc_id": "doc-security", "title": "Безопасность", "source": "security.md"},
                    }
                ],
                "trace_id": "trace-citations",
                "suggested_questions": [],
            }

    async def _fake_get_or_create_session(session_id: str | None, tenant_id: str = "default"):
        _ = session_id, tenant_id
        return "00000000000000000000000000000003", FakeSession()

    monkeypatch.setattr(api_app, "_get_or_create_session", _fake_get_or_create_session)
    monkeypatch.setattr(api_app, "log_audit", _fake_log_audit)

    response = client.post("/api/ask", json={"question": "Как обновить настройки безопасности?"})

    assert response.status_code == 200
    assert response.json()["answer"].endswith("[3].")
    assert response.json()["citations"] == [
        {
            "index": 1,
            "doc_id": "doc-security",
            "title": "Безопасность",
            "excerpt": "Раздел безопасности находится в профиле пользователя.",
        }
    ]
