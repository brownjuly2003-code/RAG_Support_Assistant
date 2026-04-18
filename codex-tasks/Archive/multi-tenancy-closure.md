# Multi-tenancy closure — full Codex session

Запусти **одну** сессию, которая закроет multi-tenancy (Phase 3 + 4)
за три последовательных коммита. Не параллелить.

## Preconditions
- Ветка: main (или feature/multi-tenancy-closure — если хочешь PR).
- `pytest tests/ -q` → 199 passed (baseline от 2026-04-17).
- `ruff check .` → 0 errors.
- `git status --short` → в `codex-tasks/`:
  - untracked: `task-95-multi-tenancy-enforcement.md`,
    `task-96-per-tenant-chromadb.md`
  - tracked (но выполненные): `task-93-…`, `task-97-…`, `task-98-…`

---

## Commit 1 — housekeeping (спеки в порядок)

```bash
git mv codex-tasks/task-93-multi-tenancy-propagation.md codex-tasks/Archive/
git mv codex-tasks/task-97-model-routing.md codex-tasks/Archive/
git mv codex-tasks/task-98-db-pool-saturation-metrics.md codex-tasks/Archive/
git add codex-tasks/task-95-multi-tenancy-enforcement.md
git add codex-tasks/task-96-per-tenant-chromadb.md
git commit -m "Archive 93/97/98 specs; stage 95/96 multi-tenancy phase 3-4"
```

Не запускай тесты на этом шаге — только rearranging файлов.

---

## Commit 2 — Phase 3: query enforcement

Следуй **целиком** `codex-tasks/task-95-multi-tenancy-enforcement.md`.
Там 516 строк с конкретными сигнатурами, тестами и constraints.

Ключевые инварианты (не забудь):
- **404 вместо 403** для foreign trace в `/admin/traces/{id}` — защита
  от information leak
- Background purge в `_lifespan` остаётся **admin-wide** (retention
  одинаково применяется ко всем tenants)
- `tenant_id` параметр **опциональный** (default None) во всех
  расширенных функциях — не сломай существующие legacy-вызовы

### Checks (обязательно перед commit):
```bash
pytest tests/ -v
# → 207+ passed (199 + 8 новых), 0 failures, 0 errors
ruff check .
# → 0 errors
```

Если flaky `test_ask_returns_429_after_60_requests` — повтори один раз.
Это известная проблема (slowapi state leak), не блокер для commit'а.

```bash
git add -A
git commit -m "Multi-tenancy Phase 3: enforce tenant_id in reads and purges (task-95)"
```

---

## Commit 3 — Phase 4: per-tenant ChromaDB

Следуй `codex-tasks/task-96-per-tenant-chromadb.md` (425 строк).

Ключевые инварианты:
- Collection name sanitize: **3-63 chars**, только `[a-zA-Z0-9._-]`;
  любой другой символ → `_`. Пустая строка → `"default"`.
- Retriever кеш per-tenant + `threading.Lock` (pipeline уже в
  thread-pool'е с task-82)
- `build_vector_store` **инвалидирует** кеш retriever'а для того
  tenant'а (новые чанки должны быть видны сразу)
- BM25 index (если есть в коде) тоже per-tenant — иначе half-leak
- Миграционный скрипт `scripts/migrate_default_collection.py` —
  только создать файл, **не** запускать
- Параметр `tenant_id` опциональный с дефолтом `"default"` — legacy
  тесты не должны сломаться

### Реальная сигнатура
Сигнатуры `build_vector_store` / `get_retriever` в текущем коде могут
отличаться от спеки. **Читай текущий `vectordb/manager.py` перед
правкой** и адаптируй под реальность; инвариант — обе функции
принимают `tenant_id` и выбирают collection по нему.

### Checks:
```bash
pytest tests/ -v
# → 212+ passed (207 + 5 новых), 0 failures
ruff check .
# → 0 errors
```

```bash
git add -A
git commit -m "Multi-tenancy Phase 4: per-tenant ChromaDB collections (task-96)"
```

---

## Post-commit: архивация выполненных спеков

После успеха обоих коммитов:
```bash
git mv codex-tasks/task-95-multi-tenancy-enforcement.md codex-tasks/Archive/
git mv codex-tasks/task-96-per-tenant-chromadb.md codex-tasks/Archive/
git mv codex-tasks/multi-tenancy-closure.md codex-tasks/Archive/
git commit -m "Archive multi-tenancy closure specs (95, 96, orchestrator)"
```

---

## DONE WHEN
- [ ] 4 коммита: housekeeping → task-95 → task-96 → archive
- [ ] `pytest tests/ -q` → **212+ passed**
- [ ] `ruff check .` → 0 errors
- [ ] `git log --oneline -6` показывает полную цепочку
- [ ] multi-tenant можно безопасно деплоить (vector store изолирован)

## STOP conditions
- Если Phase 3 тесты не проходят — **не переходи** к Phase 4. Отчёт
  что сломалось.
- Если Phase 4 ломает существующие тесты ingestion/retrieval — откати
  этот коммит, отчёт. Phase 3 оставить.
- Никаких `--no-verify`, `push --force`, `reset --hard` без явного
  запроса от пользователя.
