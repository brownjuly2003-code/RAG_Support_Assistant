# Batch E — Code Quality & Integration Tests (orchestrator)

Три таска для финального polish'а. Можно делать **до** Batch B/C/D
(если хочется чистую базу для agentic/enterprise work) ИЛИ **после**
(финальный cleanup перед production cutover). См. ROADMAP.md —
рекомендованный порядок: после Batch A, перед Batch B.

## Preconditions
- Batch A смержен минимум (Archive/ содержит 102-106)
- `pytest tests/ -q` → 230+ passed
- ruff clean

## Порядок

### 1. task-120 (dedup root modules) — **FIRST**
Блокирует нормальную работу task-107 (agentic framework будет жить в
`agent/`, а там сейчас конфликтный root-level `graph.py`). Делать
первым из батча.

**Важно:** делать incremental, 1 модуль = 1 commit. Откат дешевле.

```bash
# Пример последовательности для одного модуля:
git mv graph.py agent/graph.py
# обновить все imports
grep -rln "from graph import\|^import graph$" --include="*.py" | xargs sed -i 's|from graph import|from agent.graph import|g'
pytest tests/ -q  # check nothing broken
git commit -m "Move graph.py to agent/graph.py + update imports"

# Повторить для state.py, chunking.py, cache.py и т.п.

# Финальный коммит батча
git commit -m "Deduplicate root-level modules: canonical submodule paths (task-120)"
```

### 2. task-121 (magic numbers) — **SECOND**
После очищенной структуры (120) легче делать глобальные replace'ы.
Независимая работа, 1 файл настроек + множество replacements.

```bash
pytest tests/ -q  # baseline
# Apply changes in batches по файлу:
# - config/settings.py (add fields)
# - graph.py (replace literals)
# - manager.py
# - chunking.py
# ...
pytest tests/ -q  # same count, same pass
git commit -m "Extract magic numbers to config/settings.py (task-121)"
```

### 3. task-122 (integration tests) — **LAST**
Самая большая работа. Нужны testcontainers, Docker-in-Docker для CI.
Не блокирует другие батчи — делается когда есть время.

```bash
# Setup testcontainers locally
pip install testcontainers[postgres,redis]
pytest tests/integration/ -v  # требует Docker daemon running
git commit -m "Integration test suite for E2E flows (task-122)"
```

### 4. Archive
```bash
git mv codex-tasks/task-12{0,1,2}-*.md codex-tasks/Archive/
git mv codex-tasks/orchestrator-batch-e-polish.md codex-tasks/Archive/
git commit -m "Archive Batch E polish specs (120-122)"
```

## DONE WHEN (batch)
- [ ] 3 task-коммита (+ внутренние на 120) + archive
- [ ] `git ls-files graph.py state.py` — либо пусто либо shim с deprecation
- [ ] Magic numbers в settings, не в literals
- [ ] `pytest -m integration` зелёный
- [ ] 300+ total passed (285 unit + integration)
- [ ] README обновлён с новой структурой модулей и integration test guide

## STOP conditions
- task-120: если circular imports после move — **не форсить**, roll back
  конкретный move, оставить shim, в PR пометить как follow-up
- task-121: если тест падает после replace — значит literal был не
  безобидный (где-то edge case). Revert, разобраться в причине, fix, retry
- task-122: testcontainers может не работать на Windows без Docker Desktop
  — alternative: использовать `pytest-postgresql` + fake redis. Документируй
  выбор в PR

## Parallel safety
120 → 121 → 122 строгая последовательность. Не параллелизовать:
- 120 меняет структуру → 121 в старой структуре сломается
- 122 использует всё существующее, последний

## Notes
После Batch E весь roadmap закрыт:
- 222 (baseline) → ~300+ (после всех батчей) tests
- Все 21 task в `Archive/`
- ROADMAP.md может быть архивирован или переписан как "completed 2026-XX-XX"
