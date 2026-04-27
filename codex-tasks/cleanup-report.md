# Cleanup report — post arc 102-122

## 1. Trash / artifacts
- `New folder/` — пустая директория в корне; `Get-ChildItem` вернул 0 элементов, `git check-ignore -v "New folder"` не даёт hit. Действие: `delete`.
- `Сброс настрок COMET.py` — локальный destructive script; `Сброс настрок COMET.py:7-20` делает `Stop-Process`, `netsh winsock reset`, `Remove-Item` по браузерным профилям. Файл скрыт правилом `.gitignore:17`, но физически лежит в корне. Действие: `delete`.
- `__pycache__/`, `archive/legacy-tests/__pycache__/`, `ingestion/__pycache__/`, `reports/__pycache__/` — generated artifacts; `.gitignore:1` уже игнорирует `__pycache__/`, `git check-ignore -v` это подтверждает для root и `archive/legacy-tests`. В root `__pycache__/` лежат кэши для `graph.py`, `manager.py`, `mock_inbox.py`, `sqlite_trace.py` и др. Действие: `delete` каталоги/`*.pyc`, правило ignore `keep`.

## 2. Duplicate / suspicious directories
- `archive/` (корень): содержит legacy docs/tests, включая `archive/legacy-tests/test_retrieval.py:30-33` с импортами `demo.seed_docs` и `ingestion.chunking`, а также `archive/graph_route_example.py:37-38` с old-style examples. `codex-tasks/Archive/` одновременно используется как архив task-specs. Статус: два разных архива под одним generic name. Действие: `rename` root `archive/` во что-то вроде `archive-legacy/` или `docs/archive/legacy`; `codex-tasks/Archive` оставить для spec-файлов.
- `ingestion/` vs `ingestions/`: `ingestion/__init__.py:4-12` — живой пакет ingestion; `ingestions/__init__.py:1-6` описывает "Интеграции" и не имеет consumers (`rg \bingestions\b` по `*.py` вернул 0 hits). Статус: stray typo-package/leftover rename. `integrations/` уже создан для `bitrix.py`/`mock_inbox.py`, поэтому действие теперь только `delete ingestions/`.

## 3. Root modules — task-120 dedup aftermath
| Module | Status | Counterpart? | Imported from? | Action |
|--------|--------|--------------|----------------|--------|
| ~~`prompts.py`~~ | удалён 2026-04-26 | `agent/prompts.py` ✅ | consumers переведены на `agent.prompts` | `done` |
| ~~`state.py`~~ | удалён 2026-04-26 | `agent/state.py` ✅ | consumers переведены на `agent.state` | `done` |
| ~~`graph.py`~~ | удалён 2026-04-26 | `agent/graph.py` ✅ | consumers переведены на `agent.graph` | `done` |
| ~~`bitrix.py`~~ | перенесён 2026-04-27 | `integrations/bitrix.py` ✅ | `integrations/mock_inbox.py` | `done` |
| `loader.py` | дубль полной реализации; root docstring уже говорит `ingestion/loader.py` (`loader.py:1`) | `ingestion/loader.py` ✅ | `api/app.py:187`, `tasks/ingest_task.py:23` | `reconcile` различия, оставить только пакетный путь, root сделать `shim` или `delete` |
| `manager.py` | каноническая логика всё ещё в root, хотя docstring говорит `vectordb/manager.py` (`manager.py:2`) | `vectordb/manager.py` ✅, но wrapper импортирует root (`vectordb/manager.py:11`) | `api/app.py:177`, `ingestion/pipeline.py:35`, `channels/telegram_bot.py:39`, `vectordb/manager.py:11`, tests | `move` core под `vectordb/`, обновить callers, root сделать `shim` или `delete` |
| `chunking.py` | orphan full implementation в root; docstring говорит `ingestion/chunking.py` (`chunking.py:2`) | `ingestion/chunking.py` ❌ | active import consumers не найдены | `move` в `ingestion/chunking.py` или `archive`, если модуль мёртв |
| ~~`seed_docs.py`~~ | перенесён 2026-04-27 | `demo/seed_docs.py` ✅ | active consumers не найдены; `archive/legacy-tests/test_retrieval.py:30` ожидает `demo.seed_docs` | `done` |
| `sqlite_trace.py` | каноническая логика всё ещё в root, хотя docstring говорит `tracing/sqlite_trace.py` (`sqlite_trace.py:2`) | `tracing/sqlite_trace.py` ✅, но wrapper импортирует root (`tracing/sqlite_trace.py:7`) | `api/app.py:441,927,1665,1986,2008,2125,2546,2574`, `scripts/nightly_eval.py:19`, `tracing/__init__.py:16` | `move` core в `tracing/sqlite_trace.py`, перевести consumers, root сделать `shim` или `delete` |
| ~~`mock_inbox.py`~~ | перенесён 2026-04-27 | `integrations/mock_inbox.py` ✅ | `agent/graph.py`, `tests/test_mock_inbox_import.py` | `done` |

