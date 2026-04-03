# Task 17 — HyDE (Hypothetical Document Embeddings)

## Goal
Улучшить точность retrieval: вместо эмбеддинга короткого вопроса генерировать
гипотетический ответ и искать по его эмбеддингу. Хорошо работает для support-вопросов
вида «Почему ошибка E20?», где вопрос короткий, а документы длинные.

## Background
Текущий `transform_query` в `graph.py` переформулирует вопрос в поисковый запрос (строку).
Retrieval затем ищет по этой строке через HybridRetriever (BM25 + ChromaDB).

HyDE-идея: вместо строки-запроса — LLM генерирует гипотетический ответ (~2-3 предложения),
ChromaDB ищет по эмбеддингу этого ответа. Вопрос «Почему ошибка E20?» →
hypothetical: «Ошибка E20 возникает при превышении температуры...» → ищем похожие документы.

Включается через `RAG_HYDE=true` — при `false` поведение прежнее.

## Files to change
- `config/settings.py` — добавить `hyde: bool`
- `state.py` — добавить поле `hyde_query: Optional[str]`
- `graph.py` — добавить HyDE-генерацию в `make_transform_query_node`

---

## 1. config/settings.py

Добавить поле рядом с другими RAG-параметрами:

```python
# --- HyDE (Hypothetical Document Embeddings) ---
hyde: bool = os.getenv("RAG_HYDE", "false").strip().lower() in ("1", "true", "yes")
```

---

## 2. state.py

В класс `GraphState` добавить поле:
```python
hyde_query: Optional[str]
```

В `create_initial_state()` добавить в объект GraphState:
```python
hyde_query=None,
```

---

## 3. graph.py

### 3a. Добавить промпт-билдер (рядом с другими build_*_prompt функциями или inline)

```python
def _build_hyde_prompt(question: str) -> str:
    return (
        "You are a helpful assistant. Write a short hypothetical answer (2-3 sentences) "
        "to the following support question. Write only the answer, no intro or meta-text.\n\n"
        f"Question: {question}\n\nHypothetical answer:"
    )
```

### 3b. Изменить `make_transform_query_node` — добавить HyDE после получения `search_query`

Найди строки (существующий конец node-функции):
```python
new_state: GraphState = {**state, "search_query": search_query}
log_step(trace_id, "transform_query", new_state)
return new_state
```

Заменить на:
```python
from config.settings import get_settings  # noqa: PLC0415
settings = get_settings()
hyde_query: Optional[str] = None
if settings.hyde:
    try:
        hyde_doc = llm.invoke(_build_hyde_prompt(question)).strip()
        if hyde_doc and len(hyde_doc) > 10:
            hyde_query = hyde_doc
            logger.debug("[transform_query] HyDE generated (%d chars)", len(hyde_doc))
    except Exception as exc:
        logger.warning("[transform_query] HyDE failed, fallback to search_query: %s", exc)

new_state: GraphState = {**state, "search_query": search_query, "hyde_query": hyde_query}
log_step(trace_id, "transform_query", new_state)
return new_state
```

### 3c. Изменить `make_retrieve_node` — использовать `hyde_query` если есть

Найди строку в `make_retrieve_node`, где берётся query для retrieval:
```python
query = state.get("search_query") or state.get("question", "")
```
(или похожую — найди сам)

Заменить на:
```python
query = state.get("hyde_query") or state.get("search_query") or state.get("question", "")
```

---

## CONSTRAINTS
- Изменить только `config/settings.py`, `state.py`, `graph.py`
- При `RAG_HYDE=false` (default) — поведение идентично текущему
- При `RAG_HYDE=true` и ошибке LLM — fallback на `search_query` (не падать)
- `Optional` уже импортирован в `state.py`; в `graph.py` — проверить и добавить если нет
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `get_settings().hyde` по умолчанию `False`
- [ ] `GraphState` содержит поле `hyde_query: Optional[str]`
- [ ] При `RAG_HYDE=true` в логах появляется `[transform_query] HyDE generated`
- [ ] При ошибке HyDE — система продолжает работу с `search_query`
- [ ] Тест: `RAG_HYDE=false` — `state["hyde_query"]` is None после transform_query
- [ ] `pytest tests/ -v` — 19 passed
