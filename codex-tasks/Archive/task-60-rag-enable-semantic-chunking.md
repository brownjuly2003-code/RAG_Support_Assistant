# Task 60 — FEAT-1: Включить semantic chunking по умолчанию

## Goal
Semantic chunking даёт +80% faithfulness (по benchmark из docs/research).
Сейчас выключен (`RAG_SEMANTIC_CHUNKING=false`). Включить по умолчанию.

## Files to change
- `config/settings.py` — default `true`
- `.env.example` — обновить комментарий

---

## 1. config/settings.py (строка ~100)

было:
```python
    semantic_chunking: bool = os.getenv("RAG_SEMANTIC_CHUNKING", "false").strip().lower() in ("1", "true", "yes")
```

стало:
```python
    semantic_chunking: bool = os.getenv("RAG_SEMANTIC_CHUNKING", "true").strip().lower() in ("1", "true", "yes")
```

---

## 2. .env.example

было:
```
RAG_SEMANTIC_CHUNKING=false
```

стало:
```
# Semantic chunking — splits by semantic similarity instead of fixed size.
# Improves faithfulness ~+80%. Requires embedding model loaded.
RAG_SEMANTIC_CHUNKING=true
```

---

## CONSTRAINTS
- Изменить только 2 файла
- Default меняется с false на true
- Env var переопределяет (можно выключить: `RAG_SEMANTIC_CHUNKING=false`)
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `get_settings().semantic_chunking` → True (без env var)
- [ ] `RAG_SEMANTIC_CHUNKING=false` → False (override работает)
- [ ] `.env.example` обновлён
- [ ] `pytest tests/ -v` — проходит
