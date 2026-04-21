"""
agent/prompts.py

Здесь собраны промпты (заготовки текстов) для локальной LLM:

1) Промпт для основного ответа (QA):
   - LLM должна отвечать ТОЛЬКО на основе переданного контекста.
   - Если в контексте недостаточно информации, модель должна честно
     написать об этом и НЕ придумывать факты.

2) Промпт для self-evaluation:
   - LLM оценивает собственный ответ по шкале 1–100.
   - В ответе модель должна вывести ТОЛЬКО число, без пояснений.
   - Далее это число пишется в quality_score.

Комментарии по метрикам качества (их мы используем в описании промпта):

- Answer relevance (релевантность ответа):
    Насколько ответ относится к исходному вопросу.
    Пример: вопрос про ошибку E20 — ответ должен быть про E20,
    а не про гарантию или доставку.

- Answer accuracy (точность / корректность):
    Насколько факты ответа совпадают с тем, что реально написано в
    документах-контексте. Даже очень "красивый" ответ может быть
    неточным, если он придуман и не подтверждается источниками.

- Retrieval quality (качество retrieval-а):
    Это характеристика не самого ответа, а того, какие документы
    вернул retriever:
        * покрывают ли они тему вопроса,
        * не тянут ли "мусорные" фрагменты,
        * не упускают ли важные части.
    От качества retrieval напрямую зависит потолок качества ответа.

В нашем PoC:

- Промпт QA нацелен на высокие Answer relevance и Answer accuracy:
  модель должна строго держаться контекста.

- Промпт self-evaluation просит модель оценить комбинацию этих факторов
  и выдать одну интегральную оценку (quality_score). На основе этого
  в узле route мы принимаем решение, отправлять ли ответ пользователю
  или эскалировать к человеку.
"""

from __future__ import annotations

from typing import List, Dict, Any


def _format_context_block(context_docs: List[Dict[str, Any]]) -> str:
    """
    Вспомогательная функция: превращает список документов в текстовый блок.

    Каждый документ показываем с небольшим заголовком вида:
        [Документ 1 | source=errors_e10_e30.txt]

    Предполагаем, что каждый элемент context_docs — это словарь с ключами:
        "page_content": str
        "metadata": dict (опционально, может быть пустым)
    """
    if not context_docs:
        return "Контекст отсутствует. База знаний не вернула ни одного фрагмента."

    parts = []
    for idx, doc in enumerate(context_docs, start=1):
        text = str(doc.get("page_content", ""))
        metadata = doc.get("metadata", {}) or {}
        source = metadata.get("source") or metadata.get("file_name") or f"doc_{idx}"
        parts.append(f"[Документ {idx} | source={source}]\n{text}")
    return "\n\n".join(parts)


def build_qa_prompt(question: str, context_docs: List[Dict[str, Any]]) -> str:
    """
    Формирует промпт для основного ответа (QA).

    Модель получает:
        - блок КОНТЕКСТ с фрагментами базы знаний;
        - ВОПРОС пользователя;
        - чёткие инструкции "не придумывать лишнего".
    """
    context_block = _format_context_block(context_docs)

    prompt = f"""Ты — ассистент службы поддержки.

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
"""
    return prompt


def build_self_eval_prompt(
    question: str,
    answer: str,
    context_docs: List[Dict[str, Any]],
) -> str:
    """
    Формирует промпт для self-evaluation.

    Модель должна выдать ОДНО целое число от 1 до 100.

    Мы явно описываем три аспекта:

    - Answer relevance:
        Насколько ответ вообще относится к заданному вопросу.

    - Answer accuracy:
        Насколько факты ответа совпадают с содержимым контекста
        (нет ли выдуманной информации, искажений, ошибок).

    - Retrieval quality:
        Насколько предоставленный контекст покрывает тему вопроса и
        не содержит лишнего. Даже при хорошем retrieval модель может
        допустить ошибки, но плохой retrieval сильно снижает максимум
        возможного качества ответа.
    """
    context_block = _format_context_block(context_docs)

    prompt = f"""Ты — эксперт по оценке качества ответов ассистента.

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
"""
    return prompt


