# Аудит RAG_Support_Assistant — 03.06.26 (Claude)

**Аудитор:** Claude (Opus 4.8, 1M)
**Дата:** 2026-06-02 (файл по запросу — `03.06.26`)
**HEAD:** `a73687b` (`docs: collect full-corpus reranker A/B`), ветка `master`, worktree **чист**.
**Origin:** `origin/master` отстаёт на **2 коммита** — `a73687b` и `3f0f062` (оба docs/handoff про R1 A/B) **НЕ запушены**. Memory указывал устаревший HEAD `9b219fa` — фактически выше ещё 2 локальных коммита.

---

## 0. Методология и честные границы

Аудит **доказательный**: каждый пункт привязан к `file:line` и подтверждён исполнением статических инструментов или прямым чтением кода, а не пересказом истории.

**Что прогонялось вживую сейчас (надёжно):**
- `ruff check .` (standalone 0.15.11) — статичен, не зависит от версий зависимостей.
- `ruff` широкий скан (`B,UP,SIM,C4,I,PERF,RUF,S,N,ASYNC`) как аудит-сигнал (не как конфиг).
- `bandit 1.9.4 -r . -ll` — статичен.
- Прямое чтение `agent/graph.py`, `vectordb/_base_manager.py`, `config/settings.py`, `api/app.py`, роутеров, `.github/workflows/ci.yml`, lock-файлов.

**Что НЕ воспроизводилось локально (и почему):** на машине **нет venv проекта (3.11)**; глобальный `python` = **3.13.7** с **расходящимся** набором (`langchain 0.3.28` против `langchain-core==1.4.0` в локе). Прогон `pytest`/`mypy` в этом окружении дал бы шум, не отражающий CI (Linux 3.11 + hashed locks). Полный `pytest` (773 теста) ещё и тяжёл для этой машины (~16 мин, history). Поэтому для `pytest`/`mypy`/`pip-audit` **источник истины — CI** (последний зелёный прогон, см. §3). Это явная граница, не пропуск.

---

## 1. Executive Summary

Проект в **сильной форме** и заметно вырос с прошлого аудита (30.05). Это уже не «caps-замороженный» репозиторий, а живой production-grade RAG-сервис: чистые статические гейты, зрелая observability, продуманный provider-runtime, и — главное — **большинство RAG-findings аудита 30.05 закрыты в коде** (R1 зашипен и провалидирован A/B, R2 и R3 починены, R5 улучшен).

**Самооценка:** **8.8 / 10** (локальное инженерное качество). Потолок держит один и тот же фактор, что и месяц назад — **R7: качество RAG не измерено RAGAS-метриками на реальном корпусе при живом LLM** (есть только retrieval-coverage прокси и 3-кейсный live-smoke). Плюс несколько новых **code-level** дефектов средней важности (fire-and-forget задачи, отсутствие CSP).

**Топ-3 на сейчас:**
1. **R7** (HIGH, foundational) — прогнать RAGAS faithfulness/precision/recall на 100-кейсном `curated_cases_aircargo.jsonl` через Colab → зафиксировать baseline-цифры. Датасет и пайплайн уже готовы.
2. **F1** (MEDIUM) — 3 fire-and-forget `asyncio.create_task` без удержания ссылки; самый острый — **запуск regression-job** (`admin_experiments.py:269`).
3. **F2** (MEDIUM, перенос) — нет `Content-Security-Policy` при inline-скриптах и bearer-токене агента в `localStorage`.

---

## 2. Состояние репозитория

| Параметр | Значение |
|---|---|
| HEAD | `a73687b` (master), worktree чист |
| Незапушено | 2 коммита (`a73687b`, `3f0f062`) — docs про R1 A/B |
| Исходники (без тестов/скриптов/archive) | ~19 000 LOC (bandit-счёт), Python |
| Крупнейшие модули | `agent/graph.py` 2429, `api/app.py` 1788, `vectordb/_base_manager.py` 1086, `tracing/_base_trace.py` 1012, `api/routers/conversation.py` 898, `config/settings.py` 876 |
| `scripts/` | 10 026 LOC / 33 файла (вне coverage/mypy/bandit, но в ruff) |
| Тесты | **143 файла, 773 test-функции**, integration 9 файлов |
| Endpoints | 72 (`@app/@router.<verb>`) |
| TODO/FIXME в исходниках | **1** (гигиена отличная) |
| Alembic | 17 ревизий, **single linear head** (16 down_revision) ✔ |

---

## 3. Гейты (verification)

