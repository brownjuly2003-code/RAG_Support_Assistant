"""
agent/prompts.py

Prompt templates and builders for the RAG assistant.
"""

from __future__ import annotations

from typing import Any, Dict, List

PROMPT_REGISTRY: dict[str, dict[str, str]] = {
    "qa": {
        "prompt_id": "QA_PROMPT_V1",
        "text": """Ты — ассистент службы поддержки.

Тебе дан контекст из базы знаний и вопрос пользователя.
Твоя задача — ответить строго по этому контексту.

Если в контексте НЕТ информации, достаточной для уверенного ответа,
честно напиши, что по имеющимся данным ответить нельзя,
и предложи обратиться к специалисту поддержки.
НЕЛЬЗЯ придумывать факты, которых нет в предоставленном тексте.

--------------------
КОНТЕКСТ:
{context_block}
--------------------

ВОПРОС:
{question}

Если ты ссылаешься на конкретный факт из контекста, сразу добавляй [N],
где N — номер документа в списке контекста, начиная с 1.
Не придумывай номера цитат. Если утверждение не подтверждено контекстом,
не добавляй ссылку.

Сформулируй понятный, краткий и точный ответ для пользователя:
""",
    },
    "self_eval": {
        "prompt_id": "SELF_EVAL_PROMPT_V1",
        "text": """Ты — эксперт по оценке качества ответов ассистента.

Тебе дан:
1) вопрос пользователя;
2) контекст (фрагменты базы знаний);
3) ответ ассистента на этот вопрос.

Оцени качество ответа по шкале от 1 до 100.

При оценке учитывай:
- Answer relevance (релевантность):
    Насколько ответ вообще относится к вопросу, отвечает ли по сути.

- Answer accuracy (точность):
    Насколько факты в ответе соответствуют тексту из контекста.
    Нельзя "награждать" ответ, который придумывает факты.

- Retrieval quality (качество retrieval-а):
    Насколько контекст, который использовал ассистент, покрывает тему
    вопроса и не содержит лишнего мусора. Если нужной информации
    в контексте нет, это также снижает конечную оценку качества ответа.

Твоя задача — вывести ОДНО ЦЕЛОЕ число от 1 до 100,
где 1 — ответ ужасный, 50 — средний, 100 — отличный.

В ОТВЕТЕ ВЫВЕДИ ТОЛЬКО ЧИСЛО, БЕЗ СЛОВ И КОММЕНТАРИЕВ.

--------------------
ВОПРОС:
{question}
--------------------
КОНТЕКСТ:
{context_block}
--------------------
ОТВЕТ АССИСТЕНТА:
{answer}
--------------------

Выведи только целое число от 1 до 100:
""",
    },
    "extract_claims": {
        "prompt_id": "EXTRACT_CLAIMS_PROMPT_V1",
        "text": """You are an assistant that breaks a text into atomic factual claims.
A claim is a single, verifiable statement of fact.
Ignore greetings, meta-commentary, and hedges.
Output each claim on its own line, prefixed with '- '.
If there are no factual claims, output 'NONE'.

Text:
{answer}

Claims:""",
    },
    "verify_claim": {
        "prompt_id": "VERIFY_CLAIM_PROMPT_V1",
        "text": """You are a fact-checker. Decide whether the CLAIM is DIRECTLY supported by the CONTEXT.
Answer strictly:
  SUPPORTED: <one-line quote or paraphrase from context>
  UNSUPPORTED
Do not use outside knowledge. If context is silent or ambiguous - UNSUPPORTED.

CONTEXT:
{context}

CLAIM: {claim}

Answer:""",
    },
    "classify_complexity": {
        "prompt_id": "CLASSIFY_COMPLEXITY_PROMPT_V1",
        "text": """Classify the user question as SIMPLE or COMPLEX.

SIMPLE: factual lookup, single concept, short answer (<5 sentences).
  Examples: 'How to reset password?', 'What is X?', 'Where is the Y button?'

COMPLEX: multi-step reasoning, comparison, analysis, inference,
or synthesis across documents.
  Examples: 'Compare A and B', 'Explain why X causes Y',
            'Analyze this contract against policy Z'

Output strictly one word: SIMPLE or COMPLEX.

Question: {question}

Classification:""",
    },
    "suggested_questions": {
        "prompt_id": "SUGGESTED_QUESTIONS_PROMPT_V1",
        "text": """Based on the user question and the assistant answer, propose 3 short follow-up questions.
The questions must:
- stay on topic
- be short (up to 60 characters)
- help the user go one step deeper

QUESTION: {question}
ANSWER: {answer_excerpt}{context_block}

Return ONLY 3 questions, one per line. No numbering. No bullets.""",
    },
    "query_transform": {
        "prompt_id": "QUERY_TRANSFORM_PROMPT_V1",
        "text": """Ты — специалист по поисковым запросам.

Пользователь задал вопрос к базе знаний технической поддержки.
Твоя задача — переформулировать вопрос в оптимальный поисковый запрос,
чтобы найти максимально релевантные документы.

Правила:
- Убери разговорный стиль, оставь ключевые термины
- Добавь синонимы и альтернативные термины через пробел
- Если есть коды ошибок (E20, E21...) — оставь как есть
- Если вопрос уже лаконичный — верни его без изменений
- Выведи ТОЛЬКО переформулированный запрос, одной строкой, БЕЗ пояснений

ВОПРОС:
{question}

Поисковый запрос:
""",
    },
    "doc_grade": {
        "prompt_id": "DOC_GRADE_PROMPT_V1",
        "text": """Ты — эксперт по оценке релевантности документов.

Определи, содержит ли данный документ информацию, полезную для ответа
на вопрос пользователя. Учитывай: частичная релевантность тоже считается.

ВОПРОС:
{question}

ДОКУМЕНТ (source={source}):
{text}

Ответь ОДНИМ словом: YES или NO.
""",
    },
    "doc_grade_batch": {
        "prompt_id": "DOC_GRADE_BATCH_PROMPT_V1",
        "text": """Ты — эксперт по оценке релевантности документов.

Для каждого документа определи, содержит ли он информацию, полезную для ответа
на вопрос пользователя. Учитывай: частичная релевантность тоже считается.

ВОПРОС:
{question}

ДОКУМЕНТЫ:
{documents}

Верни только JSON без Markdown:
{{"grades":[{{"index":1,"relevant":true,"reason":"коротко"}}]}}
""",
    },
    "query_rewrite": {
        "prompt_id": "QUERY_REWRITE_PROMPT_V1",
        "text": """Ты — специалист по улучшению поисковых запросов.

Система пыталась ответить на вопрос пользователя, но качество ответа
оказалось низким (оценка: {quality_score}/100).

Исходный вопрос:
{question}

Предыдущий ответ (неудачный):
{previous_answer}

Твоя задача — переформулировать вопрос так, чтобы поиск по базе знаний
нашёл более релевантные документы. Попробуй:
- Использовать другие ключевые слова
- Разбить сложный вопрос на более конкретный
- Добавить контекст или уточнения

Выведи ТОЛЬКО новый поисковый запрос, одной строкой, БЕЗ пояснений:
""",
    },
    "conversational_qa": {
        "prompt_id": "CONVERSATIONAL_QA_PROMPT_V1",
        "text": """Ты — ассистент службы поддержки.

Тебе дан контекст из базы знаний, история диалога и текущий вопрос.
Используй историю, чтобы понять контекст уточняющих вопросов.
Отвечай строго по контексту из базы знаний.

--------------------
ИСТОРИЯ ДИАЛОГА:
{history_block}
--------------------
КОНТЕКСТ:
{context_block}
--------------------

ТЕКУЩИЙ ВОПРОС:
{question}

Если ты ссылаешься на конкретный факт из контекста, сразу добавляй [N],
где N — номер документа в списке контекста, начиная с 1.
Не придумывай номера цитат. Если утверждение не подтверждено контекстом,
не добавляй ссылку.

Ответ:
""",
    },
    "conversational_query_transform": {
        "prompt_id": "CONVERSATIONAL_QUERY_TRANSFORM_PROMPT_V1",
        "text": """Ты — специалист по поисковым запросам.

Пользователь ведёт диалог с ассистентом поддержки.
Его текущий вопрос может быть уточняющим (ссылается на предыдущие сообщения).

Твоя задача — переформулировать текущий вопрос в самодостаточный поисковый
запрос, который можно использовать для поиска по базе знаний БЕЗ истории.

ИСТОРИЯ ДИАЛОГА:
{history_block}

ТЕКУЩИЙ ВОПРОС:
{question}

Выведи ТОЛЬКО полноценный поисковый запрос, одной строкой:
""",
    },
    "multi_query": {
        "prompt_id": "MULTI_QUERY_PROMPT_V1",
        "text": """Разбей вопрос пользователя на 2-3 независимых поисковых запроса.
Каждый запрос должен искать один конкретный аспект вопроса.
Если вопрос простой и не требует разбиения — верни его как есть.

ВОПРОС:
{question}

Выведи запросы, по одному на строку (2-3 строки, без нумерации и маркеров):
""",
    },
}
# BEGIN DEPLOYED_PROMPT_OVERRIDES
DEPLOYED_PROMPT_OVERRIDES: dict[str, str] = {}
# END DEPLOYED_PROMPT_OVERRIDES


