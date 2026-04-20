# Tech debt closure — одна Codex-сессия

Запусти одну сессию, которая закроет три tech-debt задачи
последовательно. Порядок важен — task-101 делай **последним**, чтобы
не шуметь renormalize-дельтой в остальных коммитах.

## Preconditions
- `pytest tests/ -q` → **214 passed**
- `ruff check .` → 0 errors
- `git log --oneline -3` показывает `ad41657` (Archive multi-tenancy
  closure specs) как последний коммит

## Порядок

### 1. task-99 — fix flaky rate-limit test
Следуй `codex-tasks/task-99-fix-flaky-rate-limit-test.md`.

**Критерий:** тест должен стабильно проходить 3 раза подряд в полном
прогоне. Если slowapi API отличается — смотри `python -c "from api.app import limiter; print(vars(limiter._storage))"`
и адаптируй путь к storage dict.

```bash
git add tests/conftest.py
# + test file если менял
git commit -m "Fix flaky rate-limit test: reset slowapi state in conftest (task-99)"
```

### 2. task-100 — wire redis cache to LLM responses
Следуй `codex-tasks/task-100-wire-redis-cache-for-llm-responses.md` —
**полностью**, это самая большая из трёх.

Ключевое: `LLM_CACHE_ENABLED=false` по умолчанию. Тестируй с
`monkeypatch.setenv("LLM_CACHE_ENABLED", "true")` — ни один существующий
тест не должен сломаться с дефолтным флагом.

```bash
git add -A
git commit -m "Wire redis cache to LLM responses: tenant-scoped, feature-flagged (task-100)"
```

Sanity-check: после этого коммита `pytest tests/ -q` → **220+ passed**.

### 3. task-101 — .gitattributes + renormalize
Следуй `codex-tasks/task-101-gitattributes-line-endings.md`.

Два коммита:
```bash
# Коммит 3.1
git add .gitattributes
git commit -m "Add .gitattributes for consistent line endings (task-101)"

# Коммит 3.2
git add --renormalize .
git commit -m "Renormalize line endings to LF across repo"
```

### 4. Archive specs
```bash
git mv codex-tasks/task-99-fix-flaky-rate-limit-test.md codex-tasks/Archive/
git mv codex-tasks/task-100-wire-redis-cache-for-llm-responses.md codex-tasks/Archive/
git mv codex-tasks/task-101-gitattributes-line-endings.md codex-tasks/Archive/
git mv codex-tasks/tech-debt-closure.md codex-tasks/Archive/
git commit -m "Archive tech debt closure specs (99, 100, 101, orchestrator)"
```

## DONE WHEN
- [ ] 5 коммитов: task-99 → task-100 → .gitattributes → renormalize → archive
- [ ] `pytest tests/ -q` → **220+ passed**, стабильно (прогнать 2 раза)
- [ ] `ruff check .` → 0 errors
- [ ] `git log --oneline -8` показывает всю цепочку чисто
- [ ] Следующий `git add` любого файла **не** пишет CRLF warning

## STOP conditions
- Если task-99 не стабилизируется за 2 попытки — отчёт + переходи к
  task-100. Flakiness можно добить отдельно.
- Если task-100 ломает существующие тесты — откатить коммит, отчёт.
  Феча-флаг должен гарантировать что с `false` ничего не меняется.
- Никаких `--no-verify` / `push --force` без явного указания.
