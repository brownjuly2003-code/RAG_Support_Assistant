"""
agent/graph.py

LangGraph-пайплайн для RAG-ассистента (Level 1-3).

Level 1: retrieve → generate → evaluate → route
Level 2: + transform_query, grade_docs (Corrective RAG), Self-RAG retry loop
Level 3: + conversation memory, multi-query retrieval, contextual retrieval
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Protocol

from langgraph.graph import END, StateGraph

# Support both package-style and root-level imports
try:
    from agent.state import GraphState, create_initial_state
    from agent.prompts import (
        build_qa_prompt,
        build_self_eval_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from tracing.sqlite_trace import start_trace, log_step, finish_trace
except ImportError:
    from state import GraphState, create_initial_state
    from prompts import (
        build_qa_prompt,
        build_self_eval_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from sqlite_trace import start_trace, log_step, finish_trace


# ---------------------------------------------------------------------------
# Интерфейс для LLM (простой протокол)
# ---------------------------------------------------------------------------


class SupportsInvoke(Protocol):
    """Протокол для объектов, у которых есть метод invoke(prompt: str) -> str."""

    def invoke(self, prompt: str) -> str:  # pragma: no cover
        ...


class LocalOllamaLLM:
    """Обёртка над локальной моделью Ollama."""

    def __init__(self, model_name: str = "mistral"):
        from langchain_community.llms import Ollama
        self._llm = Ollama(model=model_name)

    def invoke(self, prompt: str) -> str:
        return self._llm.invoke(prompt)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _docs_to_plain_dicts(docs: List[Any]) -> List[Dict[str, Any]]:
    """Преобразует Document объекты в plain dicts для JSON/SQLite."""
    plain_docs: List[Dict[str, Any]] = []
    for doc in docs:
        if hasattr(doc, "page_content"):
            text = getattr(doc, "page_content", "")
            metadata = getattr(doc, "metadata", {}) or {}
        elif isinstance(doc, dict):
            text = doc.get("page_content", "")
            metadata = doc.get("metadata", {}) or {}
        else:
            text = str(doc)
            metadata = {}
        plain_docs.append({"page_content": text, "metadata": metadata})
    return plain_docs


def _parse_int_score(text: str, default: int = 50) -> int:
    """Извлекает целое число 1-100 из текста."""
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return default
    value = int(numbers[0])
    return max(1, min(100, value))


# ---------------------------------------------------------------------------
# Level 2: Query Transform node
# ---------------------------------------------------------------------------


def make_transform_query_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел transform_query: переформулирует вопрос в поисковый запрос.

    Level 3: учитывает chat_history для уточняющих вопросов.
    """

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        chat_history = state.get("chat_history", [])

        # Если search_query уже задан (rewrite_query это сделал), не перезаписываем
        if state.get("search_query"):
            log_step(trace_id, "transform_query", state)
            return state

        # Level 3: conversation-aware transform
        if chat_history:
            prompt = build_conversational_query_transform_prompt(question, chat_history)
        else:
            prompt = build_query_transform_prompt(question)

        try:
            search_query = llm.invoke(prompt).strip()
            if not search_query or len(search_query) < 3:
                search_query = question
        except Exception as exc:
            print(f"[transform_query] LLM error: {exc}")
            search_query = question

        new_state: GraphState = {
            **state,
            "search_query": search_query,
        }
        log_step(trace_id, "transform_query", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 1: Retrieve node (updated to use search_query)
# ---------------------------------------------------------------------------


def make_retrieve_node(retriever: Any) -> Callable[[GraphState], GraphState]:
    """Узел retrieve: ищет документы по search_query (или question как fallback)."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        # Используем трансформированный запрос, если есть
        query = state.get("search_query") or state.get("question", "")

        try:
            docs = retriever.get_relevant_documents(query)
        except Exception as exc:
            print(f"[retrieve] Error: {exc}")
            docs = []

        plain_docs = _docs_to_plain_dicts(docs)

        new_state: GraphState = {
            **state,
            "context_docs": plain_docs,
        }
        log_step(trace_id, "retrieve", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 2: Grade Documents node (Corrective RAG)
# ---------------------------------------------------------------------------


def make_grade_docs_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел grade_docs: оценивает каждый документ на релевантность.

    Corrective RAG: LLM проверяет каждый документ (YES/NO).
    Нерелевантные отфильтровываются → в graded_docs попадают только полезные.
    """

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        context_docs = state.get("context_docs", []) or []

        if not context_docs:
            new_state: GraphState = {
                **state,
                "graded_docs": [],
                "doc_grade_reason": "No documents retrieved",
            }
            log_step(trace_id, "grade_docs", new_state)
            return new_state

        graded: List[Dict[str, Any]] = []
        filtered_count = 0

        for doc in context_docs:
            prompt = build_doc_grade_prompt(question=question, document=doc)
            try:
                verdict = llm.invoke(prompt).strip().upper()
                is_relevant = verdict.startswith("YES")
            except Exception as exc:
                print(f"[grade_docs] LLM error: {exc}")
                # При ошибке — оставляем документ (безопасный fallback)
                is_relevant = True

            if is_relevant:
                graded.append(doc)
            else:
                filtered_count += 1

        reason = f"Kept {len(graded)}/{len(context_docs)}, filtered {filtered_count}"

        new_state: GraphState = {
            **state,
            "graded_docs": graded,
            "doc_grade_reason": reason,
        }
        log_step(trace_id, "grade_docs", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 1: Generate node (updated to use graded_docs)
# ---------------------------------------------------------------------------


def make_generate_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел generate: формирует ответ. Level 3: учитывает chat_history."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        docs = state.get("graded_docs") or state.get("context_docs", []) or []
        chat_history = state.get("chat_history", [])

        # Level 3: conversation-aware generation
        if chat_history:
            prompt = build_conversational_qa_prompt(
                question=question, context_docs=docs, chat_history=chat_history,
            )
        else:
            prompt = build_qa_prompt(question=question, context_docs=docs)

        try:
            answer = llm.invoke(prompt)
        except Exception as exc:
            print(f"[generate] LLM error: {exc}")
            answer = "Извините, при обработке запроса произошла внутренняя ошибка."

        new_state: GraphState = {
            **state,
            "answer": answer,
        }
        log_step(trace_id, "generate", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 1: Evaluate node
# ---------------------------------------------------------------------------


def make_evaluate_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел evaluate: самооценка качества ответа (1-100)."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        answer = state.get("answer") or ""
        docs = state.get("graded_docs") or state.get("context_docs", []) or []

        prompt = build_self_eval_prompt(
            question=question, answer=answer, context_docs=docs,
        )

        try:
            raw = llm.invoke(prompt)
        except Exception as exc:
            print(f"[evaluate] LLM error: {exc}")
            raw = ""

        score = _parse_int_score(raw, default=50)
        relevance = round(score / 100.0, 3)

        new_state: GraphState = {
            **state,
            "quality_score": score,
            "relevance_score": relevance,
        }
        log_step(trace_id, "evaluate", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 2: Route or Retry (Self-RAG loop)
# ---------------------------------------------------------------------------


def make_route_or_retry_node(
    min_quality: int = 80,
    min_relevance: float = 0.8,
) -> Callable[[GraphState], GraphState]:
    """Узел route_or_retry: решает — финал или повторная попытка.

    Логика:
    - quality >= min_quality → route="auto" → END
    - quality < min_quality и iteration < max_iterations → route="retry"
    - quality < min_quality и итерации кончились → route="human" → END
    """

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        q = state.get("quality_score")
        r = state.get("relevance_score")
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 2)

        if q is None or r is None:
            route = "human"
        elif q >= min_quality and r >= min_relevance:
            route = "auto"
        elif iteration < max_iter:
            route = "retry"
        else:
            route = "human"

        new_state: GraphState = {
            **state,
            "route": route,
        }
        log_step(trace_id, "route_or_retry", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Level 2: Rewrite Query (для Self-RAG retry)
# ---------------------------------------------------------------------------


def make_rewrite_query_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел rewrite_query: переформулирует запрос после неудачного ответа.

    Используется только при route="retry" (Self-RAG цикл).
    Инкрементирует iteration, сбрасывает search_query для нового поиска.
    """

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        question = state.get("question", "")
        previous_answer = state.get("answer") or ""
        quality_score = state.get("quality_score") or 50
        iteration = state.get("iteration", 0)

        prompt = build_query_rewrite_prompt(
            question=question,
            previous_answer=previous_answer,
            quality_score=quality_score,
        )

        try:
            new_query = llm.invoke(prompt).strip()
            if not new_query or len(new_query) < 3:
                new_query = question
        except Exception as exc:
            print(f"[rewrite_query] LLM error: {exc}")
            new_query = question

        new_state: GraphState = {
            **state,
            "search_query": new_query,
            "iteration": iteration + 1,
            # Сбрасываем промежуточные результаты для нового цикла
            "context_docs": [],
            "graded_docs": [],
            "answer": None,
            "quality_score": None,
            "relevance_score": None,
        }
        log_step(trace_id, "rewrite_query", new_state)
        return new_state

    return node


# ---------------------------------------------------------------------------
# Log node
# ---------------------------------------------------------------------------


def make_log_node() -> Callable[[GraphState], GraphState]:
    """Финальный узел: логирует итоговое состояние."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        log_step(trace_id, "log", state)
        return state

    return node


# ---------------------------------------------------------------------------
# Conditional routing function
# ---------------------------------------------------------------------------


def _should_retry(state: GraphState) -> str:
    """Conditional edge: определяет, куда идти после route_or_retry.

    Returns:
        "retry" → rewrite_query → retrieve → grade_docs → generate → evaluate → ...
        "end"   → log → END
    """
    route = state.get("route", "human")
    if route == "retry":
        return "retry"
    return "end"


# ---------------------------------------------------------------------------
# Сборка графа (Level 2: Corrective & Self-RAG)
# ---------------------------------------------------------------------------


def build_support_graph(
    retriever: Any,
    llm: SupportsInvoke | None = None,
    min_quality: int = 80,
    max_iterations: int = 2,
):
    """Собирает и компилирует граф LangGraph Level 2.

    Граф:
        transform_query → retrieve → grade_docs → generate → evaluate
            → route_or_retry ─┬─ (retry) → rewrite_query → retrieve → ...
                               └─ (end)   → log → END
    """
    if llm is None:
        llm = LocalOllamaLLM(model_name="mistral")

    workflow = StateGraph(GraphState)

    # Регистрируем узлы
    workflow.add_node("transform_query", make_transform_query_node(llm))
    workflow.add_node("retrieve", make_retrieve_node(retriever))
    workflow.add_node("grade_docs", make_grade_docs_node(llm))
    workflow.add_node("generate", make_generate_node(llm))
    workflow.add_node("evaluate", make_evaluate_node(llm))
    workflow.add_node("route_or_retry", make_route_or_retry_node(min_quality=min_quality))
    workflow.add_node("rewrite_query", make_rewrite_query_node(llm))
    workflow.add_node("log", make_log_node())

    # Основной путь
    workflow.set_entry_point("transform_query")
    workflow.add_edge("transform_query", "retrieve")
    workflow.add_edge("retrieve", "grade_docs")
    workflow.add_edge("grade_docs", "generate")
    workflow.add_edge("generate", "evaluate")
    workflow.add_edge("evaluate", "route_or_retry")

    # Conditional: retry или finish
    workflow.add_conditional_edges(
        "route_or_retry",
        _should_retry,
        {
            "retry": "rewrite_query",
            "end": "log",
        },
    )

    # Retry path: rewrite → retrieve → grade → generate → evaluate → route_or_retry
    workflow.add_edge("rewrite_query", "retrieve")

    # Финал
    workflow.add_edge("log", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Высокоуровневая функция запуска (обратная совместимость)
# ---------------------------------------------------------------------------


def run_qa_pipeline(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: List[Dict[str, str]] | None = None,
) -> GraphState:
    """Обрабатывает один вопрос через граф.

    Args:
        question: вопрос пользователя.
        retriever: retriever для поиска документов.
        llm: LLM для генерации.
        max_iterations: макс. итераций Self-RAG.
        chat_history: история диалога (Level 3).
    """
    trace_id = start_trace()
    initial_state = create_initial_state(question=question, trace_id=trace_id)
    initial_state["max_iterations"] = max_iterations
    if chat_history:
        initial_state["chat_history"] = chat_history

    graph = build_support_graph(
        retriever=retriever,
        llm=llm,
        max_iterations=max_iterations,
    )

    final_state = graph.invoke(initial_state)
    finish_trace(trace_id, final_state)
    return final_state


# ---------------------------------------------------------------------------
# Level 3: Conversation Session (multi-turn)
# ---------------------------------------------------------------------------


class ConversationSession:
    """Управляет многоходовым диалогом с RAG-ассистентом.

    Хранит историю и автоматически передаёт её в каждый вызов графа.

    Пример:
        session = ConversationSession(retriever=ret, llm=llm)

        r1 = session.ask("Что означает ошибка E20?")
        print(r1["answer"])  # "E20 — перегрев двигателя..."

        r2 = session.ask("А покрывает ли это гарантия?")
        print(r2["answer"])  # "Гарантия действует 3 года..." (знает контекст!)
    """

    def __init__(
        self,
        retriever: Any,
        llm: SupportsInvoke | None = None,
        max_iterations: int = 2,
        max_history: int = 10,
    ):
        self._retriever = retriever
        self._llm = llm
        self._max_iterations = max_iterations
        self._max_history = max_history
        self._history: List[Dict[str, str]] = []

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def ask(self, question: str) -> GraphState:
        """Задаёт вопрос с учётом истории диалога."""
        result = run_qa_pipeline(
            question=question,
            retriever=self._retriever,
            llm=self._llm,
            max_iterations=self._max_iterations,
            chat_history=self._history,
        )

        # Сохраняем в историю
        self._history.append({"role": "user", "content": question})
        answer = result.get("answer") or ""
        self._history.append({"role": "assistant", "content": answer})

        # Обрезаем историю
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-(self._max_history * 2):]

        return result

    def clear(self) -> None:
        """Сбрасывает историю."""
        self._history.clear()