def _resolve_prompt(name: str, experiment: Any | None = None) -> str:
    from agent.prompt_registry import get_prompt

    return get_prompt(name, experiment)


def _format_context_block(context_docs: List[Dict[str, Any]]) -> str:
    if not context_docs:
        return "Контекст отсутствует. База знаний не вернула ни одного фрагмента."

    parts = []
    for idx, doc in enumerate(context_docs, start=1):
        text = str(doc.get("page_content", ""))
        metadata = doc.get("metadata", {}) or {}
        source = metadata.get("source") or metadata.get("file_name") or f"doc_{idx}"
        parts.append(f"[Документ {idx} | source={source}]\n{text}")
    return "\n\n".join(parts)


def build_qa_prompt(
    question: str,
    context_docs: List[Dict[str, Any]],
    experiment: Any | None = None,
) -> str:
    context_block = _format_context_block(context_docs)
    return _resolve_prompt("qa", experiment).format(
        context_block=context_block,
        question=question,
    )


def build_self_eval_prompt(
    question: str,
    answer: str,
    context_docs: List[Dict[str, Any]],
    experiment: Any | None = None,
) -> str:
    context_block = _format_context_block(context_docs)
    return _resolve_prompt("self_eval", experiment).format(
        question=question,
        context_block=context_block,
        answer=answer,
    )


