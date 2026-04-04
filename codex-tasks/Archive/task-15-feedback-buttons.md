# Task 15 — Feedback buttons (👍/👎) on bot messages

## Goal
Дать пользователю возможность оценить каждый ответ ассистента.
Фидбек сохраняется в SQLite и используется для аудита качества и настройки порогов.

## Files to change
- `sqlite_trace.py` — добавить таблицу `feedback` и функцию `save_feedback()`
- `api/app.py` — добавить `POST /api/feedback`
- `static/chat.html` — добавить кнопки 👍/👎 к каждому ответу бота

---

## 1. sqlite_trace.py

### 1a. В функции `_init_db()` добавить CREATE TABLE после trace_steps

```python
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id    TEXT,
        session_id  TEXT,
        rating      TEXT CHECK(rating IN ('up','down')),
        reason      TEXT,
        ts          TEXT
    );
    """
)
```

### 1b. Добавить новую функцию после `finish_trace()`

```python
def save_feedback(
    trace_id: str,
    session_id: str,
    rating: str,          # "up" or "down"
    reason: str = "",
) -> None:
    """Сохраняет пользовательский фидбек на ответ ассистента."""
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback (trace_id, session_id, rating, reason, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, session_id, rating, reason, _now_iso()),
        )
        conn.commit()
```

---

## 2. api/app.py

### 2a. Добавить Pydantic модель (рядом с другими моделями запросов)

```python
class FeedbackRequest(BaseModel):
    trace_id: str
    session_id: str
    rating: str          # "up" or "down"
    reason: Optional[str] = ""
```

### 2b. Добавить route (после `/api/ask` или `/api/ask/stream`)

```python
@router.post("/feedback", status_code=204)
async def post_feedback(body: FeedbackRequest) -> None:
    """Сохранить фидбек пользователя на ответ."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating must be 'up' or 'down'")
    try:
        from sqlite_trace import save_feedback  # noqa: PLC0415
        save_feedback(
            trace_id=body.trace_id,
            session_id=body.session_id,
            rating=body.rating,
            reason=body.reason or "",
        )
    except Exception as exc:
        logger.warning("Failed to save feedback: %s", exc)
```

Проверь, что `HTTPException` уже импортирован — если нет, добавь в блок импортов.

---

## 3. static/chat.html

### 3a. В CSS добавить стили для feedback-блока (в конец блока `<style>`)

```css
.msg-feedback {
    display: flex;
    gap: 6px;
    margin-top: 6px;
    justify-content: flex-end;
}
.btn-feedback {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 14px;
    cursor: pointer;
    color: var(--text-secondary);
    transition: background 0.15s, color 0.15s;
}
.btn-feedback:hover { background: var(--bg-secondary); }
.btn-feedback.voted { opacity: 0.5; pointer-events: none; }
```

### 3b. В функцию добавления bot-сообщения

Найти место, где создаётся и добавляется DOM-элемент bot message (содержит `bot-message`
или похожий класс). После добавления текста ответа и бейджей добавить feedback-блок:

```javascript
// Добавляем feedback кнопки если есть trace_id
if (data.trace_id || data.session_id) {
    const fbDiv = document.createElement('div');
    fbDiv.className = 'msg-feedback';
    fbDiv.innerHTML = `
        <button class="btn-feedback" data-rating="up" title="Ответ полезен">👍</button>
        <button class="btn-feedback" data-rating="down" title="Ответ не помог">👎</button>
    `;
    fbDiv.querySelectorAll('.btn-feedback').forEach(btn => {
        btn.addEventListener('click', async () => {
            const rating = btn.dataset.rating;
            fbDiv.querySelectorAll('.btn-feedback').forEach(b => b.classList.add('voted'));
            try {
                await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        trace_id: data.trace_id || '',
                        session_id: data.session_id || sessionId || '',
                        rating: rating,
                    }),
                });
            } catch (_) {}
        });
    });
    // botMsgDiv — это переменная с DOM-элементом bot-сообщения
    botMsgDiv.appendChild(fbDiv);
}
```

Замени `botMsgDiv` на реальное имя переменной DOM-элемента бот-сообщения в файле.
Если `data.trace_id` в ответе нет — добавить поле `trace_id` в `AskResponse` в app.py
(посмотри, что возвращает `/api/ask`: если там нет trace_id, добавь его в Pydantic-модель
и в `return AskResponse(...)` в маршруте `/api/ask`).

---

## CONSTRAINTS
- Изменить только `sqlite_trace.py`, `api/app.py`, `static/chat.html`
- После фидбека кнопки становятся `pointer-events: none` (нельзя голосовать дважды)
- Ошибки сохранения — только warning в лог, не 500 пользователю
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] Таблица `feedback` создаётся в SQLite при запуске
- [ ] `POST /api/feedback` возвращает 204 при корректных данных
- [ ] `POST /api/feedback` возвращает 422 при rating != "up"/"down"
- [ ] Под каждым ответом бота появляются кнопки 👍 и 👎
- [ ] После клика кнопки затухают (voted), повторный клик невозможен
- [ ] `pytest tests/ -v` — 19 passed
