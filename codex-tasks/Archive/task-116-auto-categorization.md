# Task 116 — Auto-categorization документов при upload

## Context
KM-3 из commercial-plan. Сейчас при upload документа он попадает в общий
KB без каких-либо категорий/тегов. Admin UI не может фильтровать по
topic ("показать все документы про доставку"), retrieval не может делать
category-scoped search ("для этого вопроса ищи только в Returns policy").

## Goal
При upload → LLM классифицирует документ в одну или несколько **предустановленных**
категорий (конфиг per tenant). Категория пишется в metadata, используется
retriever для filtering.

## Files to change
- `config/settings.py` — путь к категориям:
  `CATEGORIES_CONFIG_PATH: str = "config/categories.yml"`
- `config/categories.yml` (новый) — default taxonomy:
  ```yaml
  default:
    - name: returns
      description: "Returns, refunds, cancellations"
    - name: shipping
      description: "Delivery, shipping, pickup"
    - name: account
      description: "Account management, login, password"
    - name: payment
      description: "Payments, billing, invoices"
    - name: product
      description: "Product info, specs, availability"
  ```
  (tenant-override в БД `tenant_settings` table — опционально)
- `ingestion/categorizer.py` — новый модуль с LLM-based classification
- `ingestion/pipeline.py` — после chunking, перед embedding, вызывать
  `classify_document(full_text, categories)` → записать в metadata
- `api/app.py` — `GET /api/admin/categories` (list), extend
  `/api/upload` response с assigned categories
- `vectordb/manager.py` — добавить `category_filter` parameter в retrieve
  (opcional)
- `tests/test_categorizer.py`

## Implementation sketch

### ingestion/categorizer.py
```python
CLASSIFY_PROMPT = """Classify the document below into one or more of these
categories. Return ONLY a JSON list of category names (лейаут strings).
If none apply, return ["uncategorized"].

Categories:
{categories}

Document:
{doc_preview}

Classification (JSON list):"""

async def classify_document(
    full_text: str,
    categories: list[dict],
    llm,
) -> list[str]:
    cats_str = "\n".join(f"- {c['name']}: {c['description']}" for c in categories)
    preview = full_text[:3000]
    response = await llm.ainvoke(CLASSIFY_PROMPT.format(
        categories=cats_str, doc_preview=preview,
    ))
    try:
        result = json.loads(response.content)
        valid = {c["name"] for c in categories}
        return [r for r in result if r in valid] or ["uncategorized"]
    except json.JSONDecodeError:
        logger.warning("Categorizer returned invalid JSON: %s", response.content)
        return ["uncategorized"]
```

### Integration (ingestion/pipeline.py)
```python
categories = load_categories(tenant_id)
assigned = await classify_document(full_text, categories, llm_fast)

for chunk in chunks:
    chunk.metadata["categories"] = assigned  # List[str]
    chunk.metadata["primary_category"] = assigned[0]
```

### Filtering in retrieval (manager.py)
```python
def retrieve(query, tenant_id, categories=None, k=5):
    where = {"tenant_id": tenant_id}
    if categories:
        where["categories"] = {"$in": categories}  # ChromaDB syntax
    return collection.query(query_texts=[query], n_results=k, where=where)
```

## CONSTRAINTS
- Classification — дополнительный LLM call per upload. Использовать
  **fast** model (`llm_fast`) — qwen2.5:3b или similar, не llm_strong
- Категории — per-tenant configurable, но default list fallback
- Если LLM fails → категория "uncategorized", не блокируем upload
- Filtering в retrieval — **opt-in** (когда bot может определить topic
  запроса). В фазе 1 категории просто пишем, filtering не включаем
- Reindex existing docs — опциональный script, как в task-110

## DONE WHEN
- [ ] `config/categories.yml` default taxonomy есть
- [ ] Upload → response содержит assigned categories
- [ ] Metadata в ChromaDB содержит `categories` list
- [ ] Test: document про доставку → category ≈ `["shipping"]`
- [ ] Fallback: invalid JSON → `["uncategorized"]`
- [ ] 268+ passed
- [ ] Commit: "Auto-categorize documents on upload via LLM (task-116)"
