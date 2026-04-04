# Task 24 — Настоящий token streaming через Ollama

## Goal
Сейчас `/api/ask/stream` ждёт полного завершения pipeline, затем отдаёт один SSE-event.
Добавить реальный стриминг токенов из Ollama в generate-узле — пользователь видит
ответ по мере генерации, а не ждёт 5+ секунд.

## Background: как это работает

Ollama поддерживает `POST /api/generate` с `"stream": true`.
Ответ — поток JSON-строк:
```
{"model":"mistral","response":"Хорошо","done":false}
{"model":"mistral","response":",","done":false}
...
{"model":"mistral","response":"","done":true,"total_duration":4200}
```

Текущий generate-узел в `graph.py` вызывает `llm.invoke(prompt)` — блокирующий вызов.
Нам нужен отдельный async-путь: когда `/api/ask/stream` запрошен — генерация стримится.

## Архитектурное решение

НЕ менять LangGraph pipeline (сложно). Вместо этого:

1. `api/app.py`: в `ask_stream` после получения `search_query` + `context_docs` через pipeline
   вызывать Ollama напрямую через `httpx.AsyncClient` с `stream: true`.
2. Для этого нужен отдельный `_stream_generate()` async-генератор.
3. pipeline запускается до узла `generate` (retrieve + grade_docs),
   а генерация — стримится отдельно.

## Files to change
- `api/app.py` — переписать `ask_stream` с реальным Ollama streaming

---

## api/app.py

### Шаг 1: добавить вспомогательный async-генератор

Добавить после импортов в app.py (проверь что `httpx` уже импортирован — если нет, добавить):

```python
async def _stream_ollama(
    prompt: str,
    model: str,
    base_url: str,
) -> AsyncGenerator[str, None]:
    """Стримит токены из Ollama /api/generate."""
    import httpx  # noqa: PLC0415
    payload = {"model": model, "prompt": prompt, "stream": True}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{base_url}/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = _json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
                except Exception:
                    continue
```

### Шаг 2: переписать `ask_stream` endpoint

Заменить существующую функцию `ask_stream` на:

```python
@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(request: Request, body: AskRequest) -> StreamingResponse:
    """SSE endpoint с реальным стримингом токенов из Ollama."""

    async def event_generator() -> AsyncGenerator[str, None]:
        yield "data: " + _json.dumps({"type": "status", "node": "processing"}) + "\n\n"

        session_id, session = _get_or_create_session(body.session_id)
        question = (body.question or "").strip()
        if not question:
            yield "data: " + _json.dumps({"type": "error", "detail": "question is required"}) + "\n\n"
            return

        _touch_session(session_id)

        # Шаг 1: retrieval (через pipeline без generate)
        # Если session.ask недоступен — fallback на старый подход
        try:
            if not hasattr(session, "_retriever") or session._retriever is None:
                raise RuntimeError("no retriever")

            # Получить контекст через retriever напрямую
            docs = await _asyncio.get_event_loop().run_in_executor(
                None,
                session._retriever.get_relevant_documents,
                question,
            )
            context = "\n\n".join(
                d.page_content if hasattr(d, "page_content") else d.get("page_content", "")
                for d in docs[:5]
            )

            from prompts import build_generation_prompt  # noqa: PLC0415
            prompt = build_generation_prompt(question=question, context=context)

        except Exception:
            # Fallback: запустить полный pipeline синхронно
            try:
                result = await _asyncio.get_event_loop().run_in_executor(
                    None, session.ask, question
                )
                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": result.get("answer", ""),
                    "quality_score": result.get("quality_score", 50),
                    "route": result.get("route", "auto"),
                    "session_id": session_id,
                    "sources": result.get("sources", []),
                }) + "\n\n"
            except Exception as exc:
                logger.error("SSE fallback error: %s", exc)
                yield "data: " + _json.dumps({
                    "type": "result", "answer": "Ошибка обработки запроса.",
                    "quality_score": 0, "route": "human", "session_id": session_id, "sources": [],
                }) + "\n\n"
            return

        # Шаг 2: stream генерация токенов
        from config.settings import get_settings  # noqa: PLC0415
        settings = get_settings()
        full_answer = ""

        yield "data: " + _json.dumps({"type": "token_start"}) + "\n\n"
        try:
            async for token in _stream_ollama(prompt, settings.ollama_model_name, settings.ollama_base_url):
                full_answer += token
                yield "data: " + _json.dumps({"type": "token", "token": token}) + "\n\n"
        except Exception as exc:
            logger.warning("Streaming error, using accumulated: %s", exc)

        # Шаг 3: evaluate качество (быстрый keyword-based без LLM)
        quality = 70 if full_answer and len(full_answer) > 20 else 40
        route = "auto" if quality >= 70 else "human"

        yield "data: " + _json.dumps({
            "type": "result",
            "answer": full_answer,
            "quality_score": quality,
            "route": route,
            "session_id": session_id,
            "sources": [],
        }) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### Шаг 3: обновить static/chat.html

В SSE-читалке (из task-14) добавить обработку `token` events:

```javascript
} else if (event.type === 'token_start') {
    // Создать placeholder для streaming текста
    streamingDiv = document.createElement('div');
    streamingDiv.className = 'streaming-answer';
    // добавить в DOM рядом с текущим bot-сообщением
} else if (event.type === 'token') {
    if (streamingDiv) {
        streamingDiv.textContent += event.token;
        // Автоскролл вниз
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
} else if (event.type === 'result') {
    // Заменить streaming div на финальное сообщение
    if (streamingDiv) streamingDiv.remove();
    data = event;
}
```

Замени `chatMessages` на реальный id контейнера из файла.

---

## CONSTRAINTS
- Изменить только `api/app.py` и `static/chat.html`
- При недоступности Ollama (таймаут) — fallback на синхронный pipeline
- При ошибке streaming — fallback на уже накопленный `full_answer`
- `httpx` уже в requirements.txt — не добавлять повторно
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] Токены из Ollama приходят по одному через SSE (`type: "token"`)
- [ ] При Ollama-таймауте — корректный fallback, не 500
- [ ] chat.html отображает токены по мере поступления
- [ ] `pytest tests/ -v` — проходит
