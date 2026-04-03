# Task 14 — SSE streaming for /api/ask

## Goal
Добавить Server-Sent Events endpoint `/api/ask/stream`, чтобы пользователь видел
прогресс обработки сразу, не ждя 5–7 с с пустым спиннером.
Существующий `/api/ask` (JSON) не трогать — backwards compat.

## Files to change
- `api/app.py` — новый route `/api/ask/stream`
- `static/chat.html` — переключить sendMessage на SSE

---

## 1. api/app.py

### 1a. Добавить импорт (в блок существующих импортов)
```python
from fastapi.responses import StreamingResponse
import asyncio as _asyncio
import json as _json
```

### 1b. Добавить новый route — вставить ПОСЛЕ маршрута `/api/ask`

```python
@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(request: Request, body: AskRequest) -> StreamingResponse:
    """SSE endpoint — немедленно отдаёт статус, затем финальный ответ."""

    async def event_generator() -> AsyncGenerator[str, None]:
        # Событие 1: сигнал о начале обработки
        yield "data: " + _json.dumps({"type": "status", "node": "processing"}) + "\n\n"

        session_id, session = _get_or_create_session(body.session_id)
        question = (body.question or "").strip()

        if not question:
            yield "data: " + _json.dumps({
                "type": "error",
                "detail": "question is required",
            }) + "\n\n"
            return

        _touch_session(session_id)

        try:
            if hasattr(session, "ask"):
                result = await _asyncio.get_event_loop().run_in_executor(
                    None, session.ask, question
                )
                quality = result.get("quality_score") or 50
                route = result.get("route") or "auto"
                answer = result.get("answer") or "Не удалось получить ответ."
                sources = result.get("sources", [])
            else:
                quality, route, answer, sources = 0, "human", "Сессия не инициализирована.", []

            yield "data: " + _json.dumps({
                "type": "result",
                "answer": answer,
                "quality_score": quality,
                "route": route,
                "session_id": session_id,
                "sources": sources,
            }) + "\n\n"

        except Exception as exc:
            logger.error("SSE pipeline error: %s", exc, exc_info=True)
            yield "data: " + _json.dumps({
                "type": "result",
                "answer": "Произошла ошибка. Запрос передан оператору.",
                "quality_score": 0,
                "route": "human",
                "session_id": session_id,
                "sources": [],
            }) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

Добавить в imports в начале функции: `from typing import AsyncGenerator`
(или уже есть — проверь существующие импорты и добавь только если нет).

---

## 2. static/chat.html

### 2a. Найти функцию `async function sendMessage()` и заменить блок fetch

Найти строку (примерно):
```javascript
const response = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: messageText, session_id: sessionId })
});
const data = await response.json();
```

Заменить на:
```javascript
const response = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: messageText, session_id: sessionId })
});

if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
}

// Читаем SSE-поток
const reader = response.body.getReader();
const decoder = new TextDecoder();
let data = null;
let buffer = '';

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // неполная строка остаётся в буфере
    for (const line of lines) {
        if (line.startsWith('data: ')) {
            try {
                const event = JSON.parse(line.slice(6));
                if (event.type === 'status') {
                    // можно обновить placeholder сообщения
                } else if (event.type === 'result') {
                    data = event;
                }
            } catch (_) {}
        }
    }
}

if (!data) throw new Error('No result received');
```

Остальная обработка `data` (отображение ответа, бейджи, session_id) остаётся без изменений.

---

## CONSTRAINTS
- Изменить только `api/app.py` и `static/chat.html`
- `/api/ask` (JSON endpoint) — не трогать
- `AsyncGenerator` import — добавить только если отсутствует в файле
- `pytest tests/ -v` должны проходить

## DONE WHEN
- [ ] `POST /api/ask/stream` возвращает `text/event-stream`
- [ ] Первое событие `{"type":"status","node":"processing"}` приходит немедленно
- [ ] Последнее событие содержит `answer`, `quality_score`, `route`, `session_id`
- [ ] chat.html использует этот endpoint вместо `/api/ask`
- [ ] `pytest tests/ -v` — 19 passed
