# Batch D — Product Differentiation (orchestrator)

Шесть тасков закрывающих Phase 5 из commercial-plan. Самый большой батч.
Разбить на 2 подгруппы:
- **D1 Knowledge cycle** (114-116): KB Builder → Freshness → Auto-cat
- **D2 Analytics + Channels** (117-119): Analytics → Weekly Reports → Email

## Preconditions
- Batch A/B/C смержены (Archive/ содержит 102-113)
- `pytest tests/ -q` → 255+ passed
- Categories + encryption инфраструктура на месте
- Postgres + Redis up, ChromaDB доступна

## Порядок

### Group D1 — Knowledge cycle

#### 1. task-116 (auto-categorization) — **FIRST**
Нужна для 114 (clustering tickets может filter'ить по category) и для
117 (analytics группирует по category). Делай сначала.

```bash
pytest tests/ -q  # 268+ passed
git commit -m "Auto-categorize documents on upload via LLM (task-116)"
```

#### 2. task-114 (Knowledge Builder)
Переиспользует clustering-паттерн из task-109 (KB gap detection). После
task-116 категории уже есть — drafts тоже category-aware.

```bash
git commit -m "Knowledge Builder: cluster resolved tickets into KB drafts (task-114)"
```

#### 3. task-115 (freshness monitoring)
Независимо от 114/116, но концептуально закрывает KB-жизненный цикл:
create (114) → categorize (116) → monitor staleness (115).

```bash
git commit -m "Knowledge freshness monitoring: stale + top-cited tracking (task-115)"
```

### Group D2 — Analytics & Channels

#### 4. task-117 (analytics dashboard)
Требует task-116 (categories для top-topics). Цена в traces считается с
момента коммита — historical data не backfill'ится.

```bash
git commit -m "Analytics dashboard: topics, resolution rate, cost tracking (task-117)"
```

#### 5. task-118 (weekly reports)
Использует analytics endpoints (117) + gap detection (109) + freshness
(115). Делай после 117.

```bash
# Dry-run первый
python scripts/weekly_report.py --tenant TEST --dry-run
git commit -m "Weekly quality report: Slack + email digest (task-118)"
```

#### 6. task-119 (email channel)
Независимо от analytics. Самый самодостаточный, можно делать в любой момент,
но ставим последним чтобы не ломать focus remaining батчей.

```bash
EMAIL_CHANNEL_MODE=disabled pytest tests/ -q  # existing passes
EMAIL_CHANNEL_MODE=imap pytest tests/test_email_channel.py -v
git commit -m "Email channel: IMAP polling + webhook mode (task-119)"
```

### 7. Archive
```bash
git mv codex-tasks/task-11{4,5,6,7,8,9}-*.md codex-tasks/Archive/
git mv codex-tasks/orchestrator-batch-d-differentiation.md codex-tasks/Archive/
git commit -m "Archive Batch D differentiation specs (114-119)"
```

## DONE WHEN (batch)
- [ ] 7 коммитов + 1 archive
- [ ] 285+ passed, ruff clean
- [ ] Upload new doc → автокатегория → в metadata
- [ ] Admin UI: KB drafts, stale docs, analytics charts — все рендерятся
- [ ] Slack webhook (mocked) получает test weekly report
- [ ] Email channel: mocked email → RAG reply sent
- [ ] 4 новые миграции: 009, 010, 011, (+maybe 012 для email audit)

## STOP conditions
- LLM classifier (116) часто возвращает invalid JSON → refine prompt,
  попробуй `json_schema` constrain в Ollama. Если стабильно fails —
  ослабь до "uncategorized" default, отчёт
- HDBSCAN может не работать на Windows без C++ — fallback KMeans(n=10)
- IMAP credentials — критично не коммитить. В test mode — mocked server
  (python `imaplib` можно stub'нуть через `responses` / `pytest-mock`)
- Если cost-tracking (117) добавляет latency >50ms per LLM call — сделать
  fire-and-forget (background task), а не sync write

## Parallel safety
- 116 → 114 → 117 (цепочка зависимостей по categories)
- 115, 119 — independent, можно в любом порядке
- Sequential по project-правилу
