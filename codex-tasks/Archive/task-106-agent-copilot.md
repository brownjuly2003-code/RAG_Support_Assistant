# Task 106 — Agent Copilot: dashboard + context panel

## Context
COPILOT-1 и COPILOT-2 из commercial-plan. Когда бот эскалирует тикет
(quality<threshold, user clicked "talk to human"), тикет уходит в
`SupportSink` (mock_inbox или Bitrix24). Оператор-человек сейчас видит
этот тикет где-то вне системы — нет UI для операторов.

Agent Copilot = отдельный UI `/agent` для операторов с:
1. Очередь эскалированных тикетов
2. AI-generated summary + suggested response draft
3. Context panel: full chat history + retrieved docs + quality scores +
   similar resolved tickets

Это НЕ замена Intercom/Zendesk, а lightweight in-house operator tool.

## Goal
Минимально жизнеспособный copilot: страница `/agent` с тремя колонками:
ticket list | conversation context | AI draft. RBAC-защита (role=agent или admin).

## Files to change
- `db/models.py` — новая таблица `EscalatedTicket` (id, session_id,
  tenant_id, user_question, ai_draft, operator_response, status,
  created_at, resolved_at)
- `alembic/versions/004_escalated_tickets.py` — миграция
- `mock_inbox.py` / `channels/escalation_sink.py` — когда прилетает
  escalation event, INSERT в `escalated_tickets` + сгенерировать draft
  через тот же LLM (short prompt: "Пользователь спросил X. Документы
  говорят Y. Напиши черновик ответа оператору.")
- `api/app.py` — endpoints:
  - `GET /api/agent/tickets` — list (filter by status)
  - `GET /api/agent/tickets/{id}` — detail (session history + retrieved + similar)
  - `POST /api/agent/tickets/{id}/respond` — оператор отвечает, status=resolved
  - `GET /api/agent/similar?ticket_id=X` — вернуть 3 similar resolved
    (semantic search по resolved.user_question через существующий vector_store)
  - Все защищены `require_role(["agent", "admin"])`
- `static/agent.html` — SPA-like 3-column layout
- `static/styles/agent.css` — новый стиль
- `tests/test_agent_endpoints.py` — CRUD тесты

## Implementation sketch

### DB schema (db/models.py)
```python
class EscalatedTicket(Base):
    __tablename__ = "escalated_tickets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    user_question: Mapped[str] = mapped_column(Text)
    ai_draft: Mapped[str | None] = mapped_column(Text)
    operator_response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # open|in_progress|resolved
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
```

### Similar tickets (semantic search)
Embedding от user_question → top-3 ближайших resolved tickets через
ChromaDB (новая коллекция `resolved_tickets_{tenant_id}` или переиспользовать
основной vector_store с metadata filter `type=ticket`).

### Frontend agent.html
```
┌─────────────┬────────────────────┬──────────────┐
│ Tickets     │ Context            │ AI Draft     │
│ [Open (3)]  │ User: ...          │ [editable    │
│ [In prog..] │ Bot: ... [1][2]    │  textarea]   │
│             │ User clicked human │              │
│ #01 ...     │                    │ [Send reply] │
│ #02 ...     │ Retrieved (3):     │              │
│ #03 ...     │ — doc1 q=0.72      │ Similar:     │
│             │ — doc2 q=0.68      │ — ticket#42  │
│             │                    │ — ticket#19  │
└─────────────┴────────────────────┴──────────────┘
```

## CONSTRAINTS
- Tenant isolation: оператор видит только тикеты СВОЕГО tenant_id (из JWT)
- AI draft generation — async, fire-and-forget: если модель недоступна,
  ticket создаётся без draft, показать placeholder
- Не ломать существующий escalation flow (mock_inbox должен продолжать
  работать для тестов)
- Операторский ответ — НЕ отправляется пользователю автоматически
  (external channel — out of scope этой таски). Отправка = просто сохранить
  в `operator_response` и пометить resolved

## DONE WHEN
- [ ] Миграция 004 прошла, таблица есть
- [ ] При escalation создаётся ticket, AI draft populated
- [ ] `/agent` доступен только role=agent/admin, 403 для viewer
- [ ] Тикет-лист показывает only own-tenant
- [ ] Similar tickets: 3 ближайших по embedding
- [ ] 230+ passed (5-7 новых тестов)
- [ ] Screenshots `/agent` с реальным эскалированным тикетом
- [ ] Commit: "Agent copilot dashboard with ticket context + AI draft (task-106)"