def build_extract_claims_prompt(answer: str) -> str:
    return (
        "You are an assistant that breaks a text into atomic factual claims.\n"
        "A claim is a single, verifiable statement of fact.\n"
        "Ignore greetings, meta-commentary, and hedges.\n"
        "Output each claim on its own line, prefixed with '- '.\n"
        "If there are no factual claims, output 'NONE'.\n\n"
        f"Text:\n{answer}\n\nClaims:"
    )


def build_verify_claim_prompt(claim: str, context: str) -> str:
    return (
        "You are a fact-checker. Decide whether the CLAIM is DIRECTLY supported by the CONTEXT.\n"
        "Answer strictly:\n"
        "  SUPPORTED: <one-line quote or paraphrase from context>\n"
        "  UNSUPPORTED\n"
        "Do not use outside knowledge. If context is silent or ambiguous - UNSUPPORTED.\n\n"
        f"CONTEXT:\n{context}\n\nCLAIM: {claim}\n\nAnswer:"
    )


def build_classify_complexity_prompt(question: str) -> str:
    return (
        "Classify the user question as SIMPLE or COMPLEX.\n\n"
        "SIMPLE: factual lookup, single concept, short answer (<5 sentences).\n"
        "  Examples: 'How to reset password?', 'What is X?', 'Where is the Y button?'\n\n"
        "COMPLEX: multi-step reasoning, comparison, analysis, inference,\n"
        "or synthesis across documents.\n"
        "  Examples: 'Compare A and B', 'Explain why X causes Y',\n"
        "            'Analyze this contract against policy Z'\n\n"
        "Output strictly one word: SIMPLE or COMPLEX.\n\n"
        f"Question: {question}\n\nClassification:"
    )


def build_suggested_questions_prompt(
    question: str,
    answer: str,
    context_snippet: str = "",
) -> str:
    """Prompt for generating short follow-up questions."""
    context_block = ""
    if context_snippet:
        context_block = f"\n\nCONTEXT:\n{context_snippet[:500]}"

    return f"""Based on the user question and the assistant answer, propose 3 short follow-up questions.
The questions must:
- stay on topic
- be short (up to 60 characters)
- help the user go one step deeper

QUESTION: {question}
ANSWER: {answer[:500]}{context_block}

Return ONLY 3 questions, one per line. No numbering. No bullets."""


# ---------------------------------------------------------------------------
# Level 2: Query Transformation
# ---------------------------------------------------------------------------


def build_query_transform_prompt(question: str) -> str:
    """Промпт для трансформации пользовательского вопроса в поисковый запрос.

    LLM должна:
    - Убрать разговорный стиль, оставить ключевые термины
    - Добавить синонимы/альтернативные формулировки
    - Расширить аббревиатуры
    - Вернуть ТОЛЬКО переформулированный запрос, без пояснений
    """
    return f"""Ты — специалист по поисковым запросам.

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
"""


# ---------------------------------------------------------------------------
# Level 2: Document Grading (Corrective RAG)
# ---------------------------------------------------------------------------


def build_doc_grade_prompt(
    question: str,
    document: Dict[str, Any],
) -> str:
    """Промпт для оценки релевантности ОДНОГО документа вопросу.

    LLM должна ответить: YES или NO.
    YES — документ содержит информацию, полезную для ответа на вопрос.
    NO — документ не относится к вопросу.
    """
    text = str(document.get("page_content", ""))
    source = (document.get("metadata") or {}).get("source", "unknown")

    return f"""Ты — эксперт по оценке релевантности документов.

Определи, содержит ли данный документ информацию, полезную для ответа
на вопрос пользователя. Учитывай: частичная релевантность тоже считается.

ВОПРОС:
{question}

ДОКУМЕНТ (source={source}):
{text}

Ответь ОДНИМ словом: YES или NO.
"""


