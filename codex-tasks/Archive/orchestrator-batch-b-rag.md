# Batch B — Advanced RAG & Intelligence (orchestrator)

Четыре таска закрывающие Phase 3 из commercial-plan. Главная архитектурная
работа батча — task-107 (agentic tool-use), остальные — independent
improvements.

## Preconditions
- Batch A смерджен (`git log --oneline -6` показывает task-106 archive)
- `pytest tests/ -q` → 230+ passed
- ruff clean
- Postgres + Redis up (docker compose up -d postgres redis)

## Порядок

### 1. task-110 (contextual headers) — **DO FIRST**
Самый independent и самый proven ROI (+35% retrieval). Никакого риска
для остальных таск. Если retrieval качество резко вырастет — это
"освободит" eval baseline для task-108.

```bash
# Optionally: run reindex on test KB
python scripts/reindex.py --tenant test
pytest tests/ -q  # 248+ passed
git commit -m "Activate contextual headers in ingestion pipeline (task-110)"
```

### 2. task-108 (nightly eval) — **DO SECOND**
Логически следует за task-110: baseline обновлён после reindex, теперь
ставим drift-мониторинг. Сначала eval, потом всё остальное — чтобы
task-107 изменения можно было оценить количественно.

```bash
# Run once manually to seed baseline
python scripts/nightly_eval.py
git commit -m "Nightly RAGAS eval + drift alert via Prometheus gauge (task-108)"
```

### 3. task-109 (KB gap detection)
Independent от 107, но логически идёт после eval pipeline (переиспользует
инфраструктуру). Перед task-107 — чтобы успеть накопить gap signals.

```bash
git commit -m "KB gap detection: cluster unanswered questions into admin tickets (task-109)"
```

### 4. task-107 (agentic tool-use) — **LAST, longest**
Самая большая архитектурная работа. Делай ПОСЛЕДНЕЙ — если агентик
ломает retrieval, у тебя уже есть eval gate (108) и KB-gap sensor (109)
чтобы это заметить. Feature-flagged `RAG_AGENTIC_MODE=false` по дефолту
— безопасно коммитить даже если есть rough edges.

```bash
# Run eval gate to confirm retrieval not regressed
RAG_AGENTIC_MODE=false pytest tests/ -q  # must stay green
RAG_AGENTIC_MODE=true pytest tests/test_agent_tools.py  # new tests
git commit -m "Agentic tool-use framework with multi-step + confirmation (task-107)"
```

### 5. Archive
```bash
git mv codex-tasks/task-10{7,8,9}-*.md codex-tasks/Archive/
git mv codex-tasks/task-110-*.md codex-tasks/Archive/
git mv codex-tasks/orchestrator-batch-b-rag.md codex-tasks/Archive/
git commit -m "Archive Batch B RAG intelligence specs (107-110)"
```

## DONE WHEN (batch)
- [ ] 5 коммитов + 1 archive
- [ ] 250+ passed
- [ ] ruff clean
- [ ] precision@5 в eval gate ≥ baseline (contextual headers ROI)
- [ ] `RAG_AGENTIC_MODE=true` → tool-use работает; `false` → старый pipeline
- [ ] Prometheus `rag_eval_drift` gauge видна
- [ ] Admin UI показывает KB gaps (может быть пустой список первые 7 дней)

## STOP conditions
- Если contextual headers (task-110) **ухудшают** precision — откат,
  оставить флаг default=false, отчёт
- Если locally установленная LLM не умеет tool-calling (Qwen2.5 должна,
  Llama3 тоже) — fallback на ReAct prompting; если и это не работает —
  закоммитить только scaffolding, полную реализацию отложить
- HDBSCAN может не установиться на Windows без C++ compiler — fallback
  на sklearn KMeans

## Parallel safety
Все 4 таски трогают разные файлы. В теории параллелизуемы, но по
feedback-правилу "sequential only" делаем последовательно.
