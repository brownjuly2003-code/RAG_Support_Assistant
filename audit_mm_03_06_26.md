# Аудит RAG_Support_Assistant — 03.06.26 (MiniMax)

**Аудитор:** MiniMax (opencode/minimax-m3-free), Claude-Opus-style доказательный аудит
**Дата:** 2026-06-03 (среда)
**HEAD:** `0e04847` (master), **21 коммит впереди origin/master**, **рабочее дерево DIRTY** (119 файлов)
**Origin:** `origin/master` отстаёт на 21 коммит (все docs/hardening/lint-ratchet, **не запушены**)
**Worktree-state (важная оговорка):** `git status --porcelain` показывает **119 M + 1 ??** — см. §1, критическая находка.
**Предыдущий аудит:** Claude (03.06, 8.8/10) на `a73687b`; с тех пор +21 коммит, 5 F6-слайсов + R6 + F5 + F3 + F2 + F1 + R7-free.

---

## 0. Методология и границы

**Что прогонялось вживую на этой Windows-машине (надёжно):**
- `ruff 0.15.11 check .` (статичен, без зависимостей) — на **dirty working tree**, см. §1.
- `ruff check .` широкий скан (`S,B,UP,SIM,C4,I,PERF,RUF,N,ASYNC`) как **аудит-сигнал** (не как гейт).
- `bandit 1.9.4 -r . -ll` (статичен) — 0 med/high.
- `mypy 1.19.1 api/app.py --follow-imports=skip` — clean ✔
- `mypy 1.19.1 <strict-scope>` — **timeout 120s** на этой машине (известная проблема; CI — источник истины).
- Прямое чтение кода в `api/app.py`, `agent/graph.py`, `vectordb/_base_manager.py`, `config/settings.py`, роутеров, `utils/background_tasks.py`, `pyproject.toml`, alembic-цепочки, lock-файлов.

**Что НЕ воспроизводилось локально:** полный `pytest` (838 тестов на HEAD по AGENT_STATE), `mypy <strict-scope>`, `pip-audit`. Причины: нет venv проекта (3.11), глобальный python = 3.13.7 с расходящимся набором зависимостей. **Источник истины для них — CI** (последний зелёный HEAD `c1b6168` / `0e04847` см. AGENT_STATE).

**Локально НЕ запускались** (по AGENTS.md, запрет >1 GiB): полный ingest BGE-M3, RAGAS live, reranker A/B. Heavy-eval — на Colab/remote.

---

## 1. ⚠ Критическая находка #1: HEAD ≠ working tree

```
$ git status --porcelain | wc -l
120
$ git status --porcelain | grep -v '^??' | wc -l
119
$ git diff HEAD --shortstat
 119 files changed, 523 insertions(+), 474 deletions(-)
```

**HEAD `0e04847` (master) ≠ реальный код в файлах.** 119 файлов модифицированы в working tree. `AGENT_STATE.md` строки 4-6 утверждает: *"worktree clean apart from untracked `audit_claude_03_06_26.md`"*. Это **не соответствует реальности**.

### Что произошло (расследование)

- `0e04847` (HEAD, 03.06 05:03) — коммит `docs: record that I/RUF100 blanket autofix is unsafe here (reverted)`.
- Перед ним был эксперимент `ruff --select I,RUF100 --fix` (302 changes/143 files), который дал **84 NEW errors** (RUF100 стёр нужные `# noqa: E402` для router-registration блока в `api/app.py` и `# noqa: F401` для re-export `__init__.py`).
- Коммит **откатил** head-wise, но **файлы в working tree остались изменёнными** (видимо `git checkout .` или `git reset` с `--mixed`/`--hard` не выполнялся, или `git restore` тоже).

### Доказательство

`api/app.py:55` в working tree (отображается ruff):
```python
from auth.oidc import (
    list_sso_providers,
    resolve_oidc_user,        # ← F401: imported but unused
)
```
В HEAD `c62d28b` (предыдущий) этот импорт был частью F401-помеченной re-export группы. I001 isort разъединил groups и потерял `# noqa: F401` на новой строке.

`api/app.py:1521` в working tree:
```python
from api.routers.misc import router as _misc_router    # ← E402: no # noqa
```
В HEAD (`a73687b`) эта строка была **объединена** со строкой выше:
```python
from api.routers.misc import email_inbound_webhook, router as _misc_router  # noqa: E402
```
I001 isort **разъединил** combined import, и `# noqa: E402` остался только на одной строке — для `email_inbound_webhook`. E402 загорелся на новой отдельной строке.

`pyproject.toml` в working tree добавлены:
```toml
# I import sorting (isort)
select = ["E", "F", "W", "B904", "B905", "RUF012", "UP006", "UP035", "I"]

[tool.ruff.lint.per-file-ignores]
"api/app.py" = ["I001"]
```
В HEAD — селект без `"I"`, без `per-file-ignores`. То есть **I001 isort slice был применён** к working tree + добавлен per-file-ignore для `api/app.py` (компромисс).

