# Task 38 — SEC-3: Input length validation через Pydantic

## Goal
`AskRequest.question` не ограничена по длине — можно отправить 10MB строку,
что перегрузит LLM и потенциально позволяет DoS.
Добавить `Field(min_length=1, max_length=2000)` на question и ограничения на другие модели.

## Files to change
- `api/app.py` — Pydantic-модели `AskRequest`, `FeedbackRequest`

---

## api/app.py

### AskRequest (строка ~211)

было:
```python
class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
```

стало:
```python
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
```

### FeedbackRequest (строка ~230)

было:
```python
class FeedbackRequest(BaseModel):
    trace_id: str
    session_id: str
    rating: str
    reason: Optional[str] = ""
```

стало:
```python
class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., max_length=100)
    session_id: str = Field(..., max_length=100)
    rating: str = Field(..., pattern=r"^(up|down)$")
    reason: Optional[str] = Field(default="", max_length=500)
```

`Field` уже импортирован (`from pydantic import BaseModel, Field` — строка 29).

---

## CONSTRAINTS
- Изменить только Pydantic-модели в `api/app.py`
- FastAPI автоматически вернёт 422 при нарушении constraints
- Не добавлять новые зависимости
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `AskRequest.question` имеет `max_length=2000`
- [ ] `FeedbackRequest.rating` ограничен `^(up|down)$`
- [ ] POST `/api/ask` с question длиной 3000 символов → 422
- [ ] POST `/api/feedback` с `rating: "invalid"` → 422
- [ ] `pytest tests/ -v` — проходит