| Gate | Результат | Источник |
|---|---|---|
| `ruff check .` (E,F,W; ignore E501) | **PASS — All checks passed** | прогон сейчас ✔ |
| `bandit -r . -ll` (med+) | **0 medium / 0 high** (19 006 LOC, 0 `#nosec`) | прогон сейчас ✔ |
| `pytest tests/ --ignore=integration` | зелёный на CI (748→ растёт) | CI `ci.yml:143`, не воспроизводил локально (env-mismatch) |
| `pytest tests/integration` | зелёный | CI `ci.yml:198` (`--timeout-method=thread`) |
| coverage `fail_under=70` | ~71.5% (history) | CI; локально не считал |
| mypy strict scope | PASS | CI `ci.yml:117` — **включает `agent/graph.py`** (typed!); `api/app.py` отдельно с `--follow-imports=skip` (см. F7) |
| pip-audit | зелёный к PyPI-сервису | CI; 3 osv-only CVE отложены осознанно (см. §6) |

**Важно про CI-eval-гейт:** `regression_eval` (`ci.yml:262-326`) — **path-filtered + informational**: запускается только при изменении regression-входов/`curated_cases.jsonl` и **не блокирует** мердж по качеству. **RAGAS в CI отсутствует вовсе** (нет упоминаний в workflows). Это и есть структурная причина R7.

---

## 4. Что изменилось с аудита 30.05 (главный value-add) ✅

Сверка findings прошлого аудита по **фактическому коду на `a73687b`**:

| Finding 30.05 | Был | Стало (03.06) | Доказательство в коде |
|---|---|---|---|
| **R1** reranker EN на RU | HIGH open | **ЗАКРЫТ + провалидирован** | `config/settings.py:295` дефолт `BAAI/bge-reranker-v2-m3`; full-corpus A/B (`docs/operations/2026-06-02-mac-fullcorpus-reranker-ab.md`): **bge-v2-m3 80% > OFF 74% > en 42%** |
| **R2** RRF-коллизия по префиксу | MEDIUM open | **ЗАКРЫТ** | `_base_manager.py:227` `_rrf_document_key` → `metadata:{doc_id}:{chunk_id}`, иначе `content:{prefix}:{sha256(full)}` — два чанка с общим 200-преф. больше не схлопываются |
| **R3** per-doc LLM-grade ×5 | MEDIUM open | **ЗАКРЫТ** | `graph.py:1048-1100` `grade_docs` теперь **батчит** в 1 structured-вызов (`build_doc_grade_batch_prompt`); per-doc цикл — только fallback при сбое парсинга |
| **R4** fan-out ~15 вызовов | MEDIUM | **снижен** | за счёт R3: grade 5→1; типичный ответ ≈ **10** последовательных `invoke` (classify+transform+grade(1)+generate+verify(1+N)+evaluate[+suggest]) |
| **R5** BM25 `.lower().split()` | MEDIUM | **улучшен** (остаток LOW) | `_base_manager.py:223` `_tokenize_for_bm25` = regex `[^\W_]+` + `casefold()` — снят прилипающий пунктуатор; **остаётся**: нет лемматизации RU + in-memory индекс на каждый retriever (`:276`) |
| **R6** reranker hardcoded CPU | LOW open | **OPEN** (стал чуть актуальнее) | `_base_manager.py:157,212` оба (`SentenceTransformer` и `CrossEncoder`) `device="cpu"`; с тяжёлым bge-v2-m3 (568M) CPU-латентность реранка выросла |
| **R7** качество не измерено | HIGH foundational | **частично, но ядро OPEN** | датасет вырос: `curated_cases_aircargo.jsonl` **31→100**, `curated_cases.jsonl` **20→35**; пайплайн прогнан на 100 кейсах (**mock**, cost $0, latency 500ms flat — `20260530T231317Z-current-vs-current.json`); **1 живой** smoke на 3 кейсах (`20260531T...ministral-3b-vs-mistral-small`, latency 40.2s→19.8s, реальный cost). **RAGAS faithfulness/precision/recall на масштабе с живым LLM по-прежнему НЕ прогнан** |

**Вывод:** инженерная часть RAG-аудита 30.05 отработана почти полностью. Открытым остаётся **измерение качества** (R7) и **мелочи** (R5-остаток, R6).

---

## 5. Новые findings (code-level, не из аудита 30.05)

#### F1 — Fire-and-forget `asyncio.create_task` без удержания ссылки — **MEDIUM**

`ruff RUF006` × 3 в рантайм-коде:

