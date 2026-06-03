from __future__ import annotations

from typing import ClassVar

import importlib
from datetime import datetime, timezone

import pytest

from auth.jwt_handler import create_access_token

agent_graph = importlib.import_module("agent.graph")


ADMIN_HEADERS = {
    "Authorization": f"Bearer {create_access_token('admin', 'admin', 'acme')}"
}


def test_is_knowledge_gap_when_too_few_docs() -> None:
    state = {"graded_docs": [{"page_content": "doc-1"}], "answer": "Ответ", "factuality_score": 100}

    assert agent_graph._is_knowledge_gap(state) is True


def test_is_knowledge_gap_when_factuality_is_low() -> None:
    state = {
        "graded_docs": [{"page_content": "doc-1"}, {"page_content": "doc-2"}],
        "answer": "Ответ",
        "factuality_score": 40,
    }

    assert agent_graph._is_knowledge_gap(state) is True


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Я не знаю, где найти эту информацию.", True),
        ("Не нашёл в документации подходящих данных.", True),
        ("Вот точный ответ по документам.", False),
    ],
)
def test_is_knowledge_gap_when_answer_explicitly_says_unknown(answer: str, expected: bool) -> None:
    state = {
        "graded_docs": [{"page_content": "doc-1"}, {"page_content": "doc-2"}],
        "answer": answer,
        "factuality_score": 100,
    }

    assert agent_graph._is_knowledge_gap(state) is expected


def test_cluster_gap_questions_groups_similar_requests() -> None:
    from scripts import kb_gap_detector

    rows = [
        {"tenant_id": "acme", "question": "Как вернуть товар?", "trace_id": "t1"},
        {"tenant_id": "acme", "question": "Как оформить возврат товара?", "trace_id": "t2"},
        {"tenant_id": "acme", "question": "Где оформить возврат заказа?", "trace_id": "t3"},
    ]

    gaps = kb_gap_detector.build_gap_records(rows, min_cluster_size=3)

    assert len(gaps) == 1
    assert gaps[0]["question_count"] == 3
    assert gaps[0]["tenant_id"] == "acme"


def test_admin_kb_gaps_endpoint_filters_by_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client_with_key,
) -> None:
    captured: dict[str, str] = {}

    class _Gap:
        id = 1
        tenant_id = "acme"
        cluster_id = "returns"
        topic_summary = "Возвраты и отмены"
        sample_questions: ClassVar[list[str]] = ["Как вернуть товар?"]
        question_count = 6
        created_at = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        resolved_at = None

    class _ScalarResult:
        def all(self):
            return [_Gap()]

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

    response = client_with_key.get("/api/admin/kb-gaps", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert "knowledge_gaps.tenant_id" in captured["sql"]
    assert response.json()["gaps"][0]["topic_summary"] == "Возвраты и отмены"