# ---------------------------------------------------------------------------
# Level 2: Query Rewrite (для повторной попытки после плохой оценки)
# ---------------------------------------------------------------------------


def build_query_rewrite_prompt(
    question: str,
    previous_answer: str,
    quality_score: int,
) -> str:
    """Промпт для переформулировки запроса после неудачного ответа.

    Используется в Self-RAG цикле, когда quality_score < порога.
    LLM должна предложить другую формулировку, которая найдёт лучшие документы.
    """
    return f"""Ты — специалист по улучшению поисковых запросов.

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
"""


# ---------------------------------------------------------------------------
# Level 3: Conversation-aware QA prompt
# ---------------------------------------------------------------------------


def build_conversational_qa_prompt(
    question: str,
    context_docs: List[Dict[str, Any]],
    chat_history: List[Dict[str, str]],
) -> str:
    """QA-промпт с учётом истории диалога.

    Позволяет обрабатывать уточняющие вопросы:
    - "А что насчёт гарантии?" (после вопроса про ошибку E20)
    - "Расскажи подробнее" (про предыдущий ответ)
    """
    context_block = _format_context_block(context_docs)

    history_block = ""
    if chat_history:
        parts = []
        for msg in chat_history[-5:]:  # Последние 5 сообщений
            role = msg.get("role", "user")
            text = msg.get("content", "")
            label = "Пользователь" if role == "user" else "Ассистент"
            parts.append(f"{label}: {text}")
        history_block = "\n".join(parts)

    if history_block:
        return f"""Ты — ассистент службы поддержки.

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
"""
    else:
        return build_qa_prompt(question=question, context_docs=context_docs)


# ---------------------------------------------------------------------------
# Level 3: Conversation-aware query transform
# ---------------------------------------------------------------------------


def build_conversational_query_transform_prompt(
    question: str,
    chat_history: List[Dict[str, str]],
) -> str:
    """Переформулирует уточняющий вопрос в полноценный поисковый запрос.

    Пример:
        История: "Что делать при ошибке E20?" → "Проверьте охлаждение..."
        Вопрос: "А покрывает ли это гарантия?"
        Результат: "гарантия покрытие ремонт ошибка E20 перегрев двигатель"
    """
    if not chat_history:
        return build_query_transform_prompt(question)

    history_parts = []
    for msg in chat_history[-4:]:
        role = msg.get("role", "user")
        text = msg.get("content", "")[:200]
        label = "Q" if role == "user" else "A"
        history_parts.append(f"{label}: {text}")
    history_block = "\n".join(history_parts)

    return f"""Ты — специалист по поисковым запросам.

Пользователь ведёт диалог с ассистентом поддержки.
Его текущий вопрос может быть уточняющим (ссылается на предыдущие сообщения).

Твоя задача — переформулировать текущий вопрос в самодостаточный поисковый
запрос, который можно использовать для поиска по базе знаний БЕЗ истории.

ИСТОРИЯ ДИАЛОГА:
{history_block}

ТЕКУЩИЙ ВОПРОС:
{question}

Выведи ТОЛЬКО полноценный поисковый запрос, одной строкой:
"""


# ---------------------------------------------------------------------------
# Level 3: Multi-Query decomposition
# ---------------------------------------------------------------------------


def build_multi_query_prompt(question: str) -> str:
    """Промпт для разбиения сложного вопроса на подвопросы.

    Используется MultiQueryRetriever для поиска по каждому аспекту вопроса.
    """
    return f"""Разбей вопрос пользователя на 2-3 независимых поисковых запроса.
Каждый запрос должен искать один конкретный аспект вопроса.
Если вопрос простой и не требует разбиения — верни его как есть.

ВОПРОС:
{question}

Выведи запросы, по одному на строку (2-3 строки, без нумерации и маркеров):
"""