def build_extract_claims_prompt(answer: str, experiment: Any | None = None) -> str:
    return _resolve_prompt("extract_claims", experiment).format(answer=answer)


def build_verify_claim_prompt(
    claim: str,
    context: str,
    experiment: Any | None = None,
) -> str:
    return _resolve_prompt("verify_claim", experiment).format(
        context=context,
        claim=claim,
    )


def build_classify_complexity_prompt(question: str, experiment: Any | None = None) -> str:
    return _resolve_prompt("classify_complexity", experiment).format(question=question)


def build_suggested_questions_prompt(
    question: str,
    answer: str,
    context_snippet: str = "",
    experiment: Any | None = None,
) -> str:
    context_block = ""
    if context_snippet:
        context_block = f"\n\nCONTEXT:\n{context_snippet[:500]}"
    return _resolve_prompt("suggested_questions", experiment).format(
        question=question,
        answer_excerpt=answer[:500],
        context_block=context_block,
    )


def build_query_transform_prompt(question: str, experiment: Any | None = None) -> str:
    return _resolve_prompt("query_transform", experiment).format(question=question)


def build_doc_grade_prompt(
    question: str,
    document: Dict[str, Any],
    experiment: Any | None = None,
) -> str:
    text = str(document.get("page_content", ""))
    source = (document.get("metadata") or {}).get("source", "unknown")
    return _resolve_prompt("doc_grade", experiment).format(
        question=question,
        source=source,
        text=text,
    )


def build_doc_grade_batch_prompt(
    question: str,
    documents: List[Dict[str, Any]],
    experiment: Any | None = None,
) -> str:
    parts = []
    for idx, document in enumerate(documents, start=1):
        text = str(document.get("page_content", ""))
        metadata = document.get("metadata") or {}
        source = metadata.get("source") or metadata.get("file_name") or f"doc_{idx}"
        parts.append(f"[{idx}] source={source}\n{text}")
    return _resolve_prompt("doc_grade_batch", experiment).format(
        question=question,
        documents="\n\n".join(parts),
    )


def build_query_rewrite_prompt(
    question: str,
    previous_answer: str,
    quality_score: int,
    experiment: Any | None = None,
) -> str:
    return _resolve_prompt("query_rewrite", experiment).format(
        quality_score=quality_score,
        question=question,
        previous_answer=previous_answer,
    )


def build_conversational_qa_prompt(
    question: str,
    context_docs: List[Dict[str, Any]],
    chat_history: List[Dict[str, str]],
    experiment: Any | None = None,
) -> str:
    context_block = _format_context_block(context_docs)
    history_block = ""
    if chat_history:
        parts = []
        for msg in chat_history[-5:]:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            label = "Пользователь" if role == "user" else "Ассистент"
            parts.append(f"{label}: {text}")
        history_block = "\n".join(parts)

    if history_block:
        return _resolve_prompt("conversational_qa", experiment).format(
            history_block=history_block,
            context_block=context_block,
            question=question,
        )
    return build_qa_prompt(question=question, context_docs=context_docs, experiment=experiment)


def build_conversational_query_transform_prompt(
    question: str,
    chat_history: List[Dict[str, str]],
    experiment: Any | None = None,
) -> str:
    if not chat_history:
        return build_query_transform_prompt(question, experiment)

    history_parts = []
    for msg in chat_history[-4:]:
        role = msg.get("role", "user")
        text = msg.get("content", "")[:200]
        label = "Q" if role == "user" else "A"
        history_parts.append(f"{label}: {text}")
    history_block = "\n".join(history_parts)

    return _resolve_prompt("conversational_query_transform", experiment).format(
        history_block=history_block,
        question=question,
    )


def build_multi_query_prompt(question: str, experiment: Any | None = None) -> str:
    return _resolve_prompt("multi_query", experiment).format(question=question)
