"""
agent/state.py

Модуль описывает СООТВЕТСТВУЮЩЕЕ состояние графа LangGraph для RAG-ассистента.
Состояние передаётся между узлами графа как обычный словарь (dict), но мы
описываем его структуру через TypedDict, чтобы было проще читать код и
использовать статическую типизацию (mypy, IDE-подсказки).

Поля состояния:

- question: str
    Вопрос пользователя. Задаётся один раз при старте обработки и дальше
    не меняется.

- context_docs: list
    Список фрагментов контекста, найденных ретривером. Для простоты PoC
    мы храним их как список словарей вида:
        {"page_content": str, "metadata": dict}
    Такое представление легко сериализуется в JSON для логирования.

- answer: str | None
    Ответ ассистента. На старте None, после узла generate — строка.

- relevance_score: float | None
    Оценка релевантности ответа вопросу (0.0–1.0). В простом варианте
    мы будем считать её как quality_score / 100.0, но при желании можно
    сделать отдельный узел с более точной оценкой.

- quality_score: int | None
    Оценка качества ответа по шкале 1–100 (чем выше, тем лучше). Эти
    значения выставляет узел evaluate (self-evaluation LLM).

- route: Literal["auto","human","retry","error","error_escalation","agentic"] | None
    Решение маршрутизации:
        "auto"  → ответ достаточно хороший, можно отдать пользователю;
        "human" → лучше эскалировать на человека (оператор поддержки);
        "retry" → Self-RAG: переформулировать запрос и повторить;
        "error" → необработанное исключение в пайплайне, эскалировать;
        "error_escalation" → fallback-ответ после error handler;
        "agentic" → ответ собран agentic tool-use flow.
    До узла route — None.

- trace_id: str
    Идентификатор одного прохода по графу. Генерируется при старте
    обработки вопроса и используется трейсингом (SQLite) для группировки
    шагов (trace_steps) и общей записи (traces).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, Optional, TypedDict


class GraphState(TypedDict, total=False):
    """
    Описание структуры состояния графа.

    total=False означает, что не все поля обязаны присутствовать всегда.
    Например, на этапе retrieve ещё нет answer / quality_score и т.п.,
    но к финалу все поля будут заполнены.

    Level 2 поля:
    - search_query: трансформированный запрос для retrieval
    - graded_docs: документы после фильтрации (Corrective RAG)
    - doc_grade_reason: пояснение, почему документы были отфильтрованы
    - iteration / max_iterations: Self-RAG цикл

    Level 3 поля:
    - chat_history: история диалога для уточняющих вопросов
    - sub_queries: подвопросы (Multi-Query Retrieval)
    """

    question: str
    search_query: Optional[str]
    hyde_query: Optional[str]
    context_docs: list[dict]
    graded_docs: list[dict]
    doc_grade_reason: Optional[str]
    answer: Optional[str]
    relevance_score: Optional[float]
    quality_score: Optional[int]
    # Provenance of quality_score: "llm" — real self-evaluation; "fixed" —
    # hardcoded agentic-flow constants; "heuristic" — streaming length check.
    # Keeps dashboards honest about which scores were actually measured.
    quality_source: Optional[Literal["llm", "fixed", "heuristic"]]
    claims: list[dict]
    factuality_score: int
    fact_verification_skipped: bool
    complexity: Literal["simple", "complex", "global", "unknown"]
    retrieval_strategy: Literal["vector", "hybrid", "graph"]
    route: Optional[Literal["auto", "human", "retry", "error", "error_escalation", "agentic"]]
    trace_id: str
    tenant_id: str
    error: bool
    error_message: str
    error_node: str
    knowledge_gap: bool
    iteration: int
    max_iterations: int
    chat_history: list[dict]
    sub_queries: list[str]
    suggested_questions: list[str]
    citations: list[dict]
    provider_name: Optional[str]
    model_name: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    cost_usd: Optional[float]
    usage_metadata: dict
    usage_node: Optional[str]
    # Tool-use / agentic flow (Batch K). Optional because most node paths
    # never set them; nodes that do (e.g. agentic generate) update via
    # state["..."] = ... rather than the constructor.
    tool_calls: list[str] | list[dict[str, Any]]
    requires_confirmation: bool
    action_summary: str


def create_initial_state(
    question: str,
    trace_id: Optional[str] = None,
    tenant_id: str = "default",
) -> GraphState:
    """
    Удобная фабрика для создания начального состояния графа.

    Обычно порядок такой:
        1) вызываем start_trace() → получаем trace_id;
        2) создаём начальное состояние через create_initial_state(...);
        3) передаём это состояние в graph.invoke(...).

    :param question: вопрос пользователя
    :param trace_id: идентификатор трассы; если не передан, будет сгенерирован
                     новый UUID (полезно для простых локальных тестов).
    :return: объект GraphState (обычный dict с нужными полями)
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())

    state: GraphState = GraphState(
        question=question,
        search_query=None,
        hyde_query=None,
        context_docs=[],
        graded_docs=[],
        doc_grade_reason=None,
        answer=None,
        relevance_score=None,
        quality_score=None,
        claims=[],
        factuality_score=0,
        fact_verification_skipped=False,
        complexity="unknown",
        retrieval_strategy="hybrid",
        route=None,
        trace_id=trace_id,
        tenant_id=tenant_id,
        error=False,
        error_message="",
        error_node="",
        iteration=0,
        max_iterations=2,
        chat_history=[],
        sub_queries=[],
        suggested_questions=[],
        citations=[],
        provider_name=None,
        model_name=None,
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
        usage_metadata={},
        usage_node=None,
    )
    return state
