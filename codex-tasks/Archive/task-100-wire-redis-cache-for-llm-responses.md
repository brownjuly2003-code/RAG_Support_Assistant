# Task 100 — Wire `cache/redis_cache.py` into LLM response caching

## Context
`cache/redis_cache.py` — готовый модуль с `cache_json_get/set`, fallback
на in-memory dict, graceful degradation. Добавлен в task-45, но **никто
не импортирует**. Dead code.

Решение — не удалять, а **подключить** к LLM response caching:
повторяющиеся вопросы в support-боте нормальны ("как сбросить пароль",
"где скачать X") — отвечаем из кеша моментально, экономим Ollama CPU.

## Architecture
- **Что кешируем:** финальный ответ `run_qa_pipeline` для пары
  `(tenant_id, question_text_normalized)`
- **TTL:** 1 час по умолчанию (env `LLM_CACHE_TTL_SECONDS=3600`)
- **Нормализация:** `.strip().lower()` — хватит; не делаем semantic dedup
- **Ключ:** `llm_resp:{tenant}:{sha256(normalized_q)[:16]}` — sha16 чтобы
  не светить вопрос в Redis, плюс короткий префикс
- **Invalidation:** по upload'у документа в tenant — сбрасываем весь
  namespace `llm_resp:{tenant}:*` (ответы могут устареть под новые доки)
- **Tenant isolation:** кеш уже per-tenant по ключу; если tenant пустой —
  `"default"`
- **Feature flag:** `LLM_CACHE_ENABLED=false` по умолчанию (безопасный
  rollout); включается в env

## Files to change
- `api/app.py` — `ask` handler: cache lookup перед pipeline, cache set после
- `api/app.py` — `upload_document`: invalidate tenant namespace после
  успешного ingest'а
- `config/settings.py` — добавить `llm_cache_enabled` и `llm_cache_ttl_seconds`
- `cache/redis_cache.py` — добавить `cache_delete_pattern(pattern: str)`
  (Redis SCAN + DELETE; для fallback — обход `_fallback` dict)
- `.env.example`, `README.md` — документация
- `monitoring/` — 2 Prometheus counter'а: `llm_cache_hits_total{tenant}`,
  `llm_cache_misses_total{tenant}`

## Files to create
- `tests/test_llm_response_cache.py` — 6 тестов

## Implementation

### `config/settings.py`

```python
llm_cache_enabled: bool = field(
    default_factory=lambda: os.getenv("LLM_CACHE_ENABLED", "false").lower() == "true"
)
llm_cache_ttl_seconds: int = field(
    default_factory=lambda: int(os.getenv("LLM_CACHE_TTL_SECONDS", "3600"))
)
```

### `cache/redis_cache.py` — новая функция

```python
def cache_delete_pattern(pattern: str) -> int:
    """Удалить все ключи по glob-паттерну. Возвращает count удалённых."""
    r = _get_redis()
    deleted = 0
    if r is not None:
        try:
            for key in r.scan_iter(match=pattern, count=500):
                r.delete(key)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.warning("Redis SCAN/DEL failed: %s", exc)
    # Fallback: in-memory dict
    import fnmatch
    to_delete = [k for k in _fallback if fnmatch.fnmatch(k, pattern)]
    for k in to_delete:
        _fallback.pop(k, None)
        deleted += 1
    return deleted
```

### `api/app.py::ask` handler

```python
import hashlib

def _cache_key(tenant: str, question: str) -> str:
    norm = question.strip().lower()
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return f"llm_resp:{tenant or 'default'}:{h}"

@router.post("/ask")
async def ask(...):
    settings = get_settings()
    tenant = get_current_tenant() or "default"

    if settings.llm_cache_enabled:
        from cache.redis_cache import cache_json_get
        key = _cache_key(tenant, payload.question)
        cached = cache_json_get(key)
        if cached is not None:
            LLM_CACHE_HITS.labels(tenant=tenant).inc()
            return JSONResponse(content={**cached, "cached": True})
        LLM_CACHE_MISSES.labels(tenant=tenant).inc()

    # ... existing pipeline ...
    result = await run_qa_pipeline(...)

    if settings.llm_cache_enabled and result.get("answer"):
        from cache.redis_cache import cache_json_set
        cache_json_set(
            key,
            {"answer": result["answer"], "sources": result.get("sources", [])},
            ttl_seconds=settings.llm_cache_ttl_seconds,
        )

    return JSONResponse(content=result)
```

**Важно:** кешируем только если `result.get("answer")` непустой (не
кешируем ошибки, escalation'ы, low-confidence).

### `api/app.py::upload_document`

```python
# После успешного ingest'а
if settings.llm_cache_enabled:
    from cache.redis_cache import cache_delete_pattern
    deleted = cache_delete_pattern(f"llm_resp:{tenant}:*")
    logger.info("Invalidated %d cached LLM responses for tenant %s", deleted, tenant)
```

### Prometheus

```python
LLM_CACHE_HITS = Counter(
    "llm_cache_hits_total", "LLM response cache hits", ["tenant"]
)
LLM_CACHE_MISSES = Counter(
    "llm_cache_misses_total", "LLM response cache misses", ["tenant"]
)
```

## Tests — `tests/test_llm_response_cache.py`

```python
def test_cache_key_is_normalized():
    from api.app import _cache_key
    k1 = _cache_key("acme", "How to reset password?")
    k2 = _cache_key("acme", "  HOW TO RESET PASSWORD?  ")
    assert k1 == k2

def test_cache_key_isolates_tenants():
    from api.app import _cache_key
    assert _cache_key("acme", "x") != _cache_key("mega", "x")

def test_cached_response_returns_without_pipeline(monkeypatch, client):
    # Enable cache via env + monkeypatch pipeline to raise if called
    ...

def test_cache_miss_invokes_pipeline_and_stores(monkeypatch, client):
    ...

def test_cache_invalidated_on_upload(monkeypatch, client):
    ...

def test_cache_disabled_flag_skips_entirely(monkeypatch, client):
    """LLM_CACHE_ENABLED=false → no cache_get/set calls."""
    ...
```

(Полные реализации — пиши самостоятельно по образцу
`tests/test_tenant_enforcement.py`.)

## CONSTRAINTS
- `LLM_CACHE_ENABLED=false` по умолчанию — safe rollout
- Никаких новых deps (redis уже есть)
- Cache miss не должен падать если Redis недоступен — graceful degradation
  через existing fallback
- Не кешировать пустые ответы, ошибки, escalation'ы
- Invalidation после upload обязательна — иначе stale ответы после
  обновления docs
- pytest tests/ -v → **220+ passed** (214 + 6), 0 regressions
- ruff 0 errors

## DONE WHEN
- [ ] `_cache_key` с нормализацией и tenant-scoping
- [ ] `ask` handler: hit → return cached с `"cached": true`, miss → store после pipeline
- [ ] `upload_document`: invalidate per-tenant namespace
- [ ] `cache_delete_pattern` в `redis_cache.py` (Redis + fallback)
- [ ] Feature flag `LLM_CACHE_ENABLED`, TTL из env
- [ ] Prometheus counters `llm_cache_hits_total` / `llm_cache_misses_total`
- [ ] 6 тестов в `test_llm_response_cache.py`
- [ ] README: раздел "LLM response caching" с env vars
- [ ] pytest 220+ passed, ruff clean
- [ ] Commit: "Wire redis cache to LLM responses: tenant-scoped, feature-flagged (task-100)"