| Сайт | Что запускается | Серьёзность |
|---|---|---|
| `api/routers/admin_experiments.py:269` | `asyncio.create_task(_app._run_regression_job(...))` — **длительная фоновая работа** | **MEDIUM** |
| `db/audit.py:46` | `asyncio.create_task(_write_entry())` — запись **audit-log** (комплаенс) | MEDIUM |
| `api/routers/conversation.py:406` | `asyncio.create_task(_app._record_citation_stats(...))` — метрики цитат | LOW |

Возвращаемое значение `create_task` не сохраняется. В CPython задача без сильной ссылки **может быть собрана GC до завершения** (документированный footgun asyncio: «save a reference … to avoid a task disappearing mid-execution»).
- `admin_experiments:269` — самый острый: regression-job может «исчезнуть», а его статус в `_app._regression_jobs[run_id]` навсегда останется `"queued"`; конкурентность джобов тоже не ограничена.
- `db/audit:46` — есть внутренний `try/except` с file-fallback (`audit.py:35-44`), но если GC снимет **саму задачу**, не выполнится и fallback → тихая потеря audit-записи.

**Fix:** держать `set()` активных задач на модуле + `task.add_done_callback(tasks.discard)`; для request-scoped (citation stats) — FastAPI `BackgroundTasks`; для regression-job — нормальный job-runner с persisted-статусом и лимитом параллелизма.

#### F2 — Нет `Content-Security-Policy` — **MEDIUM** (перенос M1 из 30.05, всё ещё open)

`grep -i content-security-policy api/` — **пусто**. Security-заголовки есть (`api/app.py:1625-1639`: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS), но **CSP отсутствует**. Страницы используют inline-скрипты, а bearer-токен агента лежит в `localStorage` (`static/agent.html`). XSS-вектор `innerHTML` закрыт ранее, но без CSP нет defense-in-depth: регресс с `innerHTML` снова станет захватом сессии.
**Fix:** добавить `Content-Security-Policy` хотя бы `default-src 'self'; script-src 'self'` (потребует вынести inline-скрипты в файлы или nonce); параллельно рассмотреть httpOnly-cookie для токена агента вместо `localStorage`.

#### F3 — Блокирующий I/O в async-функциях — **LOW**

`ruff ASYNC240` × 4: `api/app.py:982-983` (`Path(chroma_dir).exists()` + `.iterdir()` при создании сессии — на каждый новый session-setup), `channels/telegram_bot.py:47`. Синхронные FS-сисколлы в event-loop. На локальном диске быстро, но формально стопорит цикл под нагрузкой.
**Fix:** обернуть в `asyncio.to_thread` или кэшировать факт наличия store.

#### F4 — `asyncio.run()` + per-call `engine.dispose()` внутри sync `run_qa_pipeline` — **LOW** (латентный)

`graph.py:1987` `asyncio.run(_persist_results())` + `:1983` `await _engine.dispose()` на **каждый** вызов. Путь корректно работает, т.к. граф зовётся через `asyncio.to_thread(session.ask)` (`conversation.py:208`) — в воркер-потоке без активного лупа. **Но**: (1) включается только при `online_evaluators_enabled` (дефолт **off**), (2) `dispose()` глобального async-engine из воркер-потока — потенциальный конфликт с пулом основного лупа, если фичу включат в проде, (3) пересоздание пула на каждый запрос = латентность. Сейчас риск низкий из-за дефолта-off; это footgun на будущее.
**Fix:** при включении online-eval в проде — выделенный engine/loop для воркер-пути, не общий.

#### F5 — Тихое глотание исключений `try/except/pass` ×30 — **LOW**

`ruff S110` = 30 в исходниках (концентрация: `graph.py` 7, `api/app.py` 7). Часть — оправданный best-effort (трейсинг/метрики), но в RAG-пайплайне глотание без `logger.exception` маскирует сбои узлов.
**Fix:** в критичных (retrieval/LLM) сайтах заменить `pass` на `logger.debug/exception`. Точечно, не массово.

#### F6 — Линт-поверхность слишком узкая для «production-hardened» — **LOW (process)**

`pyproject.toml:16` `select = ["E","F","W"]` — только pyflakes+pycodestyle. Широкий скан показывает неуправляемый долг: **106 `RUF100` unused-noqa** (мёртвые подавления — код когда-то имел проблемы, их заглушили и забыли), **42 `I001`** несортированных импортов, **14 `B904`** (потеря цепочки исключений `raise ... from`), **13 `RUF012`** mutable-class-default, **6 `B905`** zip без strict. Ничего из этого не ловится.
**Fix:** поэтапно включить `I` (isort), `B` (bugbear), `RUF`; начать с авто-fix `RUF100`/`I001`, затем разобрать `B904`/`B905` вручную.

#### F7 — `mypy api/app.py --follow-imports=skip` = поверхностная проверка — **LOW**