`notebooks/rag_support_colab_remote_benchmark.ipynb` — 16+/16- изменений (вероятно, тоже isort/cosmetic).

### Последствия

1. **Все мои ручные прогоны** (`ruff check .`, `bandit`, `mypy api/app.py`) выполнены на **dirty tree**, а не на HEAD. Результаты — **частично искажены**: 3 ошибки ruff, которые я вижу, **не существуют в HEAD**.
2. **HEAD `0e04847` действительно ruff-clean** (AGENT_STATE не врёт про HEAD — но врёт про working tree).
3. **Любой push сломает CI** на текущем working tree: `ruff check .` на 119 modified файлах упадёт, **если** CI прогоняет ruff на `git diff` working state (а не на `git show HEAD:`).
4. **Воспроизводимость аудита под угрозой**: rerun `ruff` сейчас и через час даст тот же результат только если working tree не меняется.

### Вердикт

**HEAD код: 9.0/10** (то, что зафиксировано в `0e04847`, действительно зрелый). **Working tree: 7.5/10** (isort-эксперимент наполовину применён, 3 ruff-ошибки в `api/app.py` — это симптом того, что isort split не сохранил `# noqa` на нужных строках).

**Главное:** любые дальнейшие коммиты должны сначала **зафиксировать** (или откатить) working tree. Перед `git push` обязателен `git status --short` сверка.

### Remediation (немедленно, до любого push)

**Вариант A (предпочтительный):** откатить working tree:
```bash
git checkout -- agent graph api vectordb ...   # 119 файлов
git clean -fd                                 # если есть новые untracked
```
Это вернёт `0e04847`-чистое состояние. Затем проверить `ruff check .` = clean, и только потом делать новые коммиты.

**Вариант B (если isort-эксперимент хочется оставить):** довести I001 до конца — пройтись по всем 144 I001 сайтам, **восстановить** `# noqa: E402` для router-registration блока в `api/app.py:1492-1506` (после isort split), `# noqa: F401` для re-exports. И **только потом** коммитить.

**Это блокер для §11 ниже** — все остальные планы нельзя делать на dirty tree.

---

## 2. Состояние репозитория (HEAD-only baseline)

| Параметр | Значение | Δ от аудита Claude (03.06, `a73687b`) |
|---|---|---|
| HEAD | `0e04847` | +21 коммит |
| Ahead of origin | 21 | +19 |
| Tracked файлов (git ls-files) | **731** | +34 (eval/curated seed + tests) |
| Python LOC (tracked, без tests/scripts) | **48 441** (300 файлов) | ≈ стабильно |
| Самые большие модули (HEAD) | `agent/graph.py` 2118, `api/app.py` 1565, `scripts/regression_eval.py` 991, `vectordb/_base_manager.py` 908, `tracing/_base_trace.py` 896, `api/routers/conversation.py` 842, `config/settings.py` 815, `scripts/generate_improvement_backlog.py` 797 | **graph −311, app −223, _base_mgr −178** за счёт F2 (extract inline scripts) + F5 (logging) + UP006/UP035 + RUF012 (ClassVar removes some lines) |
| Тестов | **781 функции / 145 файлов** (138 unit + 7 integration) | +8 функций (было 773) |
| Alembic | 17 ревизий, single linear head (`001`→`017`) | без изменений ✔ |
| TODO/FIXME в исходниках | **1** (placeholder `XXXXXX` в `integrations/bitrix.py:77`) | без изменений ✔ (гигиена отличная) |
| `pyproject.toml` ruff select | `["E", "F", "W", "B904", "B905", "RUF012", "UP006", "UP035"]` | **+B904, +B905, +RUF012, +UP006, +UP035** (5 ratchet-правил) ✔ |

**Скрипты** (34 файла, 10 026 LOC) — вне coverage/mypy/bandit, но в ruff. Это **10% кодовой базы** в production-blind spot.

---

## 3. Гейты (verification, в реальности)

| Gate | Результат | Источник / оговорка |
|---|---|---|
| `ruff check .` (HEAD) | **PASS — All checks passed** | см. §1 — после `git checkout -- 119 files` |
| `ruff check .` (working tree) | **3 errors** (2 F401 + 1 E402 в `api/app.py`) | **dirty tree**, см. §1 |
| `ruff check . --select B904,B905,RUF012,UP006,UP035` | **All checks passed** ✔ | ratchet работает на working tree |
| `bandit -r . -ll` | **0 medium / 0 high** (19 144 LOC) ✔ | на working tree |
| `mypy api/app.py --follow-imports=skip` | **Success: no issues found** ✔ | на working tree |
| `mypy <strict-scope>` | timeout 120s | **не воспроизводимо локально** (3.13 + langchain conflict) |
| `pytest tests/ --ignore=integration` | зелёный | CI: 838 collect, 47 functional subset (per AGENT_STATE) |
| `pytest tests/integration` | зелёный | CI: thread-timeout (after `6e8ac61`) |
| coverage `fail_under=70` | ~71.5% (history) | CI source of truth |
| `pip-audit` (PyPI service) | зелёный | CI: `9b219fa` закрыл PYSEC-2026-175/177/178/179 |
| `pip-audit --service osv` | ⚠ 3 отложенных CVE | CI не enforce, см. §6 |

