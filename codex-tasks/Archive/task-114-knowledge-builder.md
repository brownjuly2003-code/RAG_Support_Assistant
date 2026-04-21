# Task 114 — Knowledge Builder: resolved tickets → draft KB articles

## Context
KM-1 из commercial-plan. Сейчас когда оператор резолвит `EscalatedTicket`
(task-106), знание уходит в пустоту: ответ остаётся только в этом
тикете, не добавляется в KB. В результате следующий пользователь с тем
же вопросом снова эскалируется.

Knowledge Builder = цикл обучения: когда ≥3 resolved tickets похожи
(semantic cluster), LLM драфтит KB-статью на основе их Q+A →
отправляет в admin review → publish.

## Goal
Полуавтоматический pipeline: детект кластеров → LLM draft → admin UI для
review/edit/publish → добавление в vector store как новый KB document.

## Files to change
- `scripts/kb_builder.py` — weekly job: кластеризация resolved tickets
  (аналогично task-109 gap detection, но на другом источнике)
- `db/models.py` — таблица `KbDraft` (id, tenant_id, topic, draft_content,
  source_ticket_ids JSON, status [pending/approved/rejected/published], created_at, reviewed_at)
- `alembic/versions/009_kb_drafts.py`
- `api/app.py` — endpoints:
  - `GET /api/admin/kb-drafts?status=pending` — list
  - `PATCH /api/admin/kb-drafts/{id}` — edit draft_content
  - `POST /api/admin/kb-drafts/{id}/publish` — добавить в ChromaDB + mark published
  - `POST /api/admin/kb-drafts/{id}/reject`
- `static/admin.html` — секция "KB Drafts" с editable textarea
- `tests/test_kb_builder.py`

## Implementation sketch

### Clustering + draft generation (scripts/kb_builder.py)
```python
async def build_drafts():
    tickets = await fetch_resolved_tickets(since=7_days_ago)
    embeddings = await embed_all([t.user_question for t in tickets])
    clusters = HDBSCAN(min_cluster_size=3).fit_predict(embeddings)

    for cid in set(clusters):
        if cid == -1: continue
        cluster = [tickets[i] for i, l in enumerate(clusters) if l == cid]
        draft = await generate_kb_draft(cluster)  # LLM call
        await create_kb_draft(
            tenant_id=cluster[0].tenant_id,
            topic=draft["topic"],
            draft_content=draft["content"],
            source_ticket_ids=[str(t.id) for t in cluster],
        )

KB_DRAFT_PROMPT = """Based on these resolved support tickets, write a KB article
that would answer the original questions. Use clear headings, short
paragraphs, and neutral tone. Do NOT include PII.

Tickets:
{tickets_json}

Output as JSON: {{"topic": "...", "content": "# Heading\\n\\nBody..."}}
"""
```

### Publish → ChromaDB (api/app.py)
```python
@app.post("/api/admin/kb-drafts/{draft_id}/publish")
async def publish_draft(draft_id: UUID, user=Depends(require_role(["admin"]))):
    draft = await get_kb_draft(draft_id)
    # Chunk + embed + add to tenant ChromaDB collection
    doc = Document(
        page_content=draft.draft_content,
        metadata={
            "source": f"kb-builder/{draft.id}",
            "tenant_id": draft.tenant_id,
            "auto_generated": True,
            "generated_from_tickets": draft.source_ticket_ids,
        },
    )
    await ingest_document(doc, tenant_id=draft.tenant_id)
    draft.status = "published"
    await session.commit()
```

### Admin UI (static/admin.html)
Section "KB Drafts":
```
[Draft #01 — Возврат товара без чека] [pending]
Source tickets: 4
Topic: "Возврат товара без чека"
Draft content:
[editable textarea с markdown preview]
[Publish] [Edit] [Reject]
```

## CONSTRAINTS
- Tenant isolation — drafts per tenant, admin видит только свой
- Auto-generated flag в metadata — для аудита откуда пришёл документ
- LLM может галлюцинировать в draft — **обязательный** human review
  перед publish. Никакого auto-publish.
- Resolved tickets содержат PII (операторский ответ, email, order ids) —
  prompt должен запрашивать "do NOT include PII". Post-generation
  — прогнать через PII-redactor (`utils/pii.py`)
- Статус reject / published — immutable (нельзя republish; нужен новый draft)

## DONE WHEN
- [ ] Миграция 009 прошла
- [ ] `python scripts/kb_builder.py` на тестовых данных создаёт drafts
- [ ] Admin UI видит pending drafts, может edit + publish
- [ ] После publish — новый документ появляется в ChromaDB, retriever
      его находит на релевантном вопросе
- [ ] PII redaction применяется к generated content
- [ ] Weekly CronJob в Helm
- [ ] 260+ passed
- [ ] Commit: "Knowledge Builder: cluster resolved tickets into KB drafts (task-114)"
