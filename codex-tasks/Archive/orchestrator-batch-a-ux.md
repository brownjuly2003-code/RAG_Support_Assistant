# Batch A — UX Commercial Grade (orchestrator)

Пять тасков, которые вместе закрывают Phase 2 из commercial-plan. Это
first батч roadmap'а — **high visible value, low architectural risk**.

## Preconditions
- `pytest tests/ -q` → **222 passed**
- `ruff check .` → 0 errors
- HEAD: `34f4f03 Archive tech debt closure specs`

## Порядок выполнения

### 1. task-102 (inline citations) — **DO FIRST**
Это фундамент для task-103 (mobile source panel) и task-106 (citations
показываются operator'у в context panel). Без citations остальные
visible-wins выглядят недокрашенными.

```bash
# После работы
pytest tests/ -q  # 225+ passed
ruff check .
git add -A && git commit -m "Inline citations in bot answers with source panel (task-102)"
```

### 2. task-103 (mobile responsive) — параллелизация возможна с task-104
Оба трогают `static/styles/components.css`, но в разных секциях
(responsive queries vs focus styles). Лучше **последовательно** — сначала
task-103 (layout changes первый), потом task-104 поверх.

```bash
git commit -m "Mobile-first responsive with 3 breakpoints (task-103)"
```

### 3. task-104 (WCAG axe-core)
Фиксы поверх task-103 (task-103 уже добавит viewport meta в templates).
Добавляет playwright + axe в test suite.

```bash
git commit -m "WCAG AA compliance: axe-core audit + fix criticals (task-104)"
```

### 4. task-105 (UX polish)
Изолированно от 102-104 — отдельные компоненты. Можно после task-104
или параллельно если разные сессии.

```bash
git commit -m "UX polish: upload progress, error recovery, onboarding (task-105)"
```

### 5. task-106 (agent copilot)
Самая большая — новая миграция, новые endpoints, новая страница. Можно
выделить в отдельный день.

```bash
alembic upgrade head  # проверить
pytest tests/ -q  # 230+ passed
git commit -m "Agent copilot dashboard with ticket context + AI draft (task-106)"
```

### 6. Archive specs
```bash
git mv codex-tasks/task-10{2,3,4,5,6}-*.md codex-tasks/Archive/
git mv codex-tasks/orchestrator-batch-a-ux.md codex-tasks/Archive/
git commit -m "Archive Batch A UX specs (102-106)"
```

## DONE WHEN (batch)
- [ ] 6 коммитов + 1 archive
- [ ] `pytest tests/ -q` → **230+ passed**
- [ ] ruff clean
- [ ] Lighthouse mobile ≥80 на chat.html
- [ ] axe-core 0 critical/serious на всех страницах
- [ ] Screenshots в PR: citations, mobile (3 sizes), onboarding, agent copilot

## STOP conditions
- Если LLM перестал вставлять `[N]` стабильно в task-102 — попробуй
  few-shot examples в prompt; если не помогает — откат, отчёт
- Если axe-core выдаёт violations которые требуют архитектурных изменений
  (полный rewrite какой-то страницы) — помечай как follow-up, закрывай
  только то что фиксится малой кровью
- Если playwright не ставится в Windows dev-окружении — axe-тесты делаем
  opt-in через `PLAYWRIGHT_ENABLED=1` env, CI запускает их на Linux

## Notes для CC (верификатор)
- После task-102 — проверь что retrieval quality не упал: прогони 3
  golden Q&A, убедись что `[N]` markers не ломают evaluator
- После task-106 — проверь что tenant isolation работает: создай ticket
  как tenantA, запроси `/api/agent/tickets` как tenantB → должен быть
  пустой список (не 403)
