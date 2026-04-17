# Task 55 — UX-3: Кнопка "Связаться с оператором"

## Goal
Постоянно видимая кнопка для ручной эскалации.
При клике: confirmation → собирает контекст → отправляет в escalation sink.

## Files to change
- `static/chat.html` — кнопка + UI flow
- `api/app.py` — новый endpoint `POST /api/escalate`

---

## 1. api/app.py

Новая модель и endpoint:

```python
class EscalateRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    question: str = Field(default="", max_length=2000)
    reason: str = Field(default="user_request", max_length=200)


@router.post("/escalate")
async def escalate_to_human(body: EscalateRequest) -> dict:
    """Ручная эскалация: пользователь хочет оператора."""
    import json as _j
    from datetime import datetime, timezone

    record = {
        "entity_id": body.session_id,
        "question": body.question,
        "route": "human_request",
        "reason": body.reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        inbox_path = PROJECT_ROOT / "data" / "inbox" / "support_inbox.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8") as f:
            f.write(_j.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write escalation: %s", exc)
        raise HTTPException(status_code=500, detail="Escalation failed")

    return {
        "status": "ok",
        "message": "Ваш запрос передан оператору. Мы ответим в ближайшее время.",
    }
```

---

## 2. static/chat.html

### Кнопка в header (рядом с help/metrics):

```html
<button class="btn-icon btn-escalate" id="escalateBtn" title="Связаться с оператором" aria-label="Связаться с оператором">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
    </svg>
</button>
```

### CSS:

```css
.btn-escalate {
    color: var(--warning, #ffc107);
}

.escalate-modal {
    position: fixed;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.5);
    z-index: 200;
}
.escalate-modal.active { display: flex; }
.escalate-dialog {
    background: var(--bg-primary, #fff);
    border-radius: 12px;
    padding: 24px;
    max-width: 400px;
    width: 90%;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.escalate-dialog h3 { margin-bottom: 12px; }
.escalate-dialog p { margin-bottom: 16px; color: var(--text-secondary, #555); font-size: 14px; }
.escalate-actions { display: flex; gap: 8px; justify-content: flex-end; }
.escalate-actions button { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; }
.btn-confirm-escalate { background: var(--accent, #4a90d9); color: #fff; }
.btn-cancel-escalate { background: var(--bg-secondary, #f0f2f5); }

.escalate-success {
    text-align: center;
    padding: 16px;
    background: var(--bg-secondary, #f0f2f5);
    border-radius: 8px;
    margin: 8px 0;
}
```

### Modal HTML (перед </body>):

```html
<div class="escalate-modal" id="escalateModal">
    <div class="escalate-dialog" role="dialog" aria-label="Подтверждение эскалации">
        <h3>Связаться с оператором</h3>
        <p>Ваш текущий диалог будет передан оператору поддержки. Мы ответим в ближайшее время.</p>
        <div class="escalate-actions">
            <button class="btn-cancel-escalate" id="escalateCancel">Отмена</button>
            <button class="btn-confirm-escalate" id="escalateConfirm">Подтвердить</button>
        </div>
    </div>
</div>
```

### JS:

```javascript
// Escalation
const escalateBtn = document.getElementById('escalateBtn');
const escalateModal = document.getElementById('escalateModal');
const escalateConfirm = document.getElementById('escalateConfirm');
const escalateCancel = document.getElementById('escalateCancel');

escalateBtn.addEventListener('click', () => {
    escalateModal.classList.add('active');
});

escalateCancel.addEventListener('click', () => {
    escalateModal.classList.remove('active');
});

escalateConfirm.addEventListener('click', async () => {
    escalateModal.classList.remove('active');
    try {
        const resp = await fetch(API_BASE + '/escalate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId || '',
                question: questionInput.value || '(пользователь запросил оператора)',
                reason: 'user_request',
            }),
        });
        const data = await resp.json();
        addMessage('assistant', data.message || 'Запрос передан оператору.', {});
    } catch (err) {
        addMessage('assistant', 'Не удалось связаться с поддержкой. Попробуйте позже.', {});
        console.warn('Escalation error:', err);
    }
});

// Close modal on overlay click
escalateModal.addEventListener('click', (e) => {
    if (e.target === escalateModal) escalateModal.classList.remove('active');
});
```

---

## CONSTRAINTS
- Кнопка видна всегда (header)
- Confirmation dialog перед эскалацией
- Запись в support_inbox.jsonl
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] Кнопка "оператор" в header
- [ ] Клик → confirmation modal
- [ ] Подтверждение → POST /api/escalate → запись в inbox
- [ ] Сообщение в чат "Запрос передан оператору"
- [ ] Отмена → modal закрывается
- [ ] `pytest tests/ -v` — проходит