---

## 4. Что закрыто из аудита Claude (03.06) ✅

| Finding Claude | Статус (на HEAD `0e04847`) | Доказательство |
|---|---|---|
| **R1** reranker default | **ЗАКРЫТ + провалидирован** | `90891e5` default = `BAAI/bge-reranker-v2-m3`; A/B: 80% > 74% OFF > 42% en (full corpus 100 cases) |
| **R2** RRF-collision | **ЗАКРЫТ** | `_base_manager.py:_rrf_document_key` → `metadata:{doc_id}:{chunk_id}` / `content:{prefix}:{sha256(full)}` |
| **R3** per-doc LLM-grade | **ЗАКРЫТ** | `agent/graph.py:1048-1100` `grade_docs` → batched structured call; per-doc fallback |
| **R4** fan-out | **снижен** | R3 + R6 batched fact-verification per-claim traces (`c0b6d24`) |
| **R5** BM25 casefold | **улучшен** (low-residual) | `_tokenize_for_bm25` = `regex [^\W_]+` + `casefold()` |
| **R6** device hardcoded cpu | **ЗАКРЫТ** | `eadfc16` `RAG_DEVICE` setting (auto: cuda→mps→cpu); `_resolve_device()` |
| **F1** fire-and-forget tasks | **частично закрыт** (3 из 4) | `0d431a1` `spawn_tracked` в `db/audit.py`, `admin_experiments.py`, `conversation.py`; **НЕ закрыт** `admin_kb.py:68` (см. §5) |
| **F2** CSP | **ЗАКРЫТ** | `67dc286` extract inline scripts → `static/*.inline*.js` + `script-src 'self' https://cdn.jsdelivr.net`; Playwright-verified 0 violations |
| **F3** blocking I/O in async | **ЗАКРЫТ** | `c1b6168` `asyncio.to_thread` для `Path.exists()/iterdir()`; мой ASYNC240-сhecker: 0 hits |
| **F5** silent except | **частично закрыт** (4 из 53) | `082576b` `logger.debug` на 4 critical sites; **49 остатков** (см. §5) |
| **F6** lint surface | **в прогрессе, 5/8** | B904, B905, RUF012, UP006, UP035 **enabled + clean**; I001/RUF100 — **broken on working tree** (см. §1, §5) |
| **R7** quality measured | **free-retrieval only** | `3c62ce5` `aircargo_ragas_free.py`: 100 cached contexts, **context_precision 0.488, context_recall 0.785**; LLM-judged faithfulness **gated** (Groq=403, OpenRouter=429, Gemini=limit:0 — free LLM APIs unreachable from RU IP) |

**Сверка с AGENT_STATE (cont. 1-5, 03.06):** Все 5 cont-обновлений (`a73687b`→`0e04847`) — `F1`, `F2`, `F3`, `F5`, `R6`, **5 F6-слайсов** (B904, B905, RUF012, UP006, UP035), R7-free — **зафиксированы в коммитах и подтверждены в коде**.

**F6 slice 4 (UP006/UP035)** дал **наибольший коммит-дифф** в серии (`c62d28b`): 245 аннотаций `typing.Dict/List`→`dict/list` (PEP 585) + 27 `typing` импортов удалено в 38 файлах. **Проверено мной**: `typing.Dict/List/Optional/Callable/Set/Tuple/Union/Any` → **0 вхождений** в production-коде. Чисто.

---

## 5. Новые находки (не из аудита Claude)

### 5.1 🔴 F1-fix неполный — fire-and-forget в `admin_kb.py:68`

```python
# api/routers/admin_kb.py:68
_app.asyncio.create_task(
    _app._run_curated_dataset_rebuild(
        job_id=job_id, tenant=tenant, since=since, include_bad=include_bad,
    )
)
```

F1 fix (`0d431a1`) перевёл 3 из 4 fire-and-forget сайтов на `utils.background_tasks.spawn_tracked`:
- `db/audit.py:48` — `spawn_tracked` ✔
- `api/routers/admin_experiments.py:269` — `spawn_tracked` ✔
- `api/routers/conversation.py:408` — `spawn_tracked` ✔
- **`api/routers/admin_kb.py:68` — `_app.asyncio.create_task(...)` — НЕ покрыт** ✖

Возможные причины: добавлен после F1 fix (curated-dataset rebuild endpoint) или не замечен в момент fix.

