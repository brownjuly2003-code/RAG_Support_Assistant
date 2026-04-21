# Task 115 — Knowledge freshness monitoring + stale doc alerts

## Context
KM-2 из commercial-plan. KB-документы устаревают: цены меняются, политики
обновляются, процедуры депрекейтятся. Сейчас нет механизма отслеживания
"свежести". Документ 2020 года может цитироваться ботом в 2026, давая
устаревшие ответы.

## Goal
Панель в admin UI "Stale Documents" с списком документов которые:
- Не обновлялись >90 дней
- Часто цитируются (top 20 по citation count за 30 дней)
- Таким образом: "старые И важные" — первоочередные кандидаты на ревизию

## Files to change
- `db/models.py` — расширить existing `documents` / ChromaDB metadata
  (уже есть `created_at`, нужно добавить `last_updated`, `citation_count`,
  `last_cited_at`)
- Если documents живут только в ChromaDB metadata — добавить postgres
  таблицу `document_stats` (doc_id, tenant_id, citation_count, last_cited_at)
- `alembic/versions/010_document_stats.py`
- `graph.py` — после успешного answer с citations (task-102), инкрементить
  counter для каждого cited doc_id
- `api/app.py` — `GET /api/admin/stale-docs?days=90&top_cited=20` endpoint
- `static/admin.html` — секция "Stale Docs"
- `tests/test_freshness.py`

## Implementation sketch

### Citation counter (graph.py)
```python
async def _record_citations(state):
    tenant_id = state["tenant_id"]
    for citation in state.get("citations", []):
        doc_id = citation["doc_id"]
        await session.execute(
            insert(DocumentStats).values(
                doc_id=doc_id, tenant_id=tenant_id,
                citation_count=1, last_cited_at=datetime.utcnow(),
            ).on_conflict_do_update(
                index_elements=["doc_id", "tenant_id"],
                set_={
                    "citation_count": DocumentStats.citation_count + 1,
                    "last_cited_at": datetime.utcnow(),
                },
            )
        )
    await session.commit()
```

### Stale detection (api/app.py)
```python
@app.get("/api/admin/stale-docs")
async def stale_docs(days: int = 90, top_cited: int = 20, user=...):
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(DocumentStats, ChromaDoc.metadata_column)
        .join(ChromaDoc, ChromaDoc.id == DocumentStats.doc_id)
        .where(
            DocumentStats.tenant_id == user.tenant_id,
            ChromaDoc.updated_at < cutoff,
        )
        .order_by(DocumentStats.citation_count.desc())
        .limit(top_cited)
    )
    return await session.scalars(stmt).all()
```

Примечание: ChromaDB не SQL, так что запрос выглядит иначе — нужно
fetch'нуть `doc_ids`, затем get metadata для каждого через ChromaDB
API. Details в implementation.

### Admin UI
```
Stale Documents (>90 days, top 20 cited)
─────────────────────────────────────────
Title                | Last updated | Citations | Actions
Политика возврата    | 2024-11-12   | 47        | [View] [Mark reviewed]
Условия доставки     | 2025-01-08   | 29        | [View] [Mark reviewed]
```

"Mark reviewed" — сбрасывает last_updated на текущий (не меняет контент,
просто фиксирует что админ проверил).

## CONSTRAINTS
- Writes на каждую citation — **async fire-and-forget** через Celery, не
  блокировать user-facing /api/ask
- UPSERT через `on_conflict_do_update` — работает только в Postgres (не
  SQLite). Уже нет SQLite prod, OK.
- Metadata rendering: для ChromaDB docs нужно fetch title/source из metadata
- Alert: если >5 docs одновременно stale+top-cited → Prometheus gauge
  `rag_stale_important_docs_count` (Alertmanager может slack'нуть)

## DONE WHEN
- [ ] Миграция 010 прошла
- [ ] Citations инкрементят counter на /api/ask
- [ ] `GET /api/admin/stale-docs` возвращает корректный список
- [ ] Admin UI показывает таблицу, "Mark reviewed" работает
- [ ] Prometheus gauge `rag_stale_important_docs_count` в /metrics
- [ ] 265+ passed
- [ ] Commit: "Knowledge freshness monitoring: stale + top-cited tracking (task-115)"