`ci.yml:118`: `api/app.py` гейтится с `--follow-imports=skip`. Это **не** проверяет импортируемые модули → возможны «фейковые» `no-any-return` и пропуск реальных type-ошибок на границах (известная гоча по другим проектам). Создаёт ложное ощущение strict-покрытия самого большого app-файла.
**Fix:** по мере типизации соседних модулей убрать `--follow-imports=skip` для `api/app.py`.

---

## 6. Безопасность и зависимости

**Bandit:** 0 med/high (B608/B310 осознанно в skip с обоснованием, `pyproject:147-153`). ✔

**CVE в локах (проверено по `requirements.lock`):**

| Пакет | Версия | Статус |
|---|---|---|
| `pyjwt` | 2.13.0 | ✔ закрыт PYSEC-2026-175/177/178/179 (свежий фикс `9b219fa`) |
| `langchain-core` | 1.4.0 | ✔ |
| `langsmith` | 0.8.5 | ✔ |
| `starlette` | 1.0.1 | ✔ (не откатывать — вернёт PYSEC-2026-161) |
| **`chromadb`** | **1.5.9** | ⚠ **CVE-2026-45829 без fixed_in** — непатчуемо, держат latest. Единственный остаточный известный CVE. Принятый риск; мониторить релизы |
| `authlib` | 1.7.0 | ⏸ osv-only CVE-2026-44681 (fix 1.6.12 < 1.7.0 — аномалия-downgrade, нужен разбор, не слепой бамп); CI (PyPI) не валит |
| `langchain-classic` | 1.0.4 | ⏸ osv-only CVE-2026-45134 (fix 1.0.7); compat-риск, отложено осознанно |

Решения по отложенным CVE **корректны и задокументированы** — это управляемый риск, а не пропуск. Гоча зафиксирована: CI `pip-audit` бьёт по **PyPI advisory**, локальный `--service osv` показывает больше — сверять с CI/PyPI, не паниковать.

**Остаточный риск:** bearer-токен агента в `localStorage` + отсутствие CSP (см. F2).

---

## 7. Архитектура и сложность

- **Граф (LangGraph) — современный дизайн 2026.** `classify_complexity → transform_query(+HyDE) → retrieve → grade_docs(CRAG, батч) → generate → verify_facts → evaluate → route_or_retry` с Self-RAG retry (`max_iterations=2`, ограничен — нет бесконечного retry, `graph.py:1779`). Hybrid retrieval (vector+BM25+RRF k=60+cross-encoder) с graceful degradation по `HAS_*`. Это сделано **правильно, не трогать**.
- **Долг сложности (open, перенос M4):** `agent/graph.py` **2429 LOC** (растёт: 2105 на 30.05), `api/app.py` **1788 LOC** (цель Step 8 — ≤600, всё ещё далеко). Router-split сделан хорошо (15 роутеров). Следующий шаг — вынос startup/health/vector-init/services из `app.py`, декомпозиция `graph.py` на node-модули.
- **`scripts/` 10k LOC** вне coverage/mypy/bandit — большой непокрытый слой (бэкапы, eval, бенчмарки). Для опс-скриптов приемлемо, но `restore_verify.py`/`backup_snapshot.py` (508/494 LOC) стоило бы покрыть тестами.

---

## 8. Тесты и покрытие

- 773 теста / 143 файла — солидно; integration-suite есть, с thread-timeout (правильно для anyio-deadlock, закрытого `6e8ac61`).
- Слабые зоны покрытия (history 30.05, не переизмерял локально): `agent/tools.py` ~37%, `auth/oidc.py` ~44%, `api/routers/admin_review.py` ~52%, `api/app.py` ~55% — это ровно critical-зоны. **Точечные тесты ветвлений важнее подъёма общего порога.**
- `pyproject` coverage source **не включает** `integrations/` (275 LOC) и корневой `cache.py` — слепое пятно метрики.

---

## 9. Observability / Ops — сильнейшая сторона (не трогать)

~50 Prometheus-метрик, OTel-спаны на каждый LLM-step (provider/model/usage/cost/duration_ms — готовая база для оптимизации латентности R4), alert_rules, retention-purge, backup/restore с verify, Helm cronjobs (eval/review/backlog/report), circuit-breaker + retry/backoff, liveness/readiness split, graceful shutdown, request-id correlation. Provider-runtime: валидация профилей (`changeme`→missing), `DAILY_COST_LIMIT_USD`, failover GraceKelly→Ollama с кэшем. Здесь добавить нечего.

---

## 10. Долг актуальности (deprecations, календарный)

