# Task 25 — Уборка корня: архив, структура, .gitignore

## Goal
Корень проекта захламлён: старые тесты, примеры, документы, пустые пакеты.
Привести к чистой структуре без удаления работающих модулей.

## Полная карта корня (что делать с каждым файлом)

### Переместить в `archive/` (создать папку)
| Файл | Причина |
|------|---------|
| `graph_route_example.py` | Пример, не импортируется |
| `prompt_for_github.md` | Старый промпт для GitHub |
| `rag_poc_architecture.md` | Старая архитектурная схема PoC |
| `rag_support_assistant_for_github.md` | Старый GitHub README |
| `production-hardening.md` | Закрытый план задач |

### Переместить в `tests/` (или удалить если дублируют)
| Файл | Причина |
|------|---------|
| `test_mock_inbox.py` | Тест вне папки tests/ — переместить |
| `test_retrieval.py` | Тест вне папки tests/ — переместить |
| `test_retrieve_node.py` | Тест вне папки tests/ — переместить |
| `test_route_node.py` | Тест вне папки tests/ — переместить |

**Перед перемещением**: запусти `python test_retrieval.py` и остальные.
Если они уже дублируют тесты из `tests/` — удали (не перемещай).
Если содержат уникальные тесты — переместить в `tests/`.

### Оставить в корне (импортируются или entry-point)
| Файл | Кем используется |
|------|-----------------|
| `main.py` | Entry point |
| `graph.py` | `main.py`, `api/app.py` |
| `manager.py` | `main.py`, `api/app.py` |
| `state.py` | `graph.py`, тесты |
| `prompts.py` | `graph.py` |
| `sqlite_trace.py` | `graph.py`, `api/app.py` |
| `mock_inbox.py` | `api/app.py` |
| `bitrix.py` | `mock_inbox.py` |
| `loader.py` | `api/app.py` |
| `cache.py` | Оставить (используется или будет) |
| `chunking.py` | Оставить (standalone utility) |
| `seed_docs.py` | Dev utility — оставить |

### Пустые пакеты — добавить в .gitignore
`demo/`, `ingestions/`, `vectordb/` содержат только `__init__.py` и `__pycache__`.
Не удалять (могут быть нужны как namespace packages), но исключить `__pycache__` через .gitignore.

---

## Действия

### 1. Создать `archive/` и переместить файлы

```bash
mkdir archive
mv graph_route_example.py archive/
mv prompt_for_github.md archive/
mv rag_poc_architecture.md archive/
mv rag_support_assistant_for_github.md archive/
mv production-hardening.md archive/
```

### 2. Разобраться с root-level тестами

Проверить каждый файл:
- Если `test_mock_inbox.py` дублирует `tests/test_mock_inbox_import.py` — удалить
- Если `test_retrieve_node.py` / `test_route_node.py` содержат уникальные тест-кейсы — переместить в `tests/` и убедиться что `pytest tests/ -v` проходит
- `test_retrieval.py` — если требует Ollama/ChromaDB → переместить в `tests/integration/` (не запускается в CI)

### 3. Обновить .gitignore

Создать или дополнить `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Environment
.env
*.env.local

# Runtime data (generated at startup)
data/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
```

Если `.gitignore` уже есть — добавить только строки которых нет.

### 4. Добавить `archive/.gitkeep`

Чтобы git отслеживал пустую папку:
```
touch archive/.gitkeep
```
(не нужно если в archive уже есть файлы)

---

## CONSTRAINTS
- НЕ удалять и не перемещать: `main.py`, `graph.py`, `manager.py`, `state.py`, `prompts.py`,
  `sqlite_trace.py`, `mock_inbox.py`, `bitrix.py`, `loader.py`, `cache.py`, `chunking.py`, `seed_docs.py`
- НЕ трогать `static/`, `api/`, `config/`, `ingestion/`, `evaluation/`, `tests/`, `docs/`
- `Сброс настрок COMET.py` — добавить в .gitignore, НЕ удалять (это файл пользователя)
- `pytest tests/ -v` — все тесты проходят после перемещений

## DONE WHEN
- [ ] `archive/` существует с 5+ перемещёнными файлами
- [ ] Корень не содержит `.md` файлов кроме `README.md`
- [ ] Корень не содержит `test_*.py` файлов (перемещены или удалены)
- [ ] `.gitignore` содержит `data/`, `__pycache__/`, `.env`
- [ ] `pytest tests/ -v` — все тесты проходят
