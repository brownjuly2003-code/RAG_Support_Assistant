# Task 120 — Deduplicate root-level modules

## Context
POLISH-2 из rec.md. В repo есть дублирование: `graph.py` в root + `agent/`
папка (пустая кроме `__init__.py`, но по плану туда переезжает код
из task-107). Также `state.py` может дублироваться между root и
сабмодулями (проверить). Это source of confusion: какой import правильный?

## Goal
Единственный источник истины для каждого модуля. Root-level файлы
оставляем только если они реально root (напр., `main.py`, `Dockerfile`).
Python-модули живут в сабпакетах.

## Files to change
- Анализ: `python -c "import ast; ..."` или grep по imports:
  - Кто импортирует `from graph import ...` vs `from agent.graph import ...`
  - `from state import ...` vs `from agent.state import ...`
  - `from cache import ...` (корневой `cache.py`) vs `from cache.redis_cache import ...`
  - `chunking.py` (root) — кто использует
- Решение на каждый модуль: переместить или оставить
- Update всех import statements
- `tests/` — тесты тоже надо пересмотреть

## Known duplicates / candidates

| Root file | Target location | Action |
|-----------|-----------------|--------|
| `graph.py` | `agent/graph.py` | Move; root оставить как re-export shim (`from agent.graph import *` + deprecation warning) или полностью удалить если все callers обновим |
| `state.py` | `agent/state.py` | Same |
| `cache.py` | `cache/` (уже есть) | Удалить root, если не imported |
| `chunking.py` | `ingestion/chunking.py` | Move |
| `manager.py` | `vectordb/manager.py` (уже есть!) | Проверить дубль |
| `loader.py` | `ingestion/loader.py` (уже есть) | Проверить |
| `prompts.py` | `agent/prompts.py` (уже есть) | Проверить |
| `mock_inbox.py` | `channels/mock_inbox.py`? | Кто импортирует? Возможно OK в root |
| `bitrix.py` | `channels/bitrix.py`? | То же |

## Implementation sketch

### Step 1: Analyze
```bash
# find all imports
grep -rn "from graph import\|^import graph$\|from state import\|^import state$" --include="*.py" .

# find который файл "настоящий"
diff graph.py agent/graph.py  # если оба есть
```

### Step 2: Пометить единую версию
Для каждого дубля:
1. Выбрать канонический путь (сабпакет)
2. Скопировать содержимое в каноническое место (если там ещё пусто)
3. Удалить или rewrite root-level как re-export с DeprecationWarning:
```python
# graph.py (root) — deprecated shim
import warnings
warnings.warn("Importing from 'graph' is deprecated; use 'agent.graph'", DeprecationWarning, stacklevel=2)
from agent.graph import *  # noqa
```

### Step 3: Обновить все callers
Find-replace во всех `*.py` и `tests/*.py`.

### Step 4: Убрать shim после верификации
После того как все internal callers обновлены — shim можно удалять в
финальном коммите задачи (или оставить на 1 релиз для внешних integrator'ов,
если таковые есть; для single-user проекта — сразу удалить).

## CONSTRAINTS
- Делать **поэтапно** по одному модулю за раз: move → update imports →
  test. НЕ hadoking bulk rename.
- Circular imports — ловушка. При переносе `graph.py` → `agent/graph.py`,
  если он импортирует что-то из root — могут сломаться зависимости.
  Тестировать после каждого move.
- `sys.path` манипуляции (если есть) могут маскировать ошибки — проверь
  что `sys.path.append(".")` / `sys.path.append("./agent")` нигде не
  используется
- Альтернатива: если полная деduplication слишком рискованна — оставить
  shim файлы с `__all__` и deprecation warning, не удалять сразу

## DONE WHEN
- [ ] Анализ завершён, список дублей задокументирован в PR
- [ ] Каждый дубль обработан (moved или kept с обоснованием)
- [ ] Нет conflicting `graph.py` (root) и `agent/graph.py` — либо один
      реальный + shim, либо только один
- [ ] `grep "from graph import" .` — возвращает либо 0 hits, либо
      все обновлены на `from agent.graph import`
- [ ] Все тесты проходят **после каждого** move, не только в конце
- [ ] Добавить в README / CONTRIBUTING секцию "Module layout" с правилом
      "новый код идёт в сабпакеты, не в root"
- [ ] 285+ passed (без новых тестов, только regression)
- [ ] Commit strategy: один коммит на один move (атомарно, легко откатить)
- [ ] Финальный commit: "Deduplicate root-level modules: canonical submodule paths (task-120)"