- `typing.Dict/List`, `Callable` из `typing` → `dict/list` + `collections.abc` (UP035 ×38) — **безвредно** на 3.11/3.13, чистая модернизация (не langchain-breakage, как могло показаться).
- `langchain_community` `Ollama`/`ChatOllama` deprecated → `langchain-ollama` (`graph.py:213-222`, `llm/providers/ollama.py`).
- `authlib.jose` deprecated → `joserfc` (`auth/oidc.py`).
- `langchain_experimental.SemanticChunker` — experimental namespace, риск переезда API (`_base_manager.py`).
- Контекстные заголовки: дефолт `contextual_headers=true` (`settings.py:321`), но это **статический doc-level header**, не настоящий Anthropic contextual retrieval; история фиксирует warning «Contextual header exceeded chunk_size; truncating» (header длиннее `chunk_size=800`). Качественный долг, не баг.

---

## 11. План ремедиации (по ROI)

**Сейчас / эта неделя:**
0. **R7 (HIGH):** RAGAS faithfulness/precision/recall на `curated_cases_aircargo.jsonl` (100 кейсов) через **Colab** (heavy → не на этой машине), Mistral live → зафиксировать baseline-цифры в README и аудит. Датасет и пайплайн готовы; это снимает потолок «недоказуемого качества».
1. **F1 (MEDIUM):** удержание ссылок на 3 `create_task` (regression-job → job-runner; audit → task-set; citation → BackgroundTasks). ~1–2 ч, локально, тестируемо.
2. **F2 (MEDIUM):** добавить CSP `default-src 'self'; script-src 'self'` (+ вынос inline-скриптов/nonce). Defense-in-depth.

**Ближайший месяц:**
3. R6 — `device` из настройки/автодетекта (`cuda/mps/cpu`); важно после тяжёлого bge-v2-m3.
4. F6 — включить ruff `I`+`B`+`RUF` поэтапно (старт с авто-fix `RUF100`/`I001`).
5. Декомпозиция `api/app.py` (≤600) и `agent/graph.py` (node-модули); снять `--follow-imports=skip` (F7).
6. R5-остаток — RU-стемминг (snowball/pymorphy3) для BM25 при наличии замеренной пользы из R7.

**Квартал / gated:**
7. Включить RAGAS-гейт в CI на RU-сете (сейчас regression informational, RAGAS нет вовсе).
8. GraphRAG-шов — только при триггере (>2K докторов/50K чанков), уже обоснованно отложен в ADR.

**Heavy-ограничение среды (соблюдать):** весь ingest BGE-M3 (~2.3ГБ) / RAGAS / reranker A/B — **только Colab/remote**, не на Windows-ноуте и не на 8GB iMac (iMac — только SSH/browser/хост DV2). Локально OK: код-швы, curated-кейсы, доки, статические гейты.

---

## 12. Final Assessment

| Измерение | Оценка | Комментарий |
|---|---|---|
| Код/линт/типы | 9.0 | ruff/bandit чисто; mypy strict (вкл. graph.py); долг — узкий ruff-select + shallow app.py |
| RAG-ядро (дизайн) | 9.0 | современный 2026-стек, R1/R2/R3 закрыты в коде |
| RAG-ядро (доказанное качество) | 6.5 | R7: RAGAS на масштабе не прогнан; есть только retrieval-coverage прокси + 3-кейс smoke |
| Безопасность | 8.5 | bandit clean, CVE управляемы; минус CSP + token в localStorage |
| Архитектура/сложность | 7.5 | graph.py 2429 / app.py 1788 — декомпозиция не доведена |
| Тесты | 8.0 | 773 теста; слабое покрытие critical-зон |
| Observability/Ops | 9.8 | образцово |
| Code-hygiene (новое) | 7.5 | F1 dangling tasks, F5 silent-except, F6 unused-noqa |
| **Итог** | **8.8 / 10** | сильный production-grade RAG; потолок — измерение качества (R7) |

**Главный вывод:** с 30.05 проект закрыл инженерную часть RAG-долга (R1 зашипен+провалидирован, R2/R3 починены, R5 улучшен). Осталось перейти от «отличного по конструкции» к «доказанно отличному» — это **R7 (RAGAS-baseline)**, плюс 2 аккуратных code-level фикса (F1 fire-and-forget, F2 CSP). Все три — конкретны, дёшевы и не требуют переписывания.

---
*Прогон вживую: ruff (PASS), bandit (0 med/high), чтение кода на `a73687b`. pytest/mypy/pip-audit — по CI (env-mismatch локально, см. §0). Heavy RAG-eval — на Colab по запросу пользователя.*
