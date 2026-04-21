# Task 126 — Hygiene & consistency audit

## Goal
Одним проходом собрать отчёт обо всех гигиенических и консистентностных проблемах репо после параллельного прогона arc 102-122. Не чинить — только описать, что нужно сделать. Отчёт — вход для последующего cleanup-таска.

## Context
- Repo: `D:\RAG_Support_Assistant` (Python 3.13, FastAPI + LangGraph + ChromaDB + Ollama).
- Arc 102-122 прогнан параллельными Codex-сессиями, изменения не закоммичены: 42 modified + ~70 untracked файлов. Tests 293 passed, ruff clean. Но repo перед коммитом нуждается в аудите.
- Известные подозрительные места (их, скорее всего, больше):
  - Мусор в корне: `New folder/`, `Сброс настрок COMET.py`.
  - Дублирующие директории: `archive/` (корень) vs `codex-tasks/Archive/`, `ingestion/` vs `ingestions/`.
  - Корневые модули после task-120 (dedup-root-modules): `prompts.py` и `state.py` остались как deprecation shims (правильно), но `graph.py`, `bitrix.py`, `loader.py`, `manager.py`, `chunking.py`, `seed_docs.py`, `sqlite_trace.py`, `mock_inbox.py` — статус неясен (переехать / shim / удалить).
  - `__pycache__/` в корне — видно в `ls`, должно быть в `.gitignore`.
  - Alembic: 8 новых миграций (004_escalated_tickets … 011_trace_costs) добавлены разными Codex-сессиями параллельно — риск конфликта `down_revision`.
  - Зависимости: task-ы добавили otel-sdk (111), authlib (112), cryptography / pgcrypto (113), ragas (108), aioimaplib / email-parser (119). Консистентность `requirements.txt` vs `pyproject.toml` не проверена.
  - Env vars: новые vars от 6 тасков должны быть в `.env.example`, `docker-compose.yml`, `deploy/helm/values.yaml` одновременно.
  - Secrets: шанс, что кто-то из Codex-сессий залил реальный ключ в `.env.example` или xардкод в код.
- Spec-файлы реализованных тасков: `codex-tasks/task-10{2..9}-*.md`, `task-11{0..3}-*.md`, `task-12{0..2}-*.md`, `codex-tasks/Archive/task-11{4..9}-*.md`.

## Deliverables
`codex-tasks/cleanup-report.md` со следующей структурой:

```markdown
# Cleanup report — post arc 102-122

## 1. Trash / artifacts
- [path] — описание + действие (delete / keep / rename)
- ...

## 2. Duplicate / suspicious directories
- `archive/` (корень): содержимое — ...; статус — ...; действие — ...
- `ingestion/` vs `ingestions/`: различия ...; действие — ...
- ...

## 3. Root modules — task-120 dedup aftermath
| Module | Status | agent/* counterpart? | Imported from? | Action |
|--------|--------|----------------------|----------------|--------|
| prompts.py | deprecation shim | agent/prompts.py ✅ | ... | keep |
| state.py | ... | ... | ... | ... |
| graph.py | ... | ... | ... | ... |
| (все 8 модулей) |

## 4. .gitignore / untracked
- `__pycache__/` в `.gitignore`? — проверено ...
- `reports/` — в `.gitignore`? должно ли быть?
- [другие untracked, которые не должны попасть в коммит]

## 5. Alembic chain
- Последовательность: 003 → 004_... → 005_... → ... → 011_...
- Проверка `down_revision`: все линейны? — ✅ / ❌ (если ❌: какие файлы конфликтуют)
- Migration rollback test: (не запускать, но отметить — возможна ли `alembic downgrade base` без ошибок)

## 6. Dependencies
### requirements.txt vs pyproject.toml
| Package | requirements.txt | pyproject.toml | Used in |
|---------|------------------|----------------|---------|
| opentelemetry-sdk | ✅ 1.x | ❌ / ✅ | tracing/otel.py |
| authlib | ... | ... | auth/oidc.py |
| cryptography | ... | ... | db/crypto.py |
| ragas | ... | ... | scripts/nightly_eval.py |
| aioimaplib (или аналог) | ... | ... | channels/email_channel.py |
| ... |

### Missing deps
- [если код импортирует пакет, не в manifestе]

### Unused deps
- [если manifest объявляет пакет, не используемый в коде]

## 7. Env var consistency
Для каждой новой переменной из `.env.example`:
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|---------------------|-------------------------|---------------|
| OIDC_CLIENT_ID | ✅ placeholder | ✅ | ✅ | ✅ |
| ENCRYPTION_KEY | ... | ... | ... | ... |
| OTEL_EXPORTER_OTLP_ENDPOINT | ... | ... | ... | ... |
| IMAP_HOST | ... | ... | ... | ... |
| (все новые vars) |

## 8. Secrets audit
- Grep по коду: `sk-`, `BEGIN PRIVATE KEY`, `ghp_`, `Bearer ey`, real-looking API keys — findings или clean.
- `.env.example`: все значения placeholder-образные (`change-me`, `your-key-here`, и т.п.), не реальные.
- Git history scan: `git log -p --all -S"sk-"` (и другие pattern'ы) — findings или clean.

## 9. Deprecated shim consumers
Grep по коду (кроме shim'ов самих): `from prompts import`, `from state import`, `import prompts`, `import state`.
- Все внутренние импорты переведены на `agent.*`? — ✅ / список файлов, которые ещё импортят старые пути.

## 10. CRLF / line endings
- `.gitattributes` создан в task-101. Проверить: `git check-attr -a <sample.py>` показывает `text eol=lf`?
- Модифицированные файлы: есть ли warnings от git о CRLF при `git status`? Какие файлы?

## 11. Scope creep
Untracked файлы, не упомянутые ни в одной spec (102-122):
- [path] — не найден в spec-файлах; вероятная причина: ...
- ...

## Summary
- Trash: N items
- Duplicate dirs: N
- Root modules needing action: N
- Alembic conflicts: N
- Missing deps: N; Unused deps: N
- Env var gaps: N
- Secrets findings: N (expected 0)
- Deprecated-import violations: N
- Scope-creep files: N
```

## Acceptance
- Покрыты все 11 секций, даже если пустые (написать "нет находок").
- Evidence для каждой проблемы: конкретный путь + цитата / номер строки, а не "кажется".
- Действие для каждой находки: `delete` / `keep` / `move to X` / `rename` / `add to .gitignore` / `add dep to file` и т.д.
- Ничего не изменено в репо (никаких `rm`, никаких `git add`, никаких редактирований).
- Отчёт в UTF-8, на русском (разделы/ячейки; код/пути английские).
- Файл сохранён: `codex-tasks/cleanup-report.md`.

## Notes
- **НЕ чинить** — это следующий таск.
- **НЕ запускать тесты** (они зелёные).
- **НЕ трогать файлы** проекта — только читать + писать отчёт.
- Метод: Read / Grep / Bash (`git log`, `git status`, `git check-attr`, `alembic history --verbose` ok).
- Если находишь что-то, не попадающее ни в одну секцию 1-11, добавь секцию "12. Other" с той же структурой (что / evidence / action).
- Для секции 6 (deps): импорты ищи через `grep -rE "^(from|import) <pkg>" --include="*.py"`, сравни с `requirements.txt` и `[project.dependencies]` / `[tool.poetry.dependencies]` в `pyproject.toml`.
- Для секции 5 (alembic): `alembic history` или чтение каждого файла `down_revision = "..."` и проверка, что цепочка линейна.