## 4. .gitignore / untracked
- `__pycache__/` в `.gitignore`? — да: `.gitignore:1`, а `git check-ignore -v __pycache__/bitrix.cpython-313.pyc` и `archive/legacy-tests/__pycache__/...` подтверждают, что правило работает. Но физические каталоги уже накопились в дереве. Действие: `delete generated caches`, правило `keep`.
- `reports/` — в `.gitignore` нет, и whole-dir игнорировать не нужно: каталог содержит source `reports/renderer.py`, а не только output. Мусор здесь только `reports/__pycache__/renderer.cpython-313.pyc`. Действие: `keep reports/`, `delete reports/__pycache__/`.
- `Сброс настрок COMET.py` — сейчас скрыт правилом `.gitignore:17`, что прячет локальный артефакт вместо его удаления. Действие: `delete file`; после этого правило можно убрать в cleanup-task.
- `New folder/` — не покрыт `.gitignore` и не попадает в `git status` только потому, что пустые директории git не показывает. Действие: `delete`.
- Другие untracked-файлы, которые не стоит автоматически добавлять в arc-commit, перечислены в section 11.

## 5. Alembic chain
- Последовательность по `alembic history`: `001 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008 -> 009 -> 010 -> 011`.
- Проверка `down_revision`: все линейны — `004_escalated_tickets.py:13 -> "003"`, `005_eval_results.py:12 -> "004"`, `006_knowledge_gaps.py:12 -> "005"`, `007_user_sso_fields.py:12 -> "006"`, `008_enable_pgcrypto.py:14 -> "007"`, `009_kb_drafts.py:13 -> "008"`, `010_document_stats.py:12 -> "009"`, `011_trace_costs.py:12 -> "010"`. Статус — ✅ конфликтов `down_revision` не найдено.
- Migration rollback test: не запускался. Структурно chain откатываемый, но `008_enable_pgcrypto.py:28-32` требует `DB_ENCRYPTION_KEY`, а `008_enable_pgcrypto.py:61-75` реально шифрует/дешифрует данные через `pgcrypto`. Действие: `run rollback smoke-test on disposable PostgreSQL` перед merge.

## 6. Dependencies
### requirements.txt vs pyproject.toml
| Package | requirements.txt | pyproject.toml | Used in |
|---------|------------------|----------------|---------|
| `authlib` | ✅ `requirements.txt:54` | ❌ `pyproject.toml` не содержит dependency section | `auth/oidc.py:13` |
| `opentelemetry-sdk` | ✅ `requirements.txt:58` | ❌ | `tracing/otel.py:71-73` |
| `opentelemetry-exporter-otlp` | ✅ `requirements.txt:59` | ❌ | `tracing/otel.py:66` |
| `opentelemetry-instrumentation-*` | ✅ `requirements.txt:60-63` | ❌ | `tracing/otel.py:67-70` |
| `requests` | ✅ `requirements.txt:53` | ❌ `pyproject.toml` не содержит dependency section | `integrations/bitrix.py:42` |
| `ragas` | ❌ | ❌ | `evaluation/ragas_eval.py:6-10` прямо говорит, что метрики реализованы `WITHOUT the ragas package` |
| `aioimaplib` / `email-parser` | ❌ | ❌ | `channels/email_channel.py:3-6` использует stdlib `email` / `imaplib` / `smtplib` |
| `cryptography` | ❌ | ❌ | `db/crypto.py:1-8` использует pgcrypto через SQLAlchemy/DB, python-import отсутствует |

### Missing deps
- `requests` — импортируется в `integrations/bitrix.py:42`; прямой runtime dependency добавлен в `requirements.txt` 2026-04-27. `pyproject.toml` сейчас tool-only, без dependency section.
- `pyproject.toml` — глобальная inconsistency: `pyproject.toml:1-17` содержит только tool-config (`ruff`/`pytest`) и не объявляет ни одной runtime-зависимости. Действие: либо завести `[project.dependencies]`/`[tool.poetry.dependencies]`, либо официально оставить один manifest и убрать требование dual-sync из процесса.

### Unused deps
- Явно доказанных unused runtime deps среди новых пакетов не найдено.
- Но есть spec/code drift:
  - task-108 ожидал `ragas`, а текущая реализация — локальный `evaluation/ragas_eval.py` без внешнего пакета.
  - task-119 упоминал `aioimaplib` / `email-parser`, а текущая реализация email-channel — синхронная stdlib.
  - task-113 в python-коде опирается на `pgcrypto`, а не на пакет `cryptography`.

