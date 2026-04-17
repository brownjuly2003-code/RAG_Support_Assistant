# Task 54 — UX-2: Suggested follow-up questions

## Goal
После каждого ответа показывать 2-3 кнопки с follow-up вопросами.
Вопросы генерирует LLM на основе контекста и ответа.

## Files to change
- `agent/prompts.py` — новый промпт `build_suggested_questions_prompt`
- `agent/graph.py` — генерация suggested questions после generate
- `agent/state.py` — новое поле `suggested_questions`
- `api/app.py` — вернуть suggested_questions в AskResponse
- `static/chat.html` — рендеринг кнопок

---

## 1. agent/state.py

Добавить в GraphState:
```python
    suggested_questions: List[str]  # follow-up вопросы
```

В `create_initial_state` добавить:
```python
    "suggested_questions": [],
```

---

## 2. agent/prompts.py

Добавить функцию:
```python
def build_suggested_questions_prompt(question: str, answer: str, context_snippet: str = "") -> str:
    """Промпт для генерации follow-up вопросов."""
    return f"""На основе вопроса пользователя и ответа предложи 3 коротких follow-up вопроса.
Вопросы должны быть:
- Связаны с темой
- Короткие (до 60 символов)
- Помогают углубить понимание

Вопрос: {question}
Ответ: {answer[:500]}

Верни ТОЛЬКО 3 вопроса, каждый на новой строке. Без нумерации, без тире."""
```

---

## 3. agent/graph.py — новый node

Добавить функцию `make_suggest_questions_node()`:

```python
def make_suggest_questions_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Генерирует 2-3 follow-up вопроса после ответа."""

    def node(state: GraphState) -> GraphState:
        if state.get("route") != "auto":
            return state  # не генерировать для escalated/error

        try:
            prompt = build_suggested_questions_prompt(
                state.get("question", ""),
                state.get("answer", ""),
            )
            raw = llm.invoke(prompt)
            questions = [q.strip() for q in raw.strip().split("\n") if q.strip()][:3]
            return {**state, "suggested_questions": questions}  # type: ignore[misc]
        except Exception as exc:
            logger.warning("Failed to generate suggested questions: %s", exc)
            return state

    return node
```

Добавить node в граф после `evaluate` (или после `route_or_retry` для auto-route):

```python
graph.add_node("suggest_questions", make_suggest_questions_node(llm))
```

---

## 4. api/app.py — AskResponse

Добавить поле:
```python
class AskResponse(BaseModel):
    answer: str
    quality_score: int = 50
    route: str = "auto"
    sources: List[SourceInfo] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    suggested_questions: List[str] = Field(default_factory=list)
```

В обработчике `/api/ask`, при формировании ответа добавить:
```python
    suggested_questions=result.get("suggested_questions", []),
```

---

## 5. static/chat.html — рендеринг

В `addMessage()`, после sources block:

```javascript
// Suggested questions
if (meta && meta.suggested_questions && meta.suggested_questions.length > 0) {
    const sqDiv = document.createElement('div');
    sqDiv.className = 'suggested-questions';
    meta.suggested_questions.forEach(function(q) {
        const btn = document.createElement('button');
        btn.className = 'btn-suggested';
        btn.textContent = q;
        btn.addEventListener('click', function() {
            questionInput.value = q;
            sendMessage();
        });
        sqDiv.appendChild(btn);
    });
    content.appendChild(sqDiv);
}
```

CSS:
```css
.suggested-questions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
}
.btn-suggested {
    padding: 6px 14px;
    border: 1px solid var(--border, #e0e0e0);
    border-radius: 16px;
    background: transparent;
    color: var(--accent, #4a90d9);
    font-size: 13px;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
}
.btn-suggested:hover {
    background: var(--bg-secondary, #f0f2f5);
    border-color: var(--accent, #4a90d9);
}
```

---

## CONSTRAINTS
- Suggested questions — optional: если LLM не сгенерирует, пустой список
- Не замедлять основной ответ: генерация вопросов может быть после основного ответа
- Клик по suggested question → отправка как обычный вопрос
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `suggested_questions` в GraphState и AskResponse
- [ ] LLM генерирует 2-3 follow-up вопроса
- [ ] Кнопки рендерятся под ответом в чате
- [ ] Клик → вопрос отправляется
- [ ] При ошибке генерации — пустой список, ответ не ломается
- [ ] `pytest tests/ -v` — проходит
