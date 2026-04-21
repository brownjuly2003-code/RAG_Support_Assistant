# Task 102 — Inline citations `[N]` + source panel

## Context
Сейчас `/api/ask` возвращает `documents: List[Doc]` рядом с текстом
ответа, но сам текст — "сплошной" без ссылок на источники. Коммерческий
стандарт (Intercom Fin, Perplexity, Fini) — inline маркеры `[1]`, `[2]`
прямо в тексте, hover показывает title+excerpt, click открывает side panel.

Без citations пользователь не может верифицировать ответ — это главный
блокер trust'а для business-use.

## Goal
1. **Backend**: generate node должен вставлять `[N]` в ответ, где `N` —
   индекс документа из `retrieved_docs` (1-based). Prompt-инструкция:
   "When citing facts, append `[N]` where N is the 1-based index of the
   source document in the list."
2. **API**: добавить `citations: List[{index: int, doc_id: str, title: str,
   excerpt: str}]` в `AskResponse`. Excerpt = первые 300 символов чанка.
3. **Frontend** (`static/chat.html`): при рендере bot message парсить
   `\[(\d+)\]` → превратить в `<button class="citation">[N]</button>` с
   `data-citation-index`. Hover → tooltip (title + excerpt). Click →
   открыть `<aside class="source-panel">` справа с полным документом.

## Files to change
- `agent/prompts.py` — добавить citation-инструкцию в system prompt для generate node
- `graph.py` (или `agent/graph.py`) — generate node собирает `citations[]` из `state.retrieved_docs`
- `api/app.py` — `AskResponse` Pydantic model расширить
- `static/chat.html` — парсер `\[\d+\]` + citation-кнопки + source-panel
- `static/styles/components.css` — стили `.citation`, `.source-panel`, `.citation-tooltip`
- `tests/test_graph.py` или новый `test_citations.py` — unit-test что
  ответ на запрос с 3 retrieved_docs содержит `[1]`, `[2]`, `[3]` и
  соответствующие citation entries

## Implementation sketch

### Prompt addition (prompts.py)
```
When citing specific facts from the documents, append [N] immediately after
the fact, where N is the 1-based position of the source document in the
provided list. Do NOT invent citation numbers. If a statement isn't
supported by a document, don't cite.
```

### Response model (api/app.py)
```python
class Citation(BaseModel):
    index: int
    doc_id: str
    title: str
    excerpt: str

class AskResponse(BaseModel):
    # existing fields...
    citations: list[Citation] = []
```

### Frontend parse (chat.html)
```javascript
function renderBotMessage(text, citations) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map(p => {
    const m = p.match(/^\[(\d+)\]$/);
    if (!m) return escapeHtml(p);
    const idx = parseInt(m[1]);
    const cit = citations.find(c => c.index === idx);
    if (!cit) return escapeHtml(p);
    return `<button class="citation" data-idx="${idx}" title="${escapeAttr(cit.title)}">[${idx}]</button>`;
  }).join('');
}
```

### Source panel (chat.html)
При клике — dispatch `showSource(citationIndex)`. Panel имеет
`aria-label="Источник цитаты"`, `role="complementary"`, close-button с
`aria-label="Закрыть"`.

## CONSTRAINTS
- Не ломать suggested-questions, escalate, feedback flow
- Source panel mobile: full-screen overlay, не сбоку
- Если LLM сгенерировал `[N]` для несуществующего doc — рендерить как
  plain text (no button), чтобы не показывать мёртвую ссылку
- Добавить regex-extract citations BEFORE отправки в quality-evaluator (
  чтобы evaluator работал на чистом тексте без `[N]`)

## DONE WHEN
- [ ] 3+ citation unit-тестов (generation, parsing, orphan-citation handling)
- [ ] Manual test: задать вопрос → ответ содержит [N] → hover показывает title → click открывает panel
- [ ] 225+ passed, ruff clean
- [ ] Screenshot в PR с работающими citations
- [ ] Commit: "Inline citations in bot answers with source panel (task-102)"
