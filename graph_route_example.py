"""
agent/graph.py — фрагмент с узлом route, работающим через SupportSink.

Предполагается, что:
  * состояние AgentState уже описано в agent/state.py,
  * узлы retrieve / generate / evaluate реализованы выше в этом файле,
  * трассировка в SQLite реализована в tracing/sqlite_trace.py.

Здесь мы добавляем только:
  * утилиту _context_to_text;
  * фабрику узла make_route_node(), которая:
      - решает, какой route выбрать: "auto" или "human";
      - при "human" делает эскалацию через SupportSink;
  * create_support_graph() и run_support_pipeline(), которые
    прокидывают SupportSink в граф.

Эскалация:
  * если quality_score ниже порога или отсутствует,
    бот выбирает route="human" и формирует "карточку" для оператора:
      - вопрос,
      - автоответ,
      - оценки,
      - короткий контекст;
  * эта карточка передаётся в SupportSink:
      - LocalFileSupportSink → строка в support_inbox.jsonl;
      - BitrixSupportSink    → комментарий в Bitrix24.
"""

from __future__ import annotations

import json
from typing import Any, Callable, List

from langgraph.graph import END, StateGraph
from langchain_core.retrievers import BaseRetriever

from agent.state import AgentState, create_initial_state
from tracing.sqlite_trace import start_trace, log_step, finish_trace
from integrations.bitrix import SupportSink
from integrations.mock_inbox import get_support_sink

# Здесь считаем, что узлы retrieve / generate / evaluate уже существуют.
# Для полноты контекста ниже приведены только route / log и сборка графа.


def _context_to_text(context_docs: List[Any], max_chars: int = 800) -> str:
    """
    Преобразует список документов в компактный текст.

    Оператору поддержки обычно не нужен весь контекст целиком.
    Ему достаточно краткого "снимка", чтобы понять, откуда взялся ответ.
    """
    parts: List[str] = []
    for idx, doc in enumerate(context_docs, start=1):
        if hasattr(doc, "page_content"):
            text = getattr(doc, "page_content", "")
            metadata = getattr(doc, "metadata", {}) or {}
        elif isinstance(doc, dict):
            text = doc.get("page_content", "")
            metadata = doc.get("metadata", {}) or {}
        else:
            text = str(doc)
            metadata = {}

        source = metadata.get("source", f"doc_{idx}")
        parts.append(f"[Документ {idx} | source={source}]\n{text}")

    big = "\n\n".join(parts)
    if len(big) > max_chars:
        return big[:max_chars] + "\n\n...[контекст обрезан]..."
    return big


def make_route_node(
    support_sink: SupportSink,
    quality_threshold: int = 70,
) -> Callable[[AgentState], AgentState]:
    """
    Фабрика узла route.

    Логика:
      * если quality_score >= quality_threshold → route = "auto";
      * если quality_score <  quality_threshold → route = "human" и эскалация;
      * если quality_score отсутствует          → route = "human" (перестраховка).

    Зачем так:
      * "auto" — когда модель сама оценила ответ как достаточно хороший;
      * "human" — когда модель не уверена или не смогла себя оценить —
        лучше передать кейс человеку, чем вернуть сомнительный ответ.
    """

    def node(state: AgentState) -> AgentState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        answer = state.get("answer") or ""
        score = state.get("quality_score")
        relevance = state.get("relevance_score")
        context_docs = state.get("context_docs", [])

        new_state = state.copy()

        # 1. Выбираем маршрут.
        if score is None:
            new_state["route"] = "human"
        else:
            new_state["route"] = "auto" if score >= quality_threshold else "human"

        # 2. Если выбрали "human" — формируем пакет для поддержки и
        #    отправляем его через абстракцию SupportSink.
        if new_state["route"] == "human":
            context_snippet = _context_to_text(context_docs, max_chars=800)

            payload = {
                "question": question,
                "answer": answer,
                "route": new_state["route"],
                "quality": score,
                "relevance": relevance,
                "context_snippet": context_snippet,
            }

            message_str = json.dumps(payload, ensure_ascii=False)

            # В простейшем случае используем trace_id как entity_id:
            # так в Bitrix/JSONL можно быстро сопоставить эскалацию
            # с конкретным запуском графа и его трассой в SQLite.
            support_sink.send(entity_id=trace_id, message=message_str)

        # 3. Фиксируем шаг в SQLite‑трассе.
        log_step(trace_id, "route", new_state)
        return new_state

    return node


def make_log_node() -> Callable[[AgentState], AgentState]:
    """Финальный узел: просто логирует итоговое состояние."""
    def node(state: AgentState) -> AgentState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        log_step(trace_id, "log", state)
        return state

    return node


# ---- Сборка графа с учётом SupportSink ----


def create_support_graph(
    retriever: BaseRetriever,
    llm,
    support_sink: SupportSink | None = None,
):
    """
    Собирает LangGraph‑пайтлайн ассистента поддержки.

    Если support_sink не передан явно, берём его из конфигурации
    (get_support_sink → LocalFileSupportSink по умолчанию).
    """
    if support_sink is None:
        support_sink = get_support_sink()

    graph = StateGraph(AgentState)

    # Эти функции должны быть реализованы выше в модуле:
    from agent.graph import make_retrieve_node, make_generate_node, make_evaluate_node  # type: ignore

    graph.add_node("retrieve", make_retrieve_node(retriever))
    graph.add_node("generate", make_generate_node(llm))
    graph.add_node("evaluate", make_evaluate_node(llm))
    graph.add_node("route", make_route_node(support_sink))
    graph.add_node("log", make_log_node())

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "evaluate")
    graph.add_edge("evaluate", "route")
    graph.add_edge("route", "log")
    graph.add_edge("log", END)

    return graph.compile()


def run_support_pipeline(
    question: str,
    retriever: BaseRetriever,
    llm,
    support_sink: SupportSink | None = None,
) -> AgentState:
    """
    Высокоуровневая функция "задать вопрос ассистенту".

    1) создаём trace_id и записываем старт трассы в SQLite;
    2) формируем начальное состояние (question + trace_id);
    3) собираем граф с нужным SupportSink;
    4) запускаем graph.invoke(initial_state);
    5) сохраняем финальное состояние в SQLite;
    6) возвращаем финальное состояние.
    """
    trace_id = start_trace()
    initial_state = create_initial_state(question=question, trace_id=trace_id)

    compiled = create_support_graph(retriever=retriever, llm=llm, support_sink=support_sink)
    final_state: AgentState = compiled.invoke(initial_state)

    finish_trace(trace_id, final_state)
    return final_state