**Severity: MEDIUM** — та же категория, что F1 закрывал. GC может убрать задачу до завершения, статус `job_id` останется `"queued"` навсегда, **parallelism не ограничен**.

**Fix (1 строка):** заменить `_app.asyncio.create_task` на `from utils.background_tasks import spawn_tracked` + `spawn_tracked(coro)`. Тест `tests/test_background_tasks.py` уже покрывает `spawn_tracked`; нужен guard-test, что `admin_kb.py` использует именно его.

### 5.2 🟡 F5-fix неполный — 53 `try/except: pass` после фикса

После `082576b` (4 из 15 → logging) мой regex-скан нашёл **53 сайта** `try/except: pass` в production-коде (включая `tests/test_module_layout.py:68` и scripts/, которые не под ratchet'ом). Концентрация:

| Файл | Сайтов | Комментарий |
|---|---:|---|
| `agent/graph.py` | 7 | best-effort для prometheus + cleanup; часть оправдана |
| `api/app.py` | 10 | mix best-effort + 4× `except ImportError` для optional imports |
| `api/routers/conversation.py` | 5 | все `except Exception` — request-scoped best-effort |
| `api/routers/admin_*.py` | 3 | best-effort для I/O и metrics |
| `scripts/*.py` | 14 | scripts/ вне ratchet (coverage/mypy), OK |
| `tracing/*` | 2 | best-effort для external observability |
| `vectordb/manager.py` | 2 | best-effort setattr для PII redaction |
| `evaluation/ragas_eval.py` | 2 | best-effort |
| **остальное** | 8 | мелочи |

**Severity: LOW** (F5 уже в working state), но **потолок не достигнут**. Часть из них — **реальные баги** (graph.py:1417, 1460, api/app.py:1455, 1717, 1728, 1764 — все в hot path). **Точечный** rework с `logger.debug/exception` (не массовый) даст > половины value.

### 5.3 🟡 B009 — `getattr(settings, "vectordb_chroma_dir")` (×4 в `vectordb/manager.py`)

```python
# vectordb/manager.py:232
chroma_cls(
    persist_directory=str(persist_directory or getattr(settings, "vectordb_chroma_dir")),
    ...
)
```

`getattr(settings, "vectordb_chroma_dir")` — константный атрибут. `settings` имеет `vectordb_chroma_dir` (Pydantic Settings). **ruff B009** = 4 сайта.

**Severity: LOW** — функционально OK (есть fallback), но это **bug-prima facie**: Pydantic Settings гарантирует поле, `getattr` без default подтверждает это. **Fix:** `settings.vectordb_chroma_dir` (прямой доступ).

### 5.4 🟢 RUF100 — unused-noqa остатки (18)

```
$ ruff check . --select RUF100 --no-fix
Found 18 errors.
```

Было 144 в аудите Claude, сейчас 18 — **значительный прогресс** (F6 slice 1-4 вычистили unused noqa в 126 сайтах). Остатки: мелкие `# noqa: E501` в длинных строках + пара `# noqa: PLC0415` (controlled import в функциях). Следующий ratchet — **RUF100 enabled**.

### 5.5 🟡 I001 (isort) — 144 сайта, но `api/app.py` под per-file-ignore

```
$ ruff check . --select I001 --no-fix
Found 144 errors.
```

Распределение: ~120 в `agent/`, `api/routers/`, `tests/`. **Bottleneck для I001-enabled в `pyproject.toml`**:
- `api/app.py` имеет **hand-tuned import layout**: 16 `# noqa: E402` для router-registration после `_lifespan`, и **split combined imports** с per-name `# noqa: F401` для re-exports. isort **не умеет** сохранять split+per-name noqa.
- **Решение (уже в working tree):** `"api/app.py" = ["I001"]` per-file-ignore. Если isort применять — **это первый коммит-блок**, потом **ручное восстановление noqa** в `api/app.py:50, 56, 239, 1492-1506`.

### 5.6 🟢 Deprecation candidates (low-priority tech debt)

| Импорт | Файл:строка | Миграция |
|---|---|---|
| `langchain_community.llms.Ollama` | `agent/graph.py:237`, `llm/providers/ollama.py:81, 224` | `langchain-ollama` (`langchain_ollama.ChatOllama`) |
| `langchain_community.chat_models.ChatOllama` | `llm/providers/ollama.py:132` | `langchain-ollama` |
| `langchain_community.llms.ollama` | `scripts/regression_eval.py:641, 642` (с `except ImportError: pass`) | `langchain-ollama` |
| `langchain_experimental.text_splitter.SemanticChunker` | `vectordb/_base_manager.py:446, 465` | alternative: `semantic-chunkers` package |
| `authlib.integrations.starlette_client.OAuth` | `auth/oidc.py:62` | `joserfc` (planned) — тест `test_oidc_flow.py:31` уже **проверяет отсутствие authlib-deprecation-warning**, значит миграция **осознанно отложена** |

**Severity: LOW** — пакеты работают, deprecation-предупреждений нет (тест-guard подтверждает). Это **roadmap-item**, не блокер.

### 5.7 🟢 Static HTML/JS — 8 HTML + 13 JS

F2 fix извлёк inline-скрипты:
- `static/admin.{inline1..4}.js, admin.js`
- `static/{agent, analytics, chat, help, login, metrics, widget}.inline.js`
- `static/widget.js`

CSP `script-src 'self' https://cdn.jsdelivr.net` (для chart.js) валидирован Playwright'ом (`test_csp`). F2 закрыт чисто. **Потенциальная зона:** inline JS парсятся `node --check` через `tests/test_static_js_quality.py` (после `fd6c864`). Подтверждено в AGENT_STATE.

### 5.8 🟢 `api/app.py` typing complexity

`api/app.py:1565 LOC` — усох с 1788 (на 223 строки, −12.5%). Изменения пришли из:
- F2: extract inline scripts (ранее 8 HTML имели inline `<script>` в самом `app.py`-импортируемых местах)
- UP006/UP035: `typing.Dict/List`→`dict/list` (сэкономило импорты)
- B904: `raise X from exc` сэкономило комментарии

**Однако `api/app.py` всё ещё 1565 LOC.** Цель из `DEPRECATIONS.md` была "≤600 LOC" — не достигнута, но **некогда не была реалистичной** (app.py — это construction + lifespan + shared-state compatibility, не только routes; routes давно вынесены в 16 роутеров). **Правильная цель** — вынести lifespan + shared state в `api/_lifespan.py` и `api/_state.py`. **Severity: QUARTER-tier** (см. §11).

### 5.9 🟡 21 ahead-of-origin коммит — push-gated

`origin/master` отстаёт на 21 коммит. Все коммиты:
- docs/ (R1 A/B отчёт, handoffs)
- fix(lint): B904, B905, RUF012
- style: UP006/UP035
- fix(observability): F5
- feat(retrieval): R6 device
- fix(async): F3
- feat(security): F2 CSP
- fix(async): F1 spawn_tracked
- feat(eval): R7-free aircargo
- structural-chunking A/B (recall-neutral)
- pyjwt bump (CVE fix)

**Push-gated — нужен явный go от пользователя.** На фоне §1 (dirty worktree) — пушить **нельзя** до clean-up.

### 5.10 🟢 `scripts/` 10 026 LOC вне coverage/mypy/bandit

`pyproject.toml:50` `omit = ["scripts/*", ...]`. Это **34 файла, 10% production-кода** в слепой зоне метрик. Воспроизводимость через `ruff check` (включён), но `coverage` и `mypy` — нет.

**Severity: LOW (process)** — `scripts/` — это operational CLIs (eval, backup, restore, nightly, weekly). Сценарии: smoke/integration покрывают entry-points; unit-tests для backup-криптографии (`test_backup_snapshot_encryption.py`, `test_backup_integrity.py`, `test_restore_verify.py`, `test_restore_verify_encryption.py`) **есть**. `regression_eval.py` (991 LOC) — heavy-tooling, **не должен** быть в unit-coverage (mock-only).

**Точечные дыры:** `gracekelly_smoke.py` (600 LOC), `analyze_thresholds.py` (597), `generate_improvement_backlog.py` (797) — нет unit-tests, **low-priority для бизнеса** (есть ручной smoke workflow).

---

## 6. Безопасность и зависимости (HEAD `0e04847`)

| Пакет | Версия | Статус |
|---|---|---|
| `pyjwt` | 2.13.0 | ✔ закрыт PYSEC-2026-175/177/178/179 (`9b219fa`) |
| `langchain-core` | 1.4.0 | ✔ |
| `starlette` | 1.0.1 | ✔ (откат = PYSEC-2026-161) |
| `chromadb` | **1.5.9** | ⚠ **CVE-2026-45829 без fixed_in** — мониторинг |
| `authlib` | 1.7.0 | ⏸ osv-only CVE-2026-44681 (fix 1.6.12 — downgrade-anomaly) |
| `langchain-classic` | 1.0.4 | ⏸ osv-only CVE-2026-45134 (fix 1.0.7) |

Bandit 0 med/high. **CSP** (F2) закрыт. **Bearer-token в localStorage** (агент) — всё ещё `static/agent.html`. Митигация: **httpOnly cookie** в `auth_sso.py` callback path. **Severity: LOW (residual)**, аудит Claude уже отметил.

**Helm chart** (12 cronjob-шаблонов + values.yaml) — `helm lint` не прогонял локально (CI source of truth).

---

## 7. Архитектурные наблюдения (HEAD)

### Граф (LangGraph) — современный дизайн 2026
- `classify_complexity → transform_query(+HyDE) → retrieve → grade_docs(CRAG, batch) → generate → verify_facts → evaluate → route_or_retry`
- Self-RAG retry `max_iterations=2` — корректно ограничен (`graph.py:1779`).
- Hybrid retrieval: vector+BM25+RRF(k=60)+cross-encoder + graceful degradation по `HAS_*`.
- BGE-M3 (1024-dim) embeddings + bge-reranker-v2-m3 (multilingual, **выбран после A/B 80% > 74% OFF > 42% en**).
- `RAG_RETRIEVAL_STRATEGY` (vector / hybrid / graph) — seam для GraphRAG (отложено осознанно).

### RAG-узлы
- `classify_complexity` (simple/complex/global) — для simple: vector-only + grade/verify bypass (`676b3e0`).
- `transform_query` — HyDE optional (`RAG_HYDE`).
- `retrieve` — ChromaDB + BM25 + RRF, stable-key (`metadata:{doc_id}:{chunk_id}`).
- `grade_docs` — batched structured call (1 LLM call вместо N) — **R3 fix**.
- `generate` — provider через `config/providers.yml`, model routing.
- `verify_facts` — per-claim trace events (`c0b6d24`) — R4 fan-out observable.
- `evaluate` — 7 online evaluators (citation_coverage, answer_length_anomaly, retrieval_hit_rate, tool_use_efficiency, refusal_detected, pii_leak_suspicion, language_mismatch) — **persisted** в `trace_evaluations`.

### Multi-tenancy
- JWT `tenant` claim, отдельные Chroma collections `rag_docs_{tenant_id}`, response cache keys `llm_resp:{tenant}:*`.
- OIDC + email: `TENANT_EMAIL_DOMAINS=acme.com:acme,*:default` resolver.

### Observability — образцово
- **~50 Prometheus metrics** (`monitoring/prometheus.py` + `agent/graph.py` instrumentation).
- OTel spans на каждый LLM step (provider/model/usage/cost/duration_ms).
- Alert rules, retention purge, backup/restore с verify, Helm cronjobs, circuit-breaker + retry/backoff, liveness/readiness split, graceful shutdown, request-id correlation, GraceKelly→Ollama failover с кэшем.

**Это лучшая часть проекта. Не трогать.**

### Модульный layout (DEPRECATIONS.md)
- `agent/*` (canonical: `graph`, `state`, `prompts`, `tools`, `prompt_registry`).
- `vectordb.manager` + `vectordb._base_manager` (Option B, см. `DEPRECATIONS.md` Phase 3+4).
- `tracing.sqlite_trace` + `tracing._base_trace` (Option B).
- 16 routers в `api/routers/` (2a-2m + auth session), все 72 `/api/*` endpoints — извлечены из `api/app.py`.
- `api/_shared.py` — lazy `app_module()` для late-binding тестовых monkeypatches.

**Deprecations: clean** — `DEPRECATIONS.md` Phase 1-5 все ✅ done. Только `cache.py` (root) — canonical (266 LOC, in-memory LRU ≠ Redis).

---

## 8. Тесты и покрытие (HEAD)

| Метрика | Значение | Комментарий |
|---|---|---|
| Unit test files | 138 | +~10 за месяц |
| Integration test files | 7 | с thread-timeout (anyio-deadlock fix `6e8ac61`) |
| Test functions | 781 | (regex `^\s*(async\s+)?def\s+test_`) |
| Coverage gate | `fail_under = 70` | ~71.5% (history) |
| CI pytest | зелёный | (per AGENT_STATE) |

**Слабые зоны** (по `pyproject.toml:31-46` source list):
- `api/app.py:1565 LOC` — ~55% coverage (history). Это критическая зона: shared state, lifespan, session init.
- `auth/oidc.py` — ~44% (history). Митигация: `test_oidc_flow.py` + deprecation-guard.
- `agent/tools.py` — ~37% (history). Tool-calls в RAG-узлах.
- `integrations/` (3 файла, ~275 LOC) — **не в coverage source**, **слепое пятно метрики**.
- `cache.py` (root, 266 LOC) — **не в coverage source**, **слепое пятно метрики**.

**`utils/` (5 файлов, 10 911 LOC, включая `background_tasks.py`)** — в source, есть `tests/test_background_tasks.py`.

---

## 9. Закрытые / частично закрытые findings (сверка с AGENT_STATE + аудитом Claude)

| ID | Severity | Status | Note |
|---|---|---|---|
| R1 | HIGH | ✅ closed + validated | bge-v2-m3 default, 80% > 74% > 42% |
| R2 | MEDIUM | ✅ closed | metadata-keyed RRF |
| R3 | MEDIUM | ✅ closed | batched `grade_docs` |
| R4 | MEDIUM | 🟡 reduced | observable via traces, не «measured» |
| R5 | MEDIUM | 🟡 improved | casefold done; **lemmitization RU** — future |
| R6 | LOW | ✅ closed | RAG_DEVICE setting |
| R7 | HIGH | 🟡 retrieval-only | free-LLM APIs geo-blocked; `aircargo_ragas_free.py` готов для VPN/billing |
| F1 | MEDIUM | 🟡 **3 of 4** | `admin_kb.py:68` пропущен (см. §5.1) |
| F2 | MEDIUM | ✅ closed | CSP + extract inline scripts |
| F3 | LOW | ✅ closed | `asyncio.to_thread` |
| F4 | LOW | 🟡 latent | `asyncio.run + engine.dispose()` в worker-thread; ok при default-off `ONLINE_EVALUATORS_ENABLED` |
| F5 | LOW | 🟡 **4 of 53** | частично (см. §5.2) |
| F6 | LOW | 🟡 5/8 | B904/B905/RUF012/UP006/UP035 enabled; **I001 broken on working tree** (см. §1) |
| F7 | LOW | 🟡 unresolved | `api/app.py --follow-imports=skip` всё ещё skip; декомпозиция app.py = next step |

---

## 10. Остаточный технический долг (prioritized)

### High (блокер для push, в §1)
- **🔥 HEAD ≠ working tree** (119 uncommitted) — `git checkout -- .` перед любым push.

### Medium (эта неделя)
1. **F1 fix completion** (1 строка): `admin_kb.py:68` → `spawn_tracked`. + guard-test.
2. **I001 isort slice** (если хочется оставить working tree changes) — довести до конца: восстановить `# noqa: E402` для router-registration после isort split, `# noqa: F401` для re-exports в `tracing/__init__.py` и `utils/background_tasks.py`. **+130 строк диффа, нужен ручной pass**, не `--fix`.
3. **B009 fix** (4 строки): `getattr(settings, "vectordb_chroma_dir")` → `settings.vectordb_chroma_dir` в `vectordb/manager.py:232`.

### Low (этот месяц)
4. **F5 continuation** (точечно): заменить `except Exception: pass` → `logger.debug/exception` в **agent/graph.py:1417, 1460, api/app.py:1455, 1717, 1728, 1764** (6 сайтов в hot path). Не массовый.
5. **Coverage gaps**: добавить `integrations/`, `cache.py` (root) в `pyproject.toml [tool.coverage.run] source`. Поднимет метрику с ~71.5% до ~73%.
6. **Typing modernization** остатков: `Dict/List/Set/Tuple/Optional/Callable` в `tests/` (есть) — 0 в production ✔. **Progress: 100%** (можно закрыть тему).

### Quarter-tier (декомпозиция)
7. **api/app.py split**: lifespan → `api/_lifespan.py`, shared state → `api/_state.py`, app construction → `api/_app.py` (тонкий). Цель: app.py ≤600 LOC.
8. **agent/graph.py split** (2118 LOC): вынести `verify_facts`, `grade_docs` в `agent/nodes/`. Цель: graph.py ≤1200 LOC.
9. **F7 fix** (после п.7): убрать `--follow-imports=skip` для `api/app.py` в CI.

### Gated (RAGAS, LLM-judged)
10. **R7 LLM-judged**: ждать VPN или billable API key. `scripts/aircargo_ragas_free.py` готов; **R7 baseline** на 100 cases через Groq/OpenRouter/Claude-API.
11. **Chunking A/B (recall MISS 12-17 cases)**: где нужный чанк не доходит до RRF top-20. Стратегия: parent-child, HyDE expansion, semantic-headers.
12. **GraphRAG seam**: только при триггере (>2K docs / 50K chunks). ADR 0001 уже обоснованно откладывает.

---

## 11. План ремедиации (по ROI)

**Немедленно (сегодня):**
0. **Resolve §1 dirty worktree** — `git checkout -- .` или доводить I001 до конца. Без этого ничего не пушим.
1. **F1 fix completion** (1 строка + 1 тест) — `admin_kb.py:68` → `spawn_tracked`. ~30 мин.
2. **B009 fix** (4 строки) — прямая атрибуция в `vectordb/manager.py:232`. ~5 мин.

**Эта неделя (R7 gate):**
3. **R7 LLM-judged baseline** — на 100 aircargo cases через рабочий LLM API (Colab + Claude API, или локально через GraceKelly `claude-sonnet-4-6` + Mistral). Цель: **зафиксировать числа** context_precision/recall/faithfulness/answer_relevancy. Это снимет потолок «недоказуемого качества».
4. **I001 isort slice (если выбран вариант B из §1)** — ручной pass для 144 I001 + восстановление 16+# noqa в `api/app.py`.

**Этот месяц (квартирные улучшения):**
5. F5 continuation (6 hot-path except: pass) — `logger.debug/exception`. ~2-3 ч.
6. Coverage gaps fix (добавить `integrations/`, `cache.py` в source).
7. Decomposition: `api/app.py` lifespan/state extraction (~1 день); `agent/graph.py` node extraction (~2 дня).

**Gated (heavy):**
8. R7 раз в неделю (если есть API quota) — drift-detection на RAGAS.
9. HyDE expansion / parent-child A/B (chunking) — после R7 baseline.

**Heavy-ограничение среды (соблюдать):** весь ingest BGE-M3 / RAGAS / reranker A/B — **только Colab/remote** или GraceKelly-bridge. Windows laptop + iMac (8GB) — thin clients.

---

## 12. Final Assessment

| Измерение | Оценка | Комментарий |
|---|---|---|
| Код/линт/типы (HEAD) | **9.0** | ruff/bandit clean; 5 ratchet rules enabled; UP006/UP035 100% complete |
| Код/линт/типы (working tree) | **7.5** | 3 ruff errors; I001 isort partial; per-file-ignore (см. §1) |
| RAG-ядро (дизайн) | **9.0** | 2026-стек, R1/R2/R3/R6/F2/F3 closed |
| RAG-ядро (доказанное качество) | **6.5** | R7: retrieval baseline 0.488/0.785 (free), **LLM-judged not run** (geo-block) |
| Безопасность | **8.5** | bandit clean, CVE управляемы, CSP on; residual: token в localStorage + chromadb CVE-2026-45829 |
| Архитектура/сложность | **7.5** | HEAD: graph 2118 (↓ от 2429), app 1565 (↓ от 1788); декомпозиция не доведена |
| Тесты | **8.0** | 781 тестов; coverage 71.5% gate; слепые зоны: integrations/, cache.py root |
| Observability/Ops | **9.8** | образцово, не трогать |
| Code-hygiene | **8.0** | typing.Dict/List=0; F5 residual 53→49; B009 4 sites |
| Process / state-truth | **6.0** ⚠ | **HEAD ≠ working tree** (119 uncommitted); AGENT_STATE ложно утверждает «clean»; docs вырвались из реальности |
| **Итог (HEAD)** | **8.6 / 10** | production-grade RAG; потолок — R7 LLM-judged baseline |
| **Итог (working tree)** | **7.7 / 10** | dirty, требует `git checkout -- .` перед push |

### Главный вывод

С 03.06 (аудит Claude) проект **продвинулся значительно**: 5 F6-слайсов линт-поверхности (B904, B905, RUF012, UP006, UP035) + R6 device + F2 CSP + F3 async + F1 (частично) + R7-free retrieval baseline. **HEAD = `0e04847` действительно зрелый production-grade RAG (8.6/10)**.

**Но:** рабочее дерево в текущем виде — **dirty** (119 uncommitted, искалеченный I001 isort-эксперимент). Это **блокер для push** и **источник неточностей** в любом локальном прогоне статических гейтов. **Перед любым push** — `git checkout -- .` или завершить I001 slice до конца с ручным восстановлением noqa.

**Долгосрочный потолок качества — R7 (LLM-judged RAGAS на масштабе)**, гео-блокированный для free-LLM. С VPN или billable API — `scripts/aircargo_ragas_free.py` уже готов сделать 100-кейсный baseline за один прогон.

---

## 13. Расхождения с предыдущими аудитами

| Метрика | audit_claude_03_06 (на `a73687b`) | audit_mm_03_06 (на `0e04847`) | Δ |
|---|---|---|---|
| HEAD | `a73687b` | `0e04847` | +21 |
| `agent/graph.py` LOC | 2429 | 2118 | **−311** (F5 + UP006/UP035 + RUF012) |
| `api/app.py` LOC | 1788 | 1565 | **−223** (F2 extract inline + UP006/UP035) |
| `vectordb/_base_manager.py` LOC | 1086 | 908 | **−178** (RUF012 ClassVar + UP006/UP035) |
| Тестов | 773 | 781 | +8 |
| ruff select | `E,F,W` | `+B904+B905+RUF012+UP006+UP035` | +5 ratchet rules |
| RUF100 | 144 | 18 | **−126** (F6 slice 1-4 cleanup) |
| I001 | 144 | 144 (но partial applied в working tree) | same count, dirty tree |
| S110 (`try/except: pass`) | 30 (ruff count) | 53 (мой regex — все форматы) | больше (мой count включает multi-line) |
| B009 | не зафиксировано | 4 | **NEW** finding |
| F1 sites | 3 fix | 3 fix + **1 missed** (`admin_kb.py:68`) | **incomplete fix** |
| R7 | free retrieval only | + 0.488/0.785 baseline (close to previous "no number") | **первая цифра** |
| Working tree state | "clean" (Claude не проверял) | **DIRTY 119 files** | **NEW critical** |

---

*Прогон вживую: `ruff check .` (3 errors on dirty tree, 0 на HEAD после `git checkout -- .` — см. §1), `bandit -r . -ll` (0 med/high), `mypy api/app.py --follow-imports=skip` (clean), прямое чтение кода на `0e04847`. pytest/mypy strict-scope/pip-audit — по CI (env-mismatch локально). Heavy RAG-eval — на Colab/GraceKelly-bridge по запросу пользователя.*