## 7. Env var consistency
Evidence base: `config/settings.py:182-288,350-352` объявляет новые env-группы; точечный `Select-String` по `.env.example`, `docker-compose.yml`, `deploy/helm/values.yaml` дал статусы ниже.

### OTel
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|--------------------|-------------------------|---------------|
| `OTEL_ENABLED` | ❌ | ✅ `docker-compose.yml:77` | ✅ `deploy/helm/values.yaml:41` | ✅ default `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | ❌ | ✅ `docker-compose.yml:78` | ✅ `deploy/helm/values.yaml:42` | ✅ local collector endpoint |
| `OTEL_SERVICE_NAME` | ❌ | ✅ `docker-compose.yml:79` | ✅ `deploy/helm/values.yaml:43` | ✅ static service name |

### SSO / OIDC
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|--------------------|-------------------------|---------------|
| `GOOGLE_OIDC_CLIENT_ID` | ❌ | ❌ | ❌ | ✅ feature disabled if absent |
| `GOOGLE_OIDC_CLIENT_SECRET` | ❌ | ❌ | ❌ | ✅ feature disabled if absent |
| `AZURE_OIDC_TENANT` | ❌ | ❌ | ❌ | ✅ feature disabled if absent |
| `AZURE_OIDC_CLIENT_ID` | ❌ | ❌ | ❌ | ✅ feature disabled if absent |
| `AZURE_OIDC_CLIENT_SECRET` | ❌ | ❌ | ❌ | ✅ feature disabled if absent |
| `TENANT_EMAIL_DOMAINS` | ❌ | ❌ | ❌ | ⚠️ blank disables tenant routing for email/SSO |

### Encryption
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|--------------------|-------------------------|---------------|
| `DB_ENCRYPTION_KEY` | ❌ | ❌ | ❌ | ❌ `config/settings.py:350-352,421-423` falls back to insecure dev key |

### Email channel
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|--------------------|-------------------------|---------------|
| `EMAIL_CHANNEL_MODE` | ❌ | ❌ | ❌ | ✅ default `disabled` |
| `IMAP_HOST` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `IMAP_PORT` | ❌ | ❌ | ❌ | ✅ default `993` |
| `IMAP_USER` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `IMAP_PASS` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `IMAP_FOLDER` | ❌ | ❌ | ❌ | ✅ default `INBOX` |
| `SMTP_HOST` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `SMTP_PORT` | ❌ | ❌ | ❌ | ✅ default `587` |
| `SMTP_USER` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `SMTP_PASS` | ❌ | ❌ | ❌ | ⚠️ blank safe only while channel disabled |
| `SMTP_FROM_ADDRESS` | ❌ | ❌ | ❌ | ✅ default `support@example.com` |
| `EMAIL_WEBHOOK_SECRET` | ❌ | ❌ | ❌ | ⚠️ empty secret |

### Reports / analytics / categorization
| Var | .env.example | docker-compose.yml | deploy/helm/values.yaml | Default safe? |
|-----|--------------|--------------------|-------------------------|---------------|
| `LLM_COST_PER_1M_TOKENS` | ❌ | ❌ | ❌ | ⚠️ implicit pricing fallback |
| `REPORT_SLACK_WEBHOOK` | ❌ | ❌ | ❌ | ✅ empty disables Slack |
| `REPORT_EMAIL_RECIPIENTS` | ❌ | ❌ | ❌ | ✅ empty disables email |
| `REPORT_SMTP_HOST` | ❌ | ❌ | ❌ | ⚠️ inherits `SMTP_HOST` or empty |
| `REPORT_SMTP_PORT` | ❌ | ❌ | ❌ | ✅ inherits `587` |
| `REPORT_SMTP_USER` | ❌ | ❌ | ❌ | ⚠️ inherits `SMTP_USER` or empty |
| `REPORT_SMTP_PASS` | ❌ | ❌ | ❌ | ⚠️ inherits `SMTP_PASS` or empty |
| `CATEGORIES_CONFIG_PATH` | ❌ | ❌ | ❌ | ✅ local path default |

### Additional consistency gap
- `config/settings.py:88-93` объявляет `chunk_size/chunk_overlap` через `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP`, а `config/settings.py:131-132` объявляет те же поля повторно через `CHUNK_SIZE` / `CHUNK_OVERLAP`. В dataclass выигрывает второе объявление; первая пара env-флагов фактически shadowed. Действие: `pick one naming scheme`, удалить мёртвый alias или явно задокументировать precedence.

## 8. Secrets audit
- Grep по текущему дереву: строгий regex-скан вне `codex-tasks/**`, `archive/**`, `*.md`, `__pycache__` не нашёл real-looking `sk-...`, `ghp_...`, `Bearer ey...` или `BEGIN PRIVATE KEY`. Статус — ✅ clean.
- `.env.example`: secret-bearing vars в основном пустые, но `.env.example:90-91` задаёт конкретные dev-credential values — `POSTGRES_PASSWORD=rag_dev_password` и `DATABASE_URL=postgresql://rag:rag_dev_password@localhost:5432/rag_assistant`. Это не похоже на production secret, но и не placeholder-style пример. Действие: `replace with changeme-style placeholders`.
- Git history scan: `git log -G "sk-[A-Za-z0-9]{10,}"`, `git log -G "ghp_[A-Za-z0-9]{20,}"`, `git log -G "Bearer ey[A-Za-z0-9._-]{10,}"` вернули 0 hits. Примечание: наивный `git log -S"sk-"` даёт ложный шум из-за строк вроде `/ask-ui`; использовать его как единственный сигнал нельзя.

## 9. Deprecated shim consumers
Grep по коду (кроме архивных/spec-файлов): `from prompts import`, `from state import`, `import prompts`, `import state`.

- Root-level `graph.py`, `state.py`, `prompts.py` уже удалены.
- Активных consumers root-level `prompts.py`/`state.py`/`graph.py` в обычном кодовом пути не найдено.
- Статус: ✅ clean.
- Действие: keep; исторические упоминания в `archive-legacy/`, `codex-tasks/Archive/`, `rec.md` не являются runtime consumers.

## 10. CRLF / line endings
- `.gitattributes:2,5-17` принудительно держит LF для `*.py`, `*.md`, `*.yml`, `*.yaml`, `*.toml`, `*.html`, `*.css`, `*.js`; Windows-исключения ограничены `*.bat`, `*.cmd`, `*.ps1` (`.gitattributes:19-22`).
- `git check-attr -a api/app.py .env.example deploy/helm/values.yaml` вернул `eol: lf` для всех трёх sample files. Статус — ✅.
- `git status` не содержит предупреждений о CRLF conversion. Действие: `keep current policy`; cleanup не требуется.

## 11. Scope creep
Method: для каждого untracked path был сделан exact search по basename/path во всех spec-файлах `task-102..122`; items ниже дали 0 hits.

- `.pre-commit-config.yaml`, `requirements-dev.txt` — не найдены в arc-specs; вероятная причина: подготовка task-127 (`ci pipeline` / pre-commit). Действие: `separate commit` или не включать в merge arc 102-122.
- `docs/CHANGELOG.md` — не найден в arc-specs; вероятная причина: task-128 (`changelog`). Действие: `separate commit`.
- `codex-tasks/task-123-arc-102-122-verification-sweep.md`, `task-124-readme-arc-102-122-update.md`, `task-125-arc-6-proposal.md`, `task-126-hygiene-consistency-audit.md`, `task-127-ci-pipeline.md`, `task-128-changelog.md`, `task-129-backup-restore-runbook.md`, `codex-tasks/verification-report.md`, `codex-tasks/arc-6-proposal.md` — follow-up/post-arc planning artifacts. Действие: `keep out of arc feature commit`; оформлять отдельным docs/planning commit.
- `codex-tasks/Archive/ROADMAP.md`, `codex-tasks/Archive/orchestrator-batch-a-ux.md`, `...-b-rag.md`, `...-c-enterprise.md`, `...-d-differentiation.md`, `...-e-polish.md` — orchestration/meta docs, не referenced individual arc-specs. Действие: `separate planning archive` или не включать в feature merge.
- `codex-tasks/Archive/task-102-inline-citations.md` ... `codex-tasks/Archive/task-122-integration-tests.md` — 21 untracked archived copies spec-файлов самих задач. Это не runtime deliverables, а meta-archive. Действие: либо `commit separately as docs-only archive`, либо убрать из рабочего дерева перед feature commit.
- `tests/test_magic_numbers_settings.py`, `tests/test_module_layout.py`, `tests/test_startup_concurrency.py` — exact paths не найдены в arc-spec text; вероятные причины: support-tests для task-121, task-120 и более ранней concurrency-work. Действие: `verify ownership before commit`.

## Summary
- Trash: 3 grouped findings
- Duplicate dirs: 2
- Root modules reviewed: 10; move/shim follow-up нужен для 4; closed — 6
- Alembic conflicts: 0
- Missing deps: 0; Unused deps: 0 proven; manifest drift: `pyproject.toml` не отражает runtime deps вообще
- Env var gaps: 30 vars с хотя бы одним gap; 27 из них отсутствуют во всех трёх поверхностях сразу
- Secrets findings: 0 real-looking leaks; 1 placeholder-hygiene issue в `.env.example`
- Deprecated-import violations: 0
- Scope-creep files: 42
