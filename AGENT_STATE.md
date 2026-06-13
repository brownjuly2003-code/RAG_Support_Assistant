# Agent State

## 2026-06-14 Update (Type-hardening) — mypy strict-scope: api routers + helpers

> **START HERE (type-hardening линия).** Заход `/auto продолжи` (после R1 ниже; адаптивные шаги R2/F2 за гейтом/Mac) → продолжена mypy strict-серия. **PUSHED: `9030706` (api strict) + `c4255be` (yaml-стаб CI-фикс), origin синхронизирован, CI run `27482448746` = success (type-check зелёный).** Отдельный workstream от adaptive-retrieval.
>
> **🔴 Поймана+починена yaml-гоча (стоила 1 красного CI, `c4255be`):** `9030706` локально зелёный (gate Success 20), но CI type-check упал — `api/routers/admin_experiments.py:139 import yaml` → «Library stubs not installed for yaml (types-PyYAML)». `ignore_missing_imports` НЕ глушит known-stub либы; CI без types-PyYAML, локальный venv с ним. Фикс = `# type: ignore[import-untyped]` (как `05dbe6c` для evaluation; types-PyYAML в deps НЕ добавлять). Проверено воспроизведением: временный деинсталл стаба → gate Success 20. **Урок повторно: strict-промоушн модуля с любым yaml-импортом (даже ленивым внутри функции) → СРАЗУ `# type: ignore[import-untyped]`.**
>
> **Сделано:** `api/_shared.py`, `api/correlation.py`, `api/rate_limit.py`, `api/routers/*` → strict (22 mypy-ошибки → 0), всё type-only:
> - indirection-хелперы `_async_session() -> Any` / `_log_audit(**kwargs: Any) -> Any` (monkeypatch-проводка) в agent/admin_ops/admin_review/admin_kb/admin_evaluations/admin_experiments/feedback.
> - return-типы: `chat -> AskResponse`, `sso_login`/`sso_callback -> RedirectResponse`; `db: Any` в `_fetch_experiment_{live,staged}_bucket`.
> - `admin_experiments`: `value is not None and hasattr(...)` перед `.isoformat()` (union-attr; поведенчески идентично — None и так не имеет isoformat).
> - `analytics`: sort-key по `object`-значениям dict → `cast(int, item["count"])` (int(object) не overload!) + `str(item["category"])`.
> - `rate_limit.py`: аннотированы stub'ы ImportError-fallback'а (`Limiter`/`RateLimitExceeded # type: ignore[no-redef]`/`decorator`); `Callable` из `collections.abc` (ruff UP035).
>
> **🔴 Гоча/решение:** api-модули **транзитивно тянут `api.app`** (через ленивый `from api import app` в `api/_shared.py:32`; mypy следует импортам даже внутри функций) → полный FastAPI-граф таймаутит mypy. Поэтому проверяются **отдельной командой `--follow-imports=skip`** (как сам `api.app`), НЕ в основной gated-команде. Pyproject-override для них **без `warn_return_any`** (в отличие от api.app): SSO-эндпоинты возвращают Any-typed redirect от authlib — флаг ругался бы ложно. Guard `test_mypy_strict_scope_is_synced_across_gates` НЕ тронут — он пинит только основную команду (skip-команда вне его охвата, как и раньше для app).
>
> **Верификация:** scoped strict (CLI `--disallow-untyped-defs`) Success 19 files; **точная gate-команда (override-driven, без CLI-флагов) `mypy api/app.py api/_shared.py api/correlation.py api/rate_limit.py api/routers --follow-imports=skip` → Success 20 files**; `tests/test_precommit_config.py` 13 passed (guard зелёный); целевые роутер-тесты (analytics/conversation/agent/admin×2/rate_limit×2) **32 passed**; ruff All checks passed. Основная gated-команда не менялась (была Success 60).
> Изменены: pyproject + 3 гейта (ci.yml/local-gate.ps1/autopilot.ps1, skip-команда) + README + CHANGELOG + 11 api-файлов.
>
> **Остаток type-hardening:** последний крупный — `vectordb/` (тянет langchain/sentence-transformers, **риск памяти на Windows** — гнать осторожно/на Mac). `customs-clearance-fields` MISS — Kaggle. Обе — без явной просьбы не начинать.

## 2026-06-14 Update (adaptive-retrieval Track R / R1) — lightweight router classifier; Verify ПРЕВЫШЕН

> **START HERE (этот workstream).** Заход `/auto RAG_Support_Assistant продолжи` → «решай сам» → взят **Track R / R1** (Windows-friendly, обратимо, без нового индекса; F2 оставлен владельцу — нужен Mac). Сделан целиком, верифицирован.
>
> **Сделано:**
> - `evaluation/adaptive_retrieval/train_router_classifier.py` — TF-IDF (word 1-2 + char_wb 3-5) → `LinearSVC(class_weight=balanced)`, stratified 5-fold CV. Мишени: `query_class` (4-class), **`route`** (binary: shipped-решение router'а), `needs_factcard` (binary). + live-сравнение с LLM `classify_complexity` (prompt+parse скопированы verbatim из `agent/prompts.py`/`agent.graph`).
> - Live LLM-baseline: **ministral-3b** через `external-mistral` (это fast-tier classify-модель в mixed/external профилях; default `gracekelly-primary` юзает sonar-2 браузерный — 135 сабмитов тяжело/флапает на Windows, потому ministral). 135/135, 0 ошибок. Ключ Mistral из `D:\TXT`, в env, не печатался.
> - **РЕЗ (route, apples-to-apples):** lightweight **macro-F1 0.831** (acc 0.874) vs LLM **0.595** (acc 0.763), **Δ +0.237**. Cost: lightweight **0 токенов / 0.16 ms/query** vs LLM **~191 ток / 1091 ms (p95 1261)**. LLM сильно biased в hybrid (vector recall 0.21 — почти всё COMPLEX→hybrid). needs_factcard CV F1 0.871; 4-class F1 0.635 (`factual` слабый, n=18 — но на route simple/factual сливаются в vector, не вредит).
> - **Verify ПРЕВЫШЕН:** план просил «F1 не хуже + экономия» → дешёвый классификатор **строго лучше по обеим осям**.
>
> **🔴 Главный caveat (в отчёте):** `model_routing_enabled=false` + `retrieval_strategy=hybrid` в дефолте → `classify_complexity` short-circuit'ит на `unknown` БЕЗ вызова LLM, router всегда hybrid (D2). Т.е. **per-query LLM-стоимости в текущем проде НЕТ** — экономия ~191 ток/query *потенциальная*, реализуется только если включить роутинг. R1 = делает включение бесплатным.
>
> **Верификация:** офлайн CV-прогон + live ministral-прогон сошлись (выше); ruff All passed; mypy strict (evaluation в gated-scope) Success; docs-quality/precommit guard зелёные. Артефакт `r1_router_results.json` + отчёт `docs/operations/2026-06-14-adaptive-retrieval-r1.md` + план обновлён (R1 [x]).
>
> **Следующий шаг (НЕ начато, GATED):** **R2** = врезать классификатор перед `_select_retrieval_strategy` — но только после **Phase-5** офлайн-дельты D2 vs D2+router (headroom мал, D2 уже FULL 96/100, мисроутинг = тихая регрессия; route-gold *выведен* из query_class, не из измеренного retrieval-выигрыша). NO-SHIP — допустимый исход. **F2** (Track F, fact-card коллекция+ingest) — тяжёлый embed, **только Mac**, за владельцем. Решение что запускать — за владельцем.

## 2026-06-14 Update (adaptive-retrieval Track F / F1) — LLM fact-card экстрактор + Verify PASS на Mac; коммит+push

> **START HERE (этот workstream).** Заход по «запусти след шаг на мак» (после Phase 0 ниже). Сделан **Track F / F1** = LLM-экстрактор fact-cards + verify на 3 customs-доках. Тяжёлый/LLM-шаг гонялся **на Mac** (`deproject-mac` 192.168.1.133, SSH key-based; репо `~/RAG_Support_Assistant`, venv py3.11, ff-pull до origin; профиль `external-mistral`, ключ Mistral передан в `/tmp/mk.env` на прогон и удалён). Код написан/залинчен на Windows, прогон — на Mac.
>
> **Сделано:**
> - `ingestion/factcard_extractor.py` — `FactCard{topic,fields,required_docs,conditions,source}` (pydantic) + `extract_fact_cards(doc, source, llm)` через `SupportsInvoke` (контракт `invoke(prompt)->str`, как в graph). **mypy strict ✓ (ingestion.* в scope) + ruff ✓.**
> - `scripts/factcard_verify.py` — F1 verify-харнесс (extract + проверка сохранности полей).
> - **Verify PASS** на 3 customs-доках (clearance/broker/representative: 23/18/22 поля). **Карта clearance-дока содержит `declaration_number` + `customs_code`** — ровно kws остаточного MISS `customs-clearance-fields`, которые D2-реранк терял → fact-card механизм закрывает enumeration-дыру. Подтверждено grep'ом сохранённого `/tmp/f1_verify.out`.
> - **🔴 Гоча F1:** полный док (~17k симв) → runaway-вывод LLM → read-timeout (даже при 180s); короткий промпт = 1s (ключ/сеть ок). `ProviderBackedLLM.invoke(prompt)` НЕ прокидывает `max_tokens`/kwargs в `generate()`. Фикс F1: `max_chars=6000` (таблица «Обязательные поля» в первых ~5k симв → поля целы, ~13s). Полнодокументное покрытие late-секций — F2 (chunk-aware / bounded `max_tokens` через `generate()`).
>
> **Верификация:** ruff All checks passed; mypy `Success: no issues` (ingestion strict scope); verify RESULT PASS на Mac (external-mistral, 3/3 [OK]).
>
> **Следующий шаг (НЕ начато):** F2 — коллекция `<prefix>_factcards` + запись карт при ingest (тяжёлый embed → Mac). Затем F3 (`get_factcard_documents`), F4 (`_RETRIEVAL_STRATEGIES`+`Literal`+`make_retrieve_node` ветка). Track R/R1 (классификатор) — независим, можно Windows. По явному запросу.
>
> **Mac-прогон recipe (для F2 и любого LLM/тяжёлого шага этого workstream):** SSH `deproject-mac` (192.168.1.133, key-based, репо `~/RAG_Support_Assistant`, venv `.venv` py3.11). Перед прогоном: `cd ~/RAG_Support_Assistant && git pull --ff-only`. Ключ Mistral — по глобальной конвенции из `D:\TXT\Mistral_API.txt` (32-симв токен, отдельной строкой); передавать БЕЗ печати значения: `key=$(grep -oE '[A-Za-z0-9_-]{28,}' /d/TXT/Mistral_API.txt | head -1); printf 'export MISTRAL_API_KEY=%s\n' "$key" | ssh deproject-mac 'cat > /tmp/mk.env && chmod 600 /tmp/mk.env'`, затем на Mac `set -a && . /tmp/mk.env && set +a && OLLAMA_REQUEST_TIMEOUT_SEC=120 LLM_PROVIDER_PROFILE=external-mistral .venv/bin/python <script>`, после — `rm /tmp/mk.env`. Run-пример F1 также в docstring `scripts/factcard_verify.py`. `OLLAMA_REQUEST_TIMEOUT_SEC` (дефолт 60s) = таймаут и Mistral-вызова тоже.

## 2026-06-13 Update (adaptive-retrieval Phase 0) — разметка+baseline+ГЕЙТ; ГЕЙТ PASS обоими треками; PUSHED, CI зелёный (origin=`7c31904`+этот sync)

> **START HERE (этот workstream).** Заход по `/auto` «RAG_Support_Assistant — adaptive-retrieval: выполни Phase 0 из docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md». **Отдельный workstream, НЕ связан с mypy-strict-линией (cont.1-3 ниже).** Phase 0 закрыт целиком: T0.1 разметка + T0.2 baseline + ГЕЙТ. **PUSHED по «все решения за тобой, про коммиты и пуши тоже»: master FF `176335d→7c31904` (Phase 0) + plan-коммит `176335d` уехал заодно; origin синхронизирован. Основной CI run `27477349393` = success полностью** (type-check со свежим `evaluation.adaptive_retrieval` / unit×2 / integration×2 / lint / security / pre-commit / migrations / helm; regression-eval запустился — eval-path тронут). **Pages-deploy = failure pre-existing** (docs-site esbuild npm-audit через astro — cont.2/cont.3, вне scope, не моя регрессия). Отчёт: `docs/operations/2026-06-13-adaptive-retrieval-phase0.md`.
>
> **Сделано:**
> - **T0.1** — размечены 135 кейсов (aircargo 100 + curated 35): `query_class` (simple/factual/enumeration/multi-condition) + `needs_factcard`. Источник истины = `evaluation/adaptive_retrieval/build_phase0_labels.py` (ручные метки запинены, идемпотентно валидирует+печатает доли), материализация = `evaluation/adaptive_retrieval/phase0_labels.jsonl`. `needs_factcard`=TRUE только для перечня полей/документов/данных/доказательств/условий-эскалации (шаги/причины/действия → enumeration, но FALSE). **Доли: aircargo needs_factcard 44%** (enum 44/multi-cond 41/factual 9/simple 6); curated 6%; ALL 34%.
> - **T0.2** — mock-harness `scripts/regression_eval.py --mock-experiment-runtime --no-persist` валиден (135/135 офлайн), НО mock строит ответ из `answer_contains` → pass-rate ≠ retrieval (не путать!). Реальный D2 (Kaggle, задокументирован в arm-e/f отчётах): **FULL 96/PART 3/MISS 1**. Среди needs_factcard: **1 MISS** = `aircargo-customs-clearance-fields` (enumeration), ≤3 PART (D2-PART id'ы локально вычищены), ≥40 FULL.
> - **ГЕЙТ → PASS обоими треками (eligible).** Fact-Card: needs_factcard 44% ≫ 10% И MISS на needs_factcard-кейсе. Router: выраженный mixed-complexity. **Дисциплина:** headroom мал (D2 уже FULL 96/100) → любая постройка обязана пройти Phase-5 NO-SHIP; router = про cost (заменить per-query LLM-classify на TF-IDF+SVM/MiniLM), не recall. E/F (query-expansion) этот MISS не закрыли — Fact-Card другой механизм (отдельная коллекция, целая карта, реранк не усекает).
>
> **Верификация:** `python evaluation/adaptive_retrieval/build_phase0_labels.py` → 135 строк, доли как выше; mock-regression обоих датасетов exit 0, 100/35 кейсов pass, 0 infra-fail; ruff на новых .py чисто.
>
> **Следующий шаг (НЕ в scope Phase 0, отдельной сессией по явному запросу):** Track R/R1 (lightweight-классификатор на `phase0_labels.jsonl`) — лёгкий, **можно Windows**, ближайший автономный кандидат. Track F/F1 (LLM-экстрактор fact-cards, ingest) — **тяжёлый, только Mac**. Решение о запуске за владельцем — Phase 0 их НЕ запускает.
>
> **НЕ трогала:** 2 чужих untracked (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`). Транзитивные mock-отчёты `reports/regression/20260613T1933*` НЕ коммичены (throwaway).

## 2026-06-13 Update (cont.3, Type-hardening) — mypy strict-scope: evaluation.*; PUSHED, CI зелёный (origin=`05dbe6c`)

> **START HERE.** Заход по `/auto` «продолжай» (та же сессия, что cont.2). Продолжена линия расширения mypy strict-scope. **PUSHED — 2 коммита `a14c023` (evaluation strict, 16→0) + `05dbe6c` (CI-фикс yaml-стаба), origin синхронизирован, дерево чисто** (кроме 2 чужих untracked — не трогать). **CI run `27460976521` (на `05dbe6c`) = success полностью**, type-check зелёный. **mypy strict-scope теперь 14 целей** (+`evaluation.*`).
>
> **Сделано (`a14c023`):** `evaluation.*` (16 ошибок) → strict, всё type-only:
> - `online_evaluators.py` (4 union-attr): тернар `payload.get(k) if isinstance(payload.get(k), dict) else {}` не сужался (2 независимых `.get`) → `.get()` связан в локал до isinstance (`refusal`/`pii`/`metadata`/`tokens`).
> - `drift.py` (2 operator): `baseline in (None, 0)` → `baseline is None or baseline == 0` (эквивалентно, mypy narrow'ит float).
> - `evaluator_runner.py` (1 arg-type): `result` (3 ветки → `dict[str, object]`) → первое присваивание `result: dict[str, Any]`.
> - `simulate_model_benchmark.py` (3 arg-type+2 call-overload): `_generate_answer(profile: dict[str, object]→dict[str, Any])` (MODEL_PROFILES-значения гетерогенны; call-site совместим).
> - `benchmark_runner.py` (1 var-annotated): `context_docs_list: list[list[str]]`.
> - `rollback_watcher.py` (4 no-untyped-def): duck-typed async `session: Any`.
> - pyproject+3 гейта+guard+README+CHANGELOG расширены на `evaluation`.
>
> **🔴 ВАЖНАЯ ГОЧА (`05dbe6c`):** локальный gated-mypy = **Success 57 files**, но CI type-check УПАЛ: «Library stubs not installed for yaml (types-PyYAML)» в `online_evaluators.py`/`experiment_schema.py`. Причина: `ignore_missing_imports` НЕ глушит known-stub либы (yaml); **CI не ставит types-PyYAML, а локальный venv — ставит** → локально не воспроизводится. Фикс = `import yaml  # type: ignore[import-untyped]` (конвенция репо: так уже в `config/settings.py`/`agent/prompt_registry.py`/`llm/providers/runtime.py`; `types-PyYAML` в deps НЕ добавляют; `warn_unused_ignores` для evaluation off → ignore безвреден локально). **Урок: при strict-промоушене модуля с top-level `import yaml` (или иной known-stub либой) СРАЗУ ставить `# type: ignore[import-untyped]` — локальный mypy это не поймает.** tracing/ingestion не имели top-level yaml → не всплыло в cont.2.
>
> **Верификация:** gated strict-mypy **Success 57 files** (16→0); целевые тесты (online-evaluators/simulate/benchmark-runner/rollback-watcher/ragas/regression/nightly-eval/precommit-guard) **74 passed**; docs-guards 20; ruff clean; CI на `05dbe6c` зелёный.
>
> **Pages-deploy = failure pre-existing** (docs-site esbuild npm-audit через astro — см. cont.2; вне scope).
>
> **Остаток (НЕ блокеры):** `customs-clearance-fields` retrieval-MISS (Kaggle, не Windows); дальнейший strict — остались **`api/`** (кроме app — но осторожно: api.app спец-обработан `--follow-imports=skip` из-за тяжёлого графа/таймаута; промоушн всего `api.*` в основную gated-команду может вернуть эту проблему) и **`vectordb/`** (тянет langchain/sentence-transformers — память Windows, риск зависания; гнать gated-командой осторожно). Обе — тяжелее/рискованнее сделанных; крупный кусок на исходе бюджета НЕ начинать.
>
> **ОТДЕЛЬНЫЙ workstream (PLANNED, не начато, не связан с type-hardening):** adaptive-retrieval router + Fact-Card (SFR) lane — план в `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md` (research-обоснование `research_adaptive.md`). Безопасный первый шаг — Phase 0 (разметка eval + baseline, без нового индекса). Запуск отдельной сессией с явным указанием плана, НЕ через голое «продолжи».

## 2026-06-13 Update (cont.2, Type-hardening) — mypy strict-scope: tracing.* + ingestion.*; PUSHED, CI зелёный (origin=`a341b77`)

> **START HERE.** Заход по `/auto` «RAG_Support_Assistant продолжи». Бэклог Fable-hardening пуст; продолжена линия расширения mypy strict-scope (тот же прецедент, что SESSION 5). **PUSHED — 1 коммит `a341b77`, origin синхронизирован, дерево чисто** (кроме 2 чужих untracked `docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py` — не трогать). **Основной CI run `27460154092` = success полностью** (type-check со свежим scope / security-pip-audit / pre-commit / test-unit×2 / test-integration×2 / lint / migrations / helm; regression-eval skipped — PR-гейт). Все правки — типовые, поведение не менялось. **mypy strict-scope теперь 13 целей** (+`tracing.*`, `ingestion.*`).
>
> **Сделано (`a341b77`):** `tracing.*` (было 18 mypy-ошибок) + `ingestion.*` (3) → strict.
> - `tracing/otel.py`: 9 optional-opentelemetry-глобалов (`trace`/`OTLPSpanExporter`/`TracerProvider`/инструментаторы) стартуют `None`, перепривязываются в `_ensure_dependencies()` → аннотированы `Any` (та же суть, что `_NoopMetric`-union в monitoring; `ignore_missing_imports` всё равно делает реальные символы `Any`). + return/param-аннотации `_NoopSpan.__enter__/__exit__` (`Literal[False]` + `TracebackType`), `start_as_current_span`, `get_tracer`, `init_otel`.
> - `tracing/_base_trace.py`: return-типы генераторов `_get_connection` (`Iterator[sqlite3.Connection]`), `_batch` (`Iterator[list[str]]`).
> - `tracing/langfuse_trace.py`: `get_langfuse -> Any`; fallback `from langfuse.otel import Langfuse` → `# type: ignore[no-redef]` (тот же идиом, что fallback Document в `ingestion/pipeline.py`). **Гоча:** `[no-redef]` НЕ воспроизводится в изолированном `mypy tracing` (показался только в полной gated-команде с agent.graph в графе) — верифицировать ВСЕГДА полной gated-командой, не одним пакетом.
> - `ingestion/loader.py`: `changes: dict[str, list[str]]`. `ingestion/pipeline.py`: `build_vector_store: Callable[..., tuple[Any, list[Document]]]` (держит tenant-aware 5-арг ИЛИ legacy 4-арг, диспетчер через `inspect.signature`; аннотация на обоих присваиваниях — `ingest` и `add_document`).
> - pyproject overrides + 3 mypy-гейта (ci.yml/local-gate.ps1/autopilot.ps1) + guard `test_mypy_strict_scope_is_synced_across_gates` расширены на `tracing`/`ingestion`. README + CHANGELOG обновлены.
>
> **Верификация:** полная gated strict-mypy — **Success: no issues found in 46 source files** (21→0); целевые тесты (otel/langfuse/trace-retention/provider-cost/metrics/loader/categorizer/pipeline×2/precommit-guard) — **52 passed**; docs-guards 20 passed; ruff clean.
>
> **Pages-deploy `27460154087` = failure — pre-existing, НЕ моя регрессия:** docs-site `npm audit --audit-level=moderate` валится на esbuild high-severity (GHSA-gv7w-rqvm-qjhr / GHSA-g7r4-m6w7-qqqr, транзитивно через astro). Падал уже на `be85be3` (docs-only коммит до меня). Фикс = `npm audit fix --force` → astro breaking change на работающем docs-site — отдельная задача, вне scope type-hardening, без явной просьбы не трогать.
>
> **Остаток (НЕ блокеры):** `customs-clearance-fields` retrieval-MISS (Kaggle, не Windows); дальнейший strict — остались `api/` (кроме app), `evaluation/`, `vectordb/` (последний тянет тяжёлый langchain/sentence-transformers граф — память на Windows; гнать gated-командой осторожно).

## 2026-06-13 Update (Type-hardening + security) — mypy strict-scope расширен (db/tasks/utils/monitoring/channels) + pypdf-CVE; PUSHED, CI зелёный (origin=`46991dc`)

> **START HERE.** Заход по «доработай проект, решай сам» → «продолжи». Бэклог Fable-hardening был пуст; взято направление расширения mypy strict-scope (+ по ходу закрыта свежая pypdf-CVE). **PUSHED — 3 коммита `cbba12f..46991dc`, origin синхронизирован, дерево чисто, CI run `27458721233` success полностью** (type-check/security/pre-commit/test-unit×2/test-integration×2/lint/migrations/helm; regression-eval skipped PR-гейт). Все правки кода — типовые/security (поведение не менялось). mypy strict-scope теперь **11 целей**: auth, db.\*, llm.providers.\*, config.settings, 5×agent, api.app, tasks.\*, utils.\*, monitoring.\*, channels.\*. Чужие untracked `docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py` — не трогать.
>
> **3 коммита:** `310f303` strict→db.\*/tasks.\*/utils.\* + governance guard · `fef03ad` security pypdf 6.10.2→6.13.2 (CVE-2026-48155/48156) · `46991dc` strict→monitoring.\*/channels.\* (type-only `_NoopMetric` решение). Детали по каждому — ниже.
>
> **Сделано:**
> 1. **mypy strict-scope расширен** на `db.*`, `tasks.*`, `utils.*` (был только `db.models`). `pyproject.toml` overrides. Правки кода = только аннотации:
>    - `utils/retry.py`, `utils/circuit_breaker.py`: `*args: Any, **kwargs: Any` у proxy-декораторов.
>    - `db/crypto.py`: `encrypt`/`decrypt`/`EncryptedText.{bind,column}_expression` → `ColumnElement[Any]` (override-совместимо с `TypeDecorator`).
>    - `db/audit.py`: `purge_old_audit` rowcount через `getattr` (base `Result` не объявляет `rowcount`; DELETE даёт `CursorResult`).
>    - `tasks/ingest_task.py`: `ingest_document(self: Task, …)` + `from celery import Task`.
> 2. **Governance guard** `test_mypy_strict_scope_is_synced_across_gates` (`tests/test_precommit_config.py`): запирает идентичность strict-путей mypy в 3 точках (ci.yml / local-gate.ps1 / autopilot.ps1) + пинит модули. Все 3 команды обновлены синхронно (`db/models.py db/engine.py` → `db`, +`tasks utils`).
>
> **Верификация:** полная gated strict-команда (новый scope) — **Success: no issues found in 30 source files, exit 0**; затронутые модули (circuit_breaker/retry/audit/encryption/ingest_task/pii/background_tasks/precommit) — **66 passed / 3 skipped**; ruff clean на изменённых файлах. `api.app` проверяется отдельной командой (`--follow-imports=skip`) — «unused section api.app» в основной команде ожидаем.
>
> **Запушено `cbba12f..310f303` (type-hardening) — CI частично красный по diff-независимой причине, починено вторым коммитом:** на `310f303` CI run `27457678239` — зелёные type-check/test-unit×2/test-integration×2/lint/helm/migrations, но **security + pre-commit упали на свежей pypdf-CVE** (CVE-2026-48155/48156 vs `pypdf 6.10.2`, fix 6.12.0; advisory появился ПОСЛЕ прошлого зелёного CI — НЕ связан с type-правками). Фикс: `pypdf` → **6.13.2** в `requirements.lock` + `requirements-dev.lock` (uv `--upgrade-package pypdf --generate-hashes`, diff только pypdf, без транзитивных) + floor `pypdf>=6.12.0` в `requirements.txt`. `--ignore-vuln` НЕ добавлял (fix доступен → нарушило бы governance-политику). Локальная верификация: pip-audit «No known vulnerabilities found, 2 ignored»; loader/ingest/governance **30 passed**.
>
> **Продолжение по «продолжи» (3-й коммит, monitoring/channels):** взято отложенное направление — `monitoring.*` (48 ошибок) + `channels.*` (8) доведены до strict. `_NoopMetric` optional-dependency fallback решён **type-only, без изменения рантайма**: union (`Counter|_NoopMetric` и т.п.) объявлен один раз в `TYPE_CHECKING`-блоке на модуль (`monitoring/prometheus.py`, `channels/email_channel.py`) — обе ветки import-present/absent проходят. Плюс channels: `payload.decode` narrow до bytes, imap `msg_data[0]` narrow до tuple, telegram `assert _session_class is not None`. pyproject + 3 гейта + guard расширены (strict-scope = 11 целей). Верификация: monitoring Success 2 files, channels Success 4 files, ruff+guard passed. (Гоча: mypy `--no-incremental` на channels тянет транзитивный граф `agent.graph→langchain`, пик ~2.2GB — близко к Windows-порогу, но завершается.)
>
> **Остаток (НЕ блокеры):** Retrieval-MISS `customs-clearance-fields` — без явной просьбы НЕ начинать (нужен Kaggle-runtime, не на Windows). Возможное будущее: расширить strict ещё (api/ кроме app, evaluation/, ingestion/, tracing/, vectordb/) — крупный churn.

## 2026-06-12 Update (Fable hardening, сессия 4) — F-14-хвост закрыт + PUSHED; CI зелёный (origin=`aacaa18`)

> **START HERE.** Бэклог Fable-hardening пуст. Origin синхронизирован — **PUSHED по явному «все решения принимаешь ты»**: `51628e2..aacaa18` (26 коммитов). CI run `27413770413` **success полностью** (pre-commit/security/test-unit×2/test-integration×2/lint/type-check/migrations/helm; regression-eval skipped — PR-гейт). Дерево чисто, кроме 2 чужих untracked (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`) — не трогать.
>
> **Сделано в сессии 4:**
> 1. **F-14 Issue 2 (`0a38756`)**: `_base_manager._project_root()` возвращал папку пакета → `_data_dir()` писал «невидимый» Chroma/Qdrant-стор в `vectordb/data/vectordb/`, отдельный от продакшен-пути `settings.vectordb_chroma_dir`. Фикс → корень репо (как `config.settings.PROJECT_ROOT`/`mock_inbox`), + guard-тест `test_data_dir_resolves_under_repo_root_not_package_internal`.
> 2. **F-14 Issue 1 (warm-cache по модели) — НЕ менялся осознанно**: закреплён тестами `test_base_manager.py:87/:110`, правдоподобно намеренный (тяжёлые модели, один резидентный объект). Рекомендация — `next-session-fable-hardening.md` «SESSION 4».
> 3. **CVE-2025-3000 (torch) ignore** (`97fdd6e` pre-commit + `aacaa18` CI security-job + оба ps1-гейта): свежий advisory против torch 2.11.0 (local memory corruption в `torch.jit.script`, fix-версии нет) валил pip-audit на push. torch — только локальный inference sentence-transformers, `torch.jit.script` недостижим для недоверенного ввода. Снять ignore, когда выйдет upstream-фикс. Все 4 точки pip-audit (pre-commit/ci.yml/local-gate.ps1/autopilot.ps1) в синхроне.
>
> **Харденинг к 9.8 (после push):**
> 4. **Reranker-гоча устранена в корне** (`c8d9ea7`): autouse-фикстура `_disable_real_reranker_download` в `tests/conftest.py` дефолтит cross-encoder OFF на тестах. Виновник — `test_per_tenant_vectorstore::test_two_tenants_get_different_retrievers` (тянул 2.3GB `bge-reranker-v2-m3` с HF). **Гоча cont.14 БОЛЬШЕ НЕ В СИЛЕ** — полный suite гонять без `RAG_RERANKER_MODEL=""`. Де-флак CI HF-429. Полный unit-suite **862 passed / 4 skipped БЕЗ env-workaround**.
> 5. **CVE-suppression governance** (`b785a07`): guard-тест `test_pip_audit_ignore_set_is_synced_and_minimal` запирает pip-audit `--ignore-vuln` ровно на 3 обоснованные CVE во всех 4 точках (pre-commit/ci.yml/local-gate.ps1/autopilot.ps1) — запрет тихих suppression + защита от рассинхрона. Reachability проверена: `torch.jit.script` не используется, Chroma — embedded `PersistentClient`.
> 6. **Gap-sweep** (`76cf488`, `bd85893`): системный скан пробелов. Закрыто: `ingestion/loader.py` print→`logging`; тест email-webhook httpx `content=` вместо deprecated `data=`. Подтверждено чистым: ruff, mypy gated-scope, нет TODO/FIXME/bare-except, skipped-тесты легитимны. LangChain `Ollama`-deprecation — **не пробел** (артефакт неполного локального env; `langchain-ollama` в requirements.txt+lock, ставится в CI).
>
> **Следующий заход:** открытых пунктов Fable-hardening нет. Единственный остаточный качественный пункт — retrieval-MISS `customs-clearance-fields` (требует staged Kaggle-runtime + новый research-подход; оба прежних рычага E/F отвергнуты данными — НЕ начинать без явной просьбы). Возможное будущее харденинг-направление (не пробел): расширить mypy strict-scope на остальные модули (крупный churn).

Верификация сессии 4: `test_base_manager.py` 17 passed (incl. guard); `test_module_layout`/`test_manager_semantic_chunking`/`test_per_tenant_vectorstore` 17 passed; `test_precommit_config.py` 12 passed (incl. ignore-lock guard); **полный unit-suite 862 passed / 4 skipped БЕЗ env-workaround** (CI-команда); pip-audit hook локально Passed; ruff + py_compile clean; **CI на origin зелёный полностью**.

## 2026-06-11 Update (Fable hardening, сессия 3) — fable_com.md ЗАКРЫТ ПОЛНОСТЬЮ: гигиен-спринт F-13/F-15/F-16 + F-4 (все 4 ловушки); push GATED

> **START HERE.** Аудит `fable_com.md` (18 findings) закрыт целиком — открытых пунктов плана §5 НЕТ. Эта сессия: гигиен-спринт §5 п.8 (F-13/F-15/F-16), сопутствующий фикс F-3-регрессии и F-4 по спеке. Push НЕ делался (GATED, master ahead origin на 21 коммит — точный счёт `git log --oneline origin/master..`).
>
> **Актуальный детальный handoff — `next-session-fable-hardening.md` (блок «SESSION 3» сверху).** Stale-файлы прежних линий теперь в `docs/sessions/` и `docs/audits/` — при онбординге игнорировать.
>
> **Следующий заход:** бэклог Fable-hardening пуст. Кандидаты (НЕ блокеры): push 21 коммита (GATED, спрашивать явно); F-14-остаток (`_base_manager._project_root` двойник пути + warm-cache без ключа по модели) — LOW, по желанию.

1. **F-13 (`ebf50a6`)**: все ~44 import-time `os.getenv`-поля Settings → `default_factory`; ast-guard `test_settings_env_fields_use_default_factory` + поведенческий тест setenv-после-импорта. Settings-suites **79 passed**, mypy/ruff clean. Гоча cont.15 (monkeypatch.setenv бессилен) больше не воспроизводится.
2. **F-15 (`1e0384f`)**: per-request `inspect.signature` убран из `/api/ask`, `/ask/stream`, `_get_or_create_session`, rebuild-путей `api/app.py`. Контракты зафиксированы: `_get_or_create_session(session_id, tenant_id)` await напрямую; `session.ask` всегда получает `trace_id/tenant_id/confirm/user_id/session_id`; `get_retriever`/`build_vector_store` — с `tenant_id`. 18 файлов тестов приведены к реальным сигнатурам (async-фейки + `**kwargs`).
3. **Фикс F-3-регрессии (`6326fdc`)**: стрим-self-eval ставил `quality_source="llm"` даже когда LLM не вернул число и скор упал на эвристику — llm-провенанс поднимал порог route с 70 до `quality_threshold` → route=human, suggested_questions пропадали (ловил integration test, фейл был и ДО F-15 — проверено stash-прогоном). Теперь "llm" только при реально распарсенном числе.
4. **F-16 (`09a81ce`)**: 8 audit-файлов → `docs/audits/`; stale session-файлы → `docs/sessions/`; история AGENT_STATE 2026-06-02..06-05 (cont.2–16) → `docs/sessions/agent-state-archive-2026-06-02-to-06-05.md` (1184→659 строк); PNG-скриншоты и `.coverage` удалены; все ссылки/pre-commit regex/autopilot allowed-paths/docs-guard тесты обновлены (40 passed).
5. **F-4 (`63a3ee4`)**: кэш provider runtime (ключ = resolved registry path + profile + mtime providers.yml) + кэш compiled graph (id-ключи, пришпиленные strong-ссылками, LRU 16). Все 4 ловушки спеки закрыты: `last_response` → `threading.local`; **`_enforce_daily_cost_limit` гоняется на КАЖДЫЙ вызов, включая cache hit** (тест-пин); id-reuse исключён strong-refs; провайдеры аудированы (per-call HTTP). `tests/test_provider_runtime_cache.py` **6/6**; autouse-фикстура conftest чистит оба кэша между тестами. Acceptance: provider/routing/online-eval/graph/failover/streaming **82 + 25 passed**.
6. **Push — GATED, спрашивать явно.** Полный suite на этой машине только с `RAG_RERANKER_MODEL=""` (гоча cont.14 в силе).

## 2026-06-11 Update (Fable hardening, сессия 2) — аудит fable_com.md разрешён §5 пп.1-7 + гигиена #11; F-4 → спека; push GATED

> Аудит `fable_com.md` (18 findings) разрешён: §5 пп.1-6 (батч) + п.7 (multi-worker) сделаны и закоммичены локально; F-4 (п.5→оптимизация) вынесен в спеку Codex. Открытый остаток — гигиен-спринт §5 п.8 (F-13/F-15/F-16) — закрыт сессией 3 выше. Push НЕ делался (GATED).

**master ahead of origin на ~12 коммитов (`2ee78a8..` + предыдущий `55f1a42`; НЕ запушено — точный HEAD см. `git log --oneline`). Working tree чисто, кроме чужих untracked (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`) — не трогать.**

1. **Верификация перед коммитом** (свежая сессия, evidence-before-commit): §2 стрим/кэш/analytics/graph **49 passed** (прошлый 47/1 — фейл был намеренный pin-тест, после отката чисто), F-2+routing **13 passed**, ruff clean.
2. **Закоммичен готовый батч** — 7 локальных коммитов на `master` (нарезка файлово-когерентная, т.к. `git add -p` интерактивен и недоступен): `2ee78a8` metrics · `544c3fc` F-2 restore BM25 chunks · `5f9194f` F-1a/F-11 event-loop unblock · `defe216` F-9a/F-12 graph+settings · `f8cc015` F-3/F-8/F-7/F-17/F-6 streaming/cache/persist · `59df7c9` **F-5/F-18**.
3. **F-5/F-18 ДОДЕЛАНЫ** (была in-flight): `utils/event_loop.py` подключён — loop регистрируется в `api/app.py` `_lifespan` (старт/finally), `run_qa_pipeline` шлёт персист online-eval через `run_coroutine_threadsafe` на main loop без per-request `engine.dispose()`; sync-скрипты → legacy `asyncio.run`+dispose. F-18: timeout из `online_evaluators_timeout_sec`, counter `rag_online_evaluators_dropped_total{reason=timeout|error}`. Тест threadsafe-пути добавлен — online-eval **19 passed**, graph/routing/conversation **17 passed**, импорт `api.app`/`agent.graph` OK.
4. **Docs + гигиена закрыты** (после батча): `1ed8efc` — README/`.env.example`/`docs/CHANGELOG.md` для 6 новых переменных (+`STREAMING_QUALITY_EVAL` rollback, [Fable-Hardening] блок); `84de8e2` — мёртвый корневой `cache.py` (затенён пакетом `cache/`) + тест → `archive-legacy/` (F-14); `.gitignore` уже содержал temp/coverage; 76× `pytest-cache-files-*` + 7× `.pytest-tmp-*` удалены.
5. **Multi-worker инвариант ЗАКРЫТ** (`d805292`): дефолты выровнены на 1 worker / 1 replica (`Dockerfile --workers 1`, helm `replicaCount:1` + autoscaling off), claim в `_base_trace.py` починен, startup-warning на `WEB_CONCURRENCY>1`, README «Deployment topology». Прошлый дефолт = 2 worker × 2–8 replica (ломал confirm-actions/сессии).
6. **F-4 де-скоуплено → спека `codex-tasks/task-F4-cache-runtime-graph.md`**: при разборе найдена 4-я ловушка (помимо `last_response`) — `_enforce_daily_cost_limit` per-request, наивный кэш runtime молча отключит `DAILY_COST_LIMIT_USD` (money-safety). Оптимизация, не баг; concurrency+money-sensitive → Codex или отдельный аккуратный заход. НЕ шипить вслепую.
7. **Push — GATED, спрашивать явно.** Полный suite на этой машине только с `RAG_RERANKER_MODEL=""` (cont.14).

## 2026-06-11 Update (Fable hardening, сессия 1) — аудит fable_com.md + 11 из 18 findings в коде; ДЕРЕВО DIRTY НАМЕРЕННО, БЕЗ КОММИТОВ

**HEAD = `55f1a42` (master, origin синхронизирован). Working tree: 11 M + наши новые `fable_com.md`, `tests/test_chunks_restore.py`, `utils/event_loop.py`, `next-session-fable-hardening.md` — НЕ закоммичено (остался хвост: ruff + доделка F-5; нарезка коммитов в handoff §5). Чужие untracked параллельной сессии (`docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`) — не трогать.**

1. **Аудит `fable_com.md`** (18 findings, оценка 8.7/10): топ-3 — BM25/parent-expansion не переживают рестарт (F-2), upload блокирует event loop на полный re-embed (F-1), стрим обходит Self-RAG с синтетическим quality 70/40 (F-3). Сверка прошлых аудитов: F1/F2/H2/R1/R6/R7 подтверждены закрытыми.
2. **Реализовано в коде** (детали и таблица верификации — `next-session-fable-hardening.md` §1): F-2 (restore chunks из Chroma + `chunk_index`-штамп + gauge `rag_retriever_bm25_enabled` — **тесты 6/6** ✅), F-1a (upload → to_thread), F-10 (см. ниже — разрешён как «намеренно»), F-12, F-8, F-7, F-17 (контракт: `/api/ask` теперь всегда отдаёт `cached: bool`), F-6, F-9a (`quality_source` llm/fixed/heuristic в state+метрика), F-3 (стрим: семафор+дедлайн+**дешёвая self-eval parity**, default ON, откат `STREAMING_QUALITY_EVAL=false`), F-11. +4 новые prometheus-метрики, +6 settings-полей.
3. **Верификация СДЕЛАНА в конце сессии**: пакет стрим/кэш/analytics/graph — **47 passed / 1 failed**; единственный фейл вскрыл, что **F-10 был НАМЕРЕННЫМ** (пин-тест `test_build_support_graph_uses_fast_llm_for_evaluate_node`, коммит `7e266af`: strong в gracekelly-primary = ~60s orchestrate-вызов). Правка evaluate→strong **откатана** (оставлено `(llm_fast, llm_fast)` + комментарий в `build_support_graph`; suggest→fast оставлен), после отката **15 passed** (`test_magic_numbers_settings` + `test_model_routing`). Резолюция вписана в `fable_com.md`. Гоча: `tests/test_analytics_dashboard.py` НЕ существует (правильно `tests/test_analytics.py`) — из-за опечатки первый прогон молча не запустился («no tests ran», `| tail` маскирует exit code).
4. **In flight**: F-5/F-18 — `utils/event_loop.py` создан, но НЕ подключён (lifespan + переписать online-eval блок в `run_qa_pipeline` на `run_coroutine_threadsafe`, убрать per-request `engine.dispose()`); пошаговый рецепт в §3. Не начато: F-4 (кэш runtime/graph — ловушка `last_response`, см. §4), гигиена, README env-таблица.
5. **Гочи**: `manager.get_retriever(embeddings=None)` в тестах тянет реальный BGE-M3 — стабовать `manager.get_embeddings` (fixture в `tests/test_chunks_restore.py`); зависший python — `taskkill //F //FI "IMAGENAME eq python.exe"`; full suite только с `RAG_RERANKER_MODEL=""` (cont.14 в силе).

**План и нарезка коммитов: `next-session-fable-hardening.md`. Push — GATED, спрашивать явно.**

## 2026-06-06 Update (cont. 18 ЗАКРЫТ) — плечо F NO-SHIP (95 < 96), цикл query-expansion ЗАКРЫТ; production = D2

**HEAD = этот handoff-коммит (master). Origin = `eeb7cd0` — unpushed: `06b9d84`+`62a54cd`+`c8cd806`+`d9d205f` (утренняя половина) + отчёт F + этот. Push GATED.**

Первая половина сессии (до kernel): graph-условие в коде (`9c77590`, запушен) + probe share 0.296 (`c8cd806`) + chunk-пин (`eeb7cd0`) + notebook (`62a54cd`) + арм F код (`06b9d84`) + kernel v7 запущен — детали в cont.18-IN-FLIGHT истории git (blob `d9d205f`).

Вторая половина (продолжение после обрыва, шаги 1-5 выполнены):

1. **Kernel v7 чистый** (`[kaggle-phase2-F] DONE`, 6h05m): скачан в `.tmp/kaggle_phase2/out_F/` (4 json + log, байты сошлись с логом 1-в-1).
2. **Expand обоих плеч** (`--window 2 --max-chars 3600`; гоча: короткого `-w` у скрипта НЕТ): **регенерированный D2 = FULL 96/PART 3/MISS 1, остаточный MISS тот же — baseline воспроизведён 1-в-1 (cont.15 валиден)**; F-pre 92 → **F 95/100 FULL** (PART 3, MISS 2).
3. **Матрица D2→F (все 100): 1 gain / 2 регрессии, нетто −1 FULL (96→95).** Gain `customs-special-cargo-manual-check`; регрессии `customs-broker-escalation` FULL→MISS (rerank-anchor shift: co-occur В пуле r20, original-реранк выбирает якоря без kw-соседей) + `waybill-escalation-events` FULL→PART (pool-выпадение — детерминированное наследство E-пулов, было предсказано). Gain E (`customs-clearance-fields`) НЕ сохранился: его закрывал expanded-РЕРАНК, не пулы → MISS опять.
4. **R7-judge SKIPPED обоснованно**: конъюнктивный критерий упал на ноге 1 (FULL 95 < 96), дельта 3 кейса внутри полосы шума судьи (гоча cont.15 re-judge C) — 300 вызовов сигнала не добавят.
5. **РЕШЕНИЕ: NO-SHIP** split-query параметра retriever'а. F-pre 92 > D2-pre 87 — split-query реально лучше БЕЗ экспансии, но parent-expansion (default ON) поглощает выигрыш (D2 +9 экспансией, F +3). **Цикл probe → E → F закрыт; production-стек = D2** (structural + parent-expansion w=2/3600). Отчёт: `docs/operations/2026-06-06-arm-f-split-query-results.md` (+ итог-блок в E-отчёте).

**ДОПОЛНЕНО той же сессией (после push, по явному «продолжи» Юли). АКТУАЛЬНОЕ СОСТОЯНИЕ: origin = `51628e2` (CI ЗЕЛЁНЫЙ), unpushed только этот addendum-коммит.**
- **PUSHED `eeb7cd0..3576410` + CI-fix `51628e2`** (6 коммитов суммарно). Первый CI-прогон упал на pre-commit `end-of-file-fixer`: notebook `62a54cd` был без trailing newline (единственный фейл, остальные 9 джобов зелёные) — фикс `51628e2`, второй прогон **success полностью**. Docs-deploy зелёный с первого раза. Гоча сети: github.com с этой машины флапает (DNS-фейл + wsarecv reset) — лечится простым retry через 10-20s.
- **`.tmp/kaggle_phase2/` вычищен (56MB**, включая v7-staging и недочищенный out_E) — датасет v7 + kernel v7 на Kaggle private живут, кандидаты в dataset (урок cont.17), expand детерминирован.

**Кандидаты следующей сессии (НЕ блокеры):**
- `customs-clearance-fields` — единственный остаточный MISS; оба известных рычага (E, F) отвергнуты данными. Новых заходов НЕ изобретать без явного запроса.
- В working tree чужие untracked `docs/architecture-data-flow.html` + `scripts/check_architecture_diagram.py` (параллельная сессия) — не трогать, не коммитить.

## 2026-06-06 Update (cont. 17) — плечо E ЗАКРЫТО: NO-SHIP (1 gain / 8 регрессий vs D2), диагноз rerank-демоции записан

**HEAD = этот handoff-коммит (master). Origin = `eaf8dd9` — unpushed: `584ecae`+`26587ab` (cont.16 хвост) + docs этой сессии + этот. Push GATED.**

Шаги 3-5 плана плеча E (`docs/operations/2026-06-05-query-expansion-probe.md`) выполнены, цикл закрыт:

1. **Kernel v6 чистый** (`[kaggle-phase2-E] DONE`, 5.7h CPU): скачан в `.tmp/kaggle_phase2/out_E/` (candidates 8MB + pool 4MB + log). Гоча: первый `kaggle kernels output` оборвался `IncompleteRead` 2.5MB/8MB и оставил **пустой** `ab_candidates_phase2_E.json` — удалить перед retry (retry прошёл). Контракт judge в данных верен: `expanded_query` у 100/100, `query` = оригинал.
2. **Expand** (`--stage expand --label E -w 2 --max-chars 3600`): E-pre 79 → **E 89/100 FULL** (PART 6, MISS 5); summary в `out_E/ab_phase2_E_summary.md`.
3. **Матрица D2→E (пересчёт `_kw_status` по обоим файлам): 1 gain / 8 регрессий, нетто −7 FULL (96→89).** Gain — ровно целевой `customs-clearance-fields` (последний MISS D2 закрыт: query-side гэп мостится). Регрессии: 5 FULL→MISS + 3 FULL→PART.
4. **Диагноз по прерank-пулам E: 7/8 регрессий — rerank-демоция** (kw-чанки В пуле на RRF rank 1-9, cross-encoder против длинного расширенного запроса, медиана 574 chars, не поднимает в top-5; 1/8 — pool-выпадение). Риск из «Ограничений пробы» реализовался.
5. **R7-judge** (mistral-small, 300 вызовов, `20260605T214926Z-e728353a`): E recall **0.920** prec **0.509** rel 0.833 faith 0.766 (zeros 19) vs D2 0.975/0.576/0.895/0.864 (z7) — проигрыш по всем и в agg, и в mean-без-нулей. **Перекрёстная валидация: judge recall-zeros E = ровно те же 5 FULL→MISS кейсов kw-матрицы, 1-в-1** — два независимых замера сошлись.
6. **РЕШЕНИЕ: NO-SHIP** — field-aware промпт в `_build_hyde_prompt` не внедряем. D2-стек (structural + parent-expansion w=2/3600, оба default ON) остаётся production; остаточный MISS один (`customs-clearance-fields`). Отчёт: `docs/operations/2026-06-06-arm-e-field-hyde-results.md` (+ итог в план-доке пробы).

**ДОПОЛНЕНО той же сессией (после push, по явному «продолжай» Юли). АКТУАЛЬНОЕ СОСТОЯНИЕ: origin = `9d80814` (CI ЗЕЛЁНЫЙ), unpushed только этот addendum-коммит.**
- **PUSHED `eaf8dd9..9d80814`** (5 коммитов). CI: первый прогон — `test-unit (3.11)` упал на HF `429 Too Many Requests` (скачивание `bge-reranker-v2-m3` per-tenant тестами — ровно гоча cont.15, transient), `gh run rerun --failed` → **зелёный 11/11**. Docs-deploy зелёный с первого раза.
- **`.tmp/kaggle_phase2/` вычищен (68MB)** — датасет v4/kernel v6 на Kaggle private живут, E-артефакты воспроизводимы (kernel output скачивается повторно, expand детерминирован); judge-репорты в `reports/ragas/` не тронуты.

**Кандидаты следующей сессии (НЕ блокеры):**
- Арм F split-query (expanded для пулов, оригинал для реранкера — обоснование в отчёте) — **только по явному запросу Юли**, новый параметр retriever'а.
- Colab-ячейки Phase 2 в notebook устарели (гоча cont.14) — при следующем заходе в notebook.

## Архив истории сессий

Секции 2026-06-02..2026-06-05 (cont.2–16: ruff-слайсы F6, R7-judge baseline,
Kaggle Phase 1/2, parent-expansion, query-expansion probe) вынесены в
`docs/sessions/agent-state-archive-2026-06-02-to-06-05.md` (F-16, 2026-06-11).

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch source: `master` tracks `origin/master`; current history includes the
  2026-05-30 Codex audit remediation series after the weekly-report fixes.
- Snapshot baseline date: 2026-05-30 (Europe/Bucharest).
- Baseline HEAD before the 2026-05-30 audit/remediation run:
  `4d60479` (`ci: clarify weekly report delivery workflow`).
- Baseline file count: 698 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Baseline generated bundle/artifact size: 0 bytes for searched bundle-like
  artifacts outside ignored dependency/cache directories.
- Git status at the 2026-05-30 durable-state refresh was clean, with local
  remediation commits ahead of the initial `origin/master` baseline.
- Origin sync at audit start: `origin/master` was at `4d60479`.

## 2026-05-31 Project Closure Update

- At project closure, `master` was synced with `origin/master` at pushed commit
  `c1bccc9`; GitHub CI run `26699926418` and Pages deploy run `26699926414`
  completed successfully.
- Final follow-up closure on 2026-06-01 synced `master` and `origin/master` at
  `315603e` after pushing the GraceKelly live revalidation note and two CI
  fixes. `304273a` restored lazy vector backend imports and made Ollama wrapper
  construction compatible with the locked LangChain surface; `315603e` also
  lazy-loads `RecursiveCharacterTextSplitter` so importing
  `vectordb._base_manager` no longer pulls `sentence_transformers` in CI. Final
  GitHub CI run `26725747231` passed on `315603e`. The relevant Pages run on
  the preceding docs-affecting head, `26725616231`, also passed; the final
  `315603e` vector-only change did not trigger the docs-site path filter.
- GraceKelly runtime check on `http://127.0.0.1:8011`: `/healthz/ready`
  returned 200, `/api/v1/models` returned 10 models, and a minimal
  `claude-sonnet-4-6` orchestrate request returned `OK`.
- Mistral credential/provider check: `MISTRAL_API_KEY` was present and
  `GET https://api.mistral.ai/v1/models` returned 200 with 74 models. The key
  value was not printed or written to tracked files.
- Windows-safe RAG acceptance ran with `LLM_PROVIDER_PROFILE=gracekelly-mixed`,
  `RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2`, vector-only retrieval,
  `REQUEST_TIMEOUT_SEC=120`, and collection prefix `rag_closure_20260531`.
  `/api/ask` returned 200 in `72491 ms`, trace
  `578325c0c7be405d9ec5aacb5c4f6927`, with providers `mistral` and
  `gracekelly` and models `ministral-3b-latest` and `claude-sonnet-4-6`.
  The RAG process stayed under the local resource cap at about `594.6 MB`.
- A separate GraceKelly defect was found and fixed locally in `D:\GraceKelly`:
  live `Sonar 2` was incorrectly marked reasoning-capable, so the browser
  adapter treated a missing Thinking toggle as fatal. Local commit
  `311fa6a fix(browser): treat Sonar 2 as non-reasoning` updates the model
  registry and tests. Verification: the new red tests failed before the fix,
  then `tests/test_model_registry.py`, `tests/test_models.py`,
  `tests/test_models_extra.py`, `tests/test_browser_adapter.py`, and
  `tests/test_browser_selectors.py` passed (`143 passed`), Ruff passed, and
  live `sonar-2` orchestrate returned 200 with `status=completed` in
  `14070 ms`.
- Follow-up live work on 2026-05-31 found a second GraceKelly browser-adapter
  defect: Perplexity's Computer onboarding card was being extracted as model
  output, could block prompt submission, and response extraction could return a
  partial first draft before the DOM text stabilized. Local GraceKelly commits
  `fd6c51e fix: reject perplexity computer onboarding output` and
  `c35c626 fix: stabilize perplexity browser submissions` add regression
  coverage and the browser fixes. Verification in `D:\GraceKelly`:
  `tests/test_playwright_driver.py`, `tests/test_browser_adapter.py`, and
  `tests/test_browser_selectors.py` passed together (`108 passed`), Ruff
  passed for the changed browser driver/test files, direct
  `claude-sonnet-4-6` browser smoke returned a full warranty answer, and the
  RAG `/api/ask` smoke returned 200 in `53861 ms` with trace
  `580a0c0c336940ddb0a5997662666f4e`, quality `95`, and `warranty.md`
  citations using collection prefix `rag_live_20260531t0756`.
- Larger R7/RAGAS/local full-corpus jobs were not started on this Windows host
  because project rules forbid local processes expected to exceed 1 GiB RAM.
  They are not required for today's GraceKelly/Mistral runtime closure; if the
  acceptance target changes to full RAGAS, run it on Colab/Mac/remote.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

This section is a historical verification ledger. Do not treat branch names,
HEAD hashes, file counts, or ahead/behind counts below as current state; rerun
`git status --short --branch`, `git rev-parse HEAD`, or the named gate command
when current evidence is needed.

- Historical `git status --short --branch`: clean on
  `post-merge-handoff...origin/master` before that `AGENT_STATE.md` refresh.
- Historical `git rev-parse HEAD`: `415d4c88baf52d4696987d5e2546dd7ce3ce576c`.
- Historical `git ls-files | Measure-Object`: 697 tracked files.
- `python -c "import json, pathlib; json.loads(pathlib.Path(r'notebooks\\rag_support_colab_remote_benchmark.ipynb').read_text(encoding='utf-8')); print('notebook json ok')"`: passed before commit `a461fba`.
- `git diff --check`: passed before commit `a461fba`.
- `git fetch origin master`: updated `origin/master` to `415d4c8` after PR #1 merge.
- `Get-Command pi`: available.
- `Get-Command codex`: available.
- `pi --version`: `0.72.1`.
- `codex --version`: `codex-cli 0.128.0`.
- `python -m pytest tests/test_agent_endpoints.py -q -p no:schemathesis -p no:cacheprovider`:
  9 passed, 1 warning after the Agent UI text-rendering XSS fix.
- `node -e "... new Function(agent inline script) ..."`: agent inline script
  syntax OK after the XSS fix.
- `npm --prefix docs-site audit --audit-level=moderate`: found 0
  vulnerabilities after the `devalue` lock update and again after the CI audit
  workflow guard was added.
- `npm --prefix docs-site run astro -- build`: passed after the docs-site lock
  update and again after marking `docs/404` as draft; the earlier `/404`
  catch-all conflict warning no longer appears.
- `python -m pytest tests/test_request_id.py tests/test_production_entrypoint.py tests/test_cors_hardening.py -q -p no:schemathesis -p no:cacheprovider`:
  21 passed, 1 warning after browser security headers and production
  docs/OpenAPI controls.
- `python -m pytest tests/test_docker_compose_hardening.py -q -p no:schemathesis -p no:cacheprovider`:
  3 passed, 1 warning after scoping default Compose to local development.
- `python -m pytest tests/test_production_entrypoint.py tests/test_settings_production_secrets.py tests/test_docs_quality.py -q -p no:schemathesis -p no:cacheprovider`:
  29 passed, 1 warning after the production auto-migration fail-closed change.
- `python -m pytest tests/test_github_workflows.py -q -p no:schemathesis -p no:cacheprovider`:
  5 passed, 1 warning after adding the docs-site npm audit workflow guard.
- `python -m pytest tests/test_restore_verify.py -q -p no:schemathesis -p no:cacheprovider`:
  7 passed, 1 warning after switching restore tar extraction to `filter="data"`.
- Targeted `ruff check` entries for changed Python test/source files passed
  during the 2026-05-30 audit remediation series.
- `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`: not rerun on 2026-05-30 because the current WIP is docs/notebook-only and local resource constraints forbid unnecessary heavy gates.
- PAUSE protocol dry-run simulation: passed (last verified 2026-05-04).
- BLOCKED protocol dry-run simulation: passed (last verified 2026-05-04).
- `python -m pytest -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-may07-snapshot --ignore=tests/integration`: 735 passed, 4 skipped (verified 2026-05-07 at `d0016c2`; 16:20 wall time).
- `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py --no-incremental`: 18 source files clean (verified 2026-05-07).
- `python -m mypy api/app.py --no-incremental --follow-imports=skip`: clean (verified 2026-05-07).
- `python -m pytest tests/test_precommit_config.py -q -p no:schemathesis -p no:cacheprovider`: 9 passed, 1 warning (verified 2026-05-30 at `6755403`).
- `ruff check tests/test_precommit_config.py`: All checks passed (verified 2026-05-30 at `6755403`).
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\ci.yml').read_text(encoding='utf-8')); yaml.safe_load(pathlib.Path(r'.pre-commit-config.yaml').read_text(encoding='utf-8')); print('yaml ok')"`: passed (verified 2026-05-30 at `6755403`).
- `python -m pytest tests/test_root_routes.py tests/test_admin_view.py tests/test_production_entrypoint.py tests/test_docs_quality.py tests/test_precommit_config.py tests/test_a11y.py::test_all_table_headers_define_scope tests/test_a11y.py::test_pages_define_one_main_landmark tests/test_a11y.py::test_widget_page_is_covered_by_a11y_landmark_checks tests/test_a11y.py::test_removed_trace_ui_templates_are_not_a11y_targets tests/test_a11y.py::test_a11y_templates_render_for_snapshot tests/test_a11y.py::test_a11y_template_heading_order_is_sequential -q -p no:schemathesis -p no:cacheprovider`: 56 passed (verified 2026-05-30 at `1ff5ff3` before commit).
- `python -m pytest tests/test_mobile_responsive.py -q -p no:schemathesis -p no:cacheprovider`: 3 passed (verified 2026-05-30 at `1ff5ff3` before commit).
- `python -m pytest tests/test_post_deploy_smoke.py::test_smoke_script_keeps_python_311_compatible_fstrings -q -p no:schemathesis -p no:cacheprovider`: failed before the smoke-report fix with one Python 3.11 f-string compatibility finding, then passed after the fix.
- `python -m pytest tests/test_post_deploy_smoke.py -q -p no:schemathesis -p no:cacheprovider`: 7 passed, 1 warning (verified 2026-05-30 before `69d8e95`).
- `ruff check scripts/post_deploy_smoke.py tests/test_post_deploy_smoke.py`: All checks passed (verified 2026-05-30 before `69d8e95`).
- `python -m py_compile scripts/post_deploy_smoke.py`: passed (verified 2026-05-30 before `69d8e95`).
- `python scripts\weekly_report.py --help` with `PYTHONPATH` set to the
  repository root: passed after commit `a86b44c`.
- `python -m pytest tests/test_precommit_config.py tests/test_weekly_report.py -q -p no:schemathesis -p no:cacheprovider`: 17 passed, 1 warning (verified 2026-05-30 before `a86b44c`).
- `ruff check tests/test_precommit_config.py`: All checks passed (verified
  2026-05-30 before `a86b44c`).
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\weekly-report.yml').read_text(encoding='utf-8')); print('weekly workflow yaml ok')"`:
  passed before `a86b44c`.
- `python -m ruff check .`: All checks passed (verified 2026-05-30 before `6755403`; later code/test changes were checked with targeted Ruff entries above).
- `python -m bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data,./archive-legacy,./.tmp`: 0 medium / 0 high (39 low informational), verified 2026-05-07.
- `pip-audit --strict --disable-pip --require-hashes --timeout 15 --progress-spinner off --cache-dir .tmp/pip-audit-cache --ignore-vuln CVE-2026-45829 --ignore-vuln GHSA-f4j7-r4q5-qw2c -r requirements.lock`: no known vulnerabilities found, 1 ignored (verified 2026-05-30 after the ChromaDB lock update).
- `gh pr checks 1`: all non-skipped CI jobs passed on PR #1 code head `11add63` before merge (helm, lint, migrations, pre-commit, regression-eval, security, test-integration 3.11/3.13, test-unit 3.11/3.13, type-check). Duplicate push/PR jobs were expected for that branch.
- `gh pr merge 1 --merge`: merged PR #1 into `master` at `415d4c8`.
- `gh run watch 26670103203 --exit-status`: master CI passed on `415d4c8` (migrations, type-check, integration 3.11/3.13, unit 3.11/3.13, lint, pre-commit, security, helm; regression-eval skipped because inputs did not change).
- `gh run watch 26670103209 --exit-status`: Pages docs build and deploy passed on `415d4c8`.
- `gh run watch 26671830370 --exit-status`: master CI passed on
  `a86b44c` (regression-eval skipped because inputs did not change).
- `gh workflow run weekly-report.yml --ref master` followed by
  `gh run watch 26671836799 --exit-status`: manual Weekly Report dispatch
  passed on `a86b44c`.
- `python -m pytest tests/test_startup_concurrency.py -q -p no:schemathesis -p no:cacheprovider`:
  2 passed, 1 warning after commit `7b0d9ee` added the Chroma
  embedding-compatibility startup guard.
- `ruff check api/app.py tests/test_startup_concurrency.py`: All checks
  passed after commit `7b0d9ee`.
- `python -m pytest tests/test_startup_concurrency.py tests/test_health.py tests/test_magic_numbers_settings.py -q -p no:schemathesis -p no:cacheprovider`:
  15 passed, 2 warnings after commit `7b0d9ee`.
- `python -m py_compile api/app.py`: passed after commit `7b0d9ee`.
- Live diagnostic regression before commit `7b0d9ee`:
  `python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 1 --seed 42 --allow-paid-apis --no-persist`
  reached live Mistral but failed the gate with 0% pass because the default
  local Chroma collection expected embedding dimension 3 while `BAAI/bge-m3`
  produced 1024.
- Same live regression after commit `7b0d9ee`: failed fast before answer
  generation with `vector store is not initialized` plus a clear log that the
  existing Chroma store is incompatible and must be rebuilt.
- Non-destructive live eval collection setup: copied `docs/warranty.md`,
  `docs/returns_policy.md`, and `docs/errors_e10_e30.md` into
  `.tmp/live-eval-seed-docs-20260530T0835`, then ingested them with
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835` and
  `INGESTION_BATCH_ENABLED=false`; ingestion loaded 3 documents and produced
  6 chunks. No tracked data or existing default Chroma collection was deleted.
- Live Mistral regression with the eval collection:
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835 ONLINE_EVALUATORS_ENABLED=false python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 3 --seed 42 --allow-paid-apis --no-persist`
  passed the gate: 3 effective cases, baseline pass rate 100%, candidate pass
  rate 100%, 0 regressions, 0 infrastructure failures, baseline cost
  `$0.000042`, candidate cost `$0.000228`.
- `gh run list --branch master --limit 5`: CI run `26679263174` and Pages run
  `26679263187` passed on pushed commit `7b0d9ee`.
- `python -m pytest tests/test_regression_runner.py tests/test_provider_benchmark.py -q -p no:schemathesis -p no:cacheprovider`:
  22 passed, 1 warning after commit `517ec57` added live regression wall-clock
  latency fallback.
- `ruff check scripts/regression_eval.py tests/test_regression_runner.py tests/test_provider_benchmark.py`:
  All checks passed after commit `517ec57`.
- `python -m py_compile scripts/regression_eval.py`: passed after commit
  `517ec57`.
- Live latency verification with the eval collection:
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835 ONLINE_EVALUATORS_ENABLED=false python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 1 --seed 43 --allow-paid-apis --no-persist`
  passed the gate and reported non-zero latency: baseline avg latency
  `59015.0 ms`, candidate avg latency `29661.0 ms`.
- `gh run watch 26679564874 --exit-status`: master CI passed on pushed commit
  `517ec57`.
- R3/R4 batch grading follow-up:
  `python -m pytest tests/test_grade_docs.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_prompt_registry_integration.py tests/test_otel.py tests/test_langfuse_trace.py -q -p no:schemathesis -p no:cacheprovider`:
  29 passed, 1 warning after commit `71367a7` batched multi-document
  `grade_docs` into one structured LLM call with fallback to the old per-doc
  path.
- `ruff check .`: All checks passed after commit `71367a7`.
- `python -m py_compile agent/graph.py agent/prompts.py`: passed after commit
  `71367a7`.
- `python -m mypy agent/prompts.py agent/graph.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `71367a7`. The same local two-file command without
  `--follow-imports=skip` timed out at 180s; GitHub CI run `26679982808`
  completed successfully on the pushed commit.
- `gh run list --branch master --limit 5`: CI run `26679982808` and Pages run
  `26679982810` passed on pushed commit `71367a7`.
- R4 fact-verification tracing follow-up:
  `python -m pytest tests/test_grade_docs.py tests/test_fact_verification.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_langfuse_trace.py tests/test_otel.py -q -p no:schemathesis -p no:cacheprovider`:
  31 passed, 1 warning after commit `c0b6d24` added `trace_llm_call`
  instrumentation for `verify_facts.extract_claims` and
  `verify_facts.verify_claim`.
- `ruff check .`: All checks passed after commit `c0b6d24`.
- `python -m py_compile agent/graph.py tests/test_fact_verification.py`: passed
  after commit `c0b6d24`.
- `python -m mypy agent/graph.py tests/test_fact_verification.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `c0b6d24`.
- `gh run watch 26680293620 --exit-status`: master CI passed on pushed commit
  `c0b6d24`.
- `gh run view 26680293609 --json status,conclusion,name,headSha,url`: Pages
  deploy passed on pushed commit `c0b6d24`.
- R7 curated seed expansion:
  `python -m pytest tests/test_curated_dataset.py tests/test_regression_runner.py tests/test_detect_stale_curated_cases.py -q -p no:schemathesis -p no:cacheprovider`:
  38 passed, 1 warning after commit `c964211` expanded
  `evaluation/curated_cases.jsonl` from 20 to 35 checked-in RU cases.
- `python scripts/regression_eval.py --baseline current --candidate current --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 100 --seed 42 --mock-experiment-runtime --no-persist`:
  passed the local mock gate on 35/35 cases with 0 regressions, 0
  infrastructure failures, and 100%/100% baseline/candidate pass rate.
- `ruff check .`: All checks passed after commit `c964211`.
- `python -m py_compile tests/test_curated_dataset.py scripts/regression_eval.py`:
  passed after commit `c964211`.
- `gh run watch 26680554552 --exit-status`: master CI passed on pushed commit
  `c964211`; the `regression-eval` job is PR-only and was skipped on this
  push.
- Final CI guard follow-up: `.github/workflows/ci.yml` now includes
  `evaluation/curated_cases.jsonl` in the `regression-eval` paths-filter, with
  `tests/test_github_workflows.py::test_regression_eval_filter_tracks_curated_dataset_changes`
  covering the guard. The red test failed before the workflow update and passed
  after it.
- Adaptive retrieval routing seam:
  `python -m pytest tests/test_model_routing.py tests/test_base_manager.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_magic_numbers_settings.py tests/test_new_features.py tests/test_structural_chunking.py tests/test_experiment_registry.py -q -p no:schemathesis -p no:cacheprovider`:
  66 passed, 2 warnings after commit `676b3e0` added `RAG_RETRIEVAL_STRATEGY`,
  `global` query classification, vector-only simple-query retrieval, and
  simple-query graph bypass for `grade_docs`/`verify_facts`.
- `ruff check agent/graph.py agent/state.py agent/prompts.py config/settings.py vectordb/_base_manager.py tests/test_model_routing.py tests/test_base_manager.py`:
  All checks passed before `676b3e0`.
- `python -m mypy agent/graph.py agent/state.py config/settings.py vectordb/_base_manager.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed before `676b3e0`.
- Aircargo curated seed expansion to the local R7 lower bound:
  `python -m pytest tests/test_curated_dataset.py -q -p no:schemathesis -p no:cacheprovider`:
  12 passed, 1 warning after commit `325d63c` expanded
  `evaluation/curated_cases_aircargo.jsonl` from 31 to 100 checked-in RU cases
  across the `32e841f`, `6b7417d`, and `325d63c` seed commits.
- `python -c "... evaluation/curated_cases_aircargo.jsonl ..."`: confirmed 100
  total rows and 100 unique `case_id` values after commit `325d63c`.
- `python scripts/regression_eval.py --baseline current --candidate current --dataset evaluation/curated_cases_aircargo.jsonl --tenant aircargo --max-cases 150 --seed 42 --mock-experiment-runtime --no-persist`:
  passed the mock gate on 100/100 aircargo cases with 0 regressions and 0
  infrastructure failures.
- `ruff check tests/test_curated_dataset.py`: All checks passed after
  `325d63c`.
- `python -m py_compile tests/test_curated_dataset.py`: passed after
  `325d63c`.
- Ahead-series focused verification after commit `db61488`:
  `python -m pytest tests/test_model_routing.py tests/test_base_manager.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_magic_numbers_settings.py tests/test_new_features.py tests/test_structural_chunking.py tests/test_experiment_registry.py tests/test_curated_dataset.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-ahead-focused-2`:
  95 passed, 2 warnings.
- `python -m mypy agent/graph.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `db61488` fixed the tenant-aware manager's `Document`
  type alias for mypy while keeping runtime `manager.Document` compatibility.
- `ruff check agent/graph.py agent/prompts.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py tests/test_base_manager.py tests/test_curated_dataset.py tests/test_model_routing.py tests/test_structural_chunking.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py`:
  All checks passed after `db61488`.
- `python -m py_compile agent/graph.py agent/prompts.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py tests/test_base_manager.py tests/test_curated_dataset.py tests/test_model_routing.py tests/test_structural_chunking.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py`:
  passed after `db61488`.
- Ahead-series docs/config verification:
  `python -m pytest tests/test_docs_quality.py tests/test_quickstart_docs.py tests/test_backlog_docs.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-docs-ahead`:
  19 passed, 1 warning after commit `8c70cf9`.
- `ruff check tests/test_docs_quality.py tests/test_quickstart_docs.py tests/test_backlog_docs.py`:
  All checks passed after `8c70cf9`.
- `git diff --check origin/master..HEAD`: passed after `8c70cf9`.
- Ahead-series CI/meta verification:
  `python -m pytest tests/test_precommit_config.py tests/test_github_workflows.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-meta-ahead`:
  16 passed, 1 warning after commit `f6efe4f`.
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\ci.yml').read_text(encoding='utf-8')); yaml.safe_load(pathlib.Path(r'.pre-commit-config.yaml').read_text(encoding='utf-8')); print('yaml ok')"`:
  passed after `f6efe4f`.
- Ahead-series regression-tooling verification:
  `python -m pytest tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-regression-tooling-ahead`:
  34 passed, 1 warning after `f6efe4f`.
- `ruff check tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py scripts/regression_eval.py`:
  All checks passed after `f6efe4f`.
- `python -m py_compile scripts/regression_eval.py tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py`:
  passed after `f6efe4f`.
- Ahead-series pre-commit verification:
  the first `pre-commit run --from-ref origin/master --to-ref HEAD` failed
  before hooks ran because the global cache file
  `C:\Users\uedom\.cache\pre-commit\repo8mdvhro7\.pre-commit-hooks.yaml`
  returned `PermissionError: [Errno 13] Permission denied`. Rerunning with
  `PRE_COMMIT_HOME` pointed at ignored `.tmp/pre-commit-cache` passed: Ruff,
  trailing-whitespace, end-of-file, large-file, merge-conflict, private-key,
  and Bandit hooks passed; YAML/TOML/pip-audit hooks were skipped because no
  relevant files were in the ahead diff.
- Ahead-series settings/env verification:
  `python -m pytest tests/test_provider_settings.py tests/test_settings_production_secrets.py tests/test_production_entrypoint.py tests/test_magic_numbers_settings.py tests/test_experiment_registry.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-settings-ahead`:
  47 passed, 2 warnings after commit `0f2a2be`.
- `ruff check tests/test_provider_settings.py tests/test_settings_production_secrets.py tests/test_production_entrypoint.py tests/test_magic_numbers_settings.py tests/test_experiment_registry.py config/settings.py`:
  All checks passed after `0f2a2be`.
- `python -m py_compile config/settings.py tests/test_provider_settings.py tests/test_settings_production_secrets.py tests/test_production_entrypoint.py tests/test_magic_numbers_settings.py tests/test_experiment_registry.py`:
  passed after `0f2a2be`.
- Ahead-series eval-tooling verification:
  `python -m pytest tests/test_ragas_eval.py tests/test_online_evaluators.py tests/test_regression_eval_profile_target.py tests/test_experiment_comparison.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-eval-tooling-ahead`:
  36 passed, 1 warning after commit `e24d270`.
- `ruff check tests/test_ragas_eval.py tests/test_online_evaluators.py tests/test_regression_eval_profile_target.py tests/test_experiment_comparison.py evaluation/ragas_eval.py`:
  All checks passed after `e24d270`.
- `python -m py_compile evaluation/ragas_eval.py tests/test_ragas_eval.py tests/test_online_evaluators.py tests/test_regression_eval_profile_target.py tests/test_experiment_comparison.py`:
  passed after `e24d270`.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external
  services, live external-provider/API benchmark calls, destructive commands.

## Next Step

All `docs/plans/2026-05-01-backlog.md` items remain closed. The Colab remote
benchmark PR is merged into `master`:

- `905a65e` adds `docs/operations/colab-remote-benchmark.md` and
  `notebooks/rag_support_colab_remote_benchmark.ipynb`.
- `b5eb848` records the Windows laptop thin-client boundary.
- `a461fba` aligns the notebook to clone `colab-remote-benchmark` and ignores
  `.pytest-tmp*/` local pytest basetemp directories.
- `fe9a474` clears notebook Ruff and security CI issues.
- `965ccd5` documents the narrow unfixed ChromaDB audit ignore.
- `6755403` aligns the CI security config test with the multiline locked
  `pip-audit` command.
- `1ff5ff3` closes the Claude trace audit findings: protected root trace
  redirect, registered API trace target, stale `/traces-ui` docs removal,
  a11y target cleanup, authenticated review-queue trace fetch, and Python
  3.11/3.13 CI coverage for unit/integration tests.
- `69d8e95` fixes the Python 3.11-only smoke-report f-string syntax failure
  found by the new CI matrix and adds a local source guard.
- `11add63` refreshes durable handoff/status docs before merge.
- `415d4c8` is the merge commit on `master`.
- `52d16c4` refreshes GitHub Actions action majors, docs wording, and the
  pre-commit config guard test.
- `a86b44c` fixes the scheduled Weekly Report workflow import path by keeping
  the repository root on `PYTHONPATH`; master CI and a manual Weekly Report
  dispatch passed on that commit.
- `7b0d9ee` fails closed when a persisted Chroma collection is incompatible
  with the active embedding model, with a regression test for dimension
  mismatch.
- `517ec57` records wall-clock case latency in live regression reports when
  trace storage has no duration, so live benchmark summaries no longer show
  `0.0 ms` latency.
- `71367a7` reduces R3/R4 LLM fan-out by batching multi-document
  `grade_docs` into one structured call, while preserving the old per-doc
  fallback and top-ranked-doc preservation guard. Master CI run `26679982808`
  and Pages run `26679982810` passed.
- `c0b6d24` records per-call trace events for fact verification extraction and
  claim checks (`verify_facts.extract_claims`, `verify_facts.verify_claim`),
  so R4 latency/cost analysis can see that fan-out explicitly. Master CI run
  `26680293620` and Pages run `26680293609` passed.
- `c964211` expands the checked-in curated RAG seed set from 20 to 35 RU cases
  over the tracked warranty/returns/error KB docs and adds a guard test for the
  minimum local seed coverage. Master CI run `26680554552` passed; local mock
  regression on all 35 cases passed 35/35.
- `676b3e0` adds the local adaptive retrieval seam: `RAG_RETRIEVAL_STRATEGY`,
  `GLOBAL` classification, vector-only retrieval for simple routed questions,
  and graph bypass of `grade_docs`/`verify_facts` on simple questions.
- `32e841f`, `6b7417d`, and `325d63c` expand the aircargo checked-in eval seed
  from 31 to 100 RU cases over HR/legal/logistics/compliance docs; local mock
  regression passed 100/100.
- `db61488` fixes the tenant-aware vector manager's `Document` typing so the
  full ahead-series focused mypy command passes with `vectordb/manager.py`
  included.
- `8c70cf9` records the focused ahead-series verification; a follow-up
  docs/config gate passed `tests/test_docs_quality.py`,
  `tests/test_quickstart_docs.py`, and `tests/test_backlog_docs.py`.
- `f6efe4f` records that docs/config gate; subsequent local meta and regression
  tooling gates also passed without live APIs.
- Pre-commit over `origin/master..HEAD` passed when using an isolated ignored
  `PRE_COMMIT_HOME=.tmp/pre-commit-cache`; the default global pre-commit cache
  is not currently reliable on this Windows user profile.
- Settings/env guard tests passed for the ahead series after `0f2a2be`.
- Eval-tooling unit tests for RAGAS/online-evaluator/profile/comparison code
  passed after `e24d270`; no heavy baseline, ingest, or live API was run.
- JavaScript/docs-site follow-up: commit `d09405c` adds the missing
  `@astrojs/check` and `typescript` dev dependencies so `astro check` is a real
  local gate, annotates the Starlight head-tag config for type checking,
  removes an unused `sync-docs.mjs` import, and uses an npm override so
  `yaml-language-server` resolves to non-vulnerable `yaml`.
- JS/docs-site verification after `d09405c`:
  `node --check` passed for `static/admin.js`, `static/widget.js`,
  `docs-site/astro.config.mjs`, and all `docs-site/scripts/*.mjs`;
  `npm --prefix docs-site audit --audit-level=moderate` found 0
  vulnerabilities; `npm --prefix docs-site run astro -- check` returned 0
  errors / 0 warnings / 0 hints; `npm --prefix docs-site run build` built 33
  pages; `PRE_COMMIT_HOME=.tmp/pre-commit-cache pre-commit run --from-ref origin/master --to-ref HEAD`
  passed.
- JavaScript/docs-site CI follow-up: commit `67a067f` adds a `check` npm script
  and runs `npm run check` in `.github/workflows/docs-site.yml` after npm audit
  and before the Pages build. The guard test first failed because the workflow
  had no `Type-check docs site` step, then passed after the workflow update.
- JavaScript static syntax guard: commit `fd6c864` adds
  `tests/test_static_js_quality.py`, which runs `node --check` over
  `static/admin.js`, `static/widget.js`, `docs-site/astro.config.mjs`, and all
  checked-in `docs-site/scripts/*.mjs` when Node is available.

PR #1 (`https://github.com/brownjuly2003-code/RAG_Support_Assistant/pull/1`) is
merged. Master CI and Pages deploy passed on `415d4c8`; post-merge handoff
commit `f8ffb0f` is on `origin/master`.

2026-05-30 compact-resume note:

- This compact refresh is intentionally limited to GitHub Actions action-major
  refresh, docs wording, and the pre-commit config guard test.
- `MISTRAL_API_KEY` is present in local `.env` and Mistral `/v1/models`
  returned `200`; no secret value was printed or copied. `D:\TXT\GMAIL.txt`
  had no relevant Mistral key names.
- GraceKelly was not reachable at `http://127.0.0.1:8011/healthz/ready`; no
  local GraceKelly, Docker, Ollama, or model process was started because of
  the current resource boundary.
- No non-live local backlog item remains open. A live GraceKelly/Mistral run
  is a staged/manual runtime experiment only, not an active backlog item.
- If these refresh files are already clean in `git status`, do not repeat this
  family of checks just to refresh handoff prose. The next safe local action is
  non-destructive branch hygiene only if stale local branches still exist.
- 2026-05-30 non-local follow-up: stale scheduled Weekly Report failures from
  May 2026 were traced to `ModuleNotFoundError: No module named 'config'` when
  GitHub Actions ran `python scripts/weekly_report.py --dry-run`. Commit
  `a86b44c` adds `PYTHONPATH: ${{ github.workspace }}` and a regression guard;
  manual dispatch run `26671836799` passed.
- 2026-05-30 Codex audit remediation follow-up: `docs/audits/audit_codex_30_05_26.md`
  records the audit. Closed local items include Agent UI API-data text
  rendering, docs-site `devalue` audit fix plus CI audit guard, production
  security headers/docs route controls, local-dev-only default Compose
  bindings, production auto-migration fail-closed behavior with explicit
  fail-open override, safe tar extraction in restore verification, and the
  docs-site 404 route warning.
- 2026-05-30 Claude audit follow-up: `docs/audits/audit_claude_30_05_26.md` records a
  Claude Opus 4.8 audit focused on the RAG pipeline and current
  implementation. It identifies R7/R1/R2/R3/R4/R5 follow-up work: measure RAG
  quality on a larger RU eval set, switch the default reranker after A/B,
  reduce LLM fan-out, and address deferred
  deprecations/security hardening. R2 is closed by `5c7f3b1`: RRF now keys by
  stable metadata ids when available and otherwise includes a full content hash,
  with regression tests for shared contextual-header prefixes. R5's baseline
  tokenizer fix is closed by `e91c1f1`: BM25 now uses Unicode word tokens plus
  `casefold()` for index and query tokenization; deeper RU lemmatization remains
  optional future tuning.
- 2026-05-30 R7 live baseline follow-up: user explicitly opted into
  GraceKelly/Mistral local runtime. Commit `7b0d9ee` makes startup fail closed
  for an incompatible persisted Chroma collection instead of running retrieval
  with dimension errors and empty citations. The default local
  `rag_docs_default` collection remains stale/incompatible until rebuilt. A
  separate ignored eval collection `rag_eval_20260530t0835_default` was built
  from the three tracked demo KB docs and produced a passing 3-case live
  Mistral baseline. Commit `517ec57` also fixed live regression latency
  accounting; a follow-up 1-case live report showed non-zero baseline/candidate
  latency. This is only a partial R7 signal; full R7 still requires a larger RU
  eval set and a larger live run.
- 2026-05-30 R3/R4 fan-out follow-up: commit `71367a7` changes
  multi-document `grade_docs` from one LLM call per document to one batch
  structured LLM call, with JSON/text parsing fallback and the previous
  per-document path retained when batch grading is unavailable. This addresses
  the per-doc grade fan-out locally; follow-up latency proof should use the
  larger R7 eval set rather than another tiny smoke.
- 2026-05-30 R4 observability follow-up: commit `c0b6d24` adds Langfuse/SQLite
  trace events with durations for `verify_facts` claim extraction and each
  claim verification call. The audit's fan-out can now be measured from traces;
  it does not change factuality behavior.
- 2026-05-30 R7 seed expansion follow-up: commit `c964211` grows the
  checked-in curated dataset from 20 to 35 RU cases and adds a guard against
  shrinking it below 35 unique case IDs. This is not the full 100-150 case
  RAGAS baseline from the audit, but it raises the local regression floor and
  keeps the next full R7 run grounded in tracked KB content.
- 2026-05-30 final CI guard: the regression-eval PR paths-filter now tracks
  `evaluation/curated_cases.jsonl`, so future dataset edits trigger the mock
  regression gate on PRs.
- 2026-05-30 local routing follow-up: commit `676b3e0` implements the ADR 0001
  retrieval seam locally without enabling heavy graph retrieval. Simple routed
  queries use vector-only retrieval when available and skip per-doc grading and
  fact verification; `global` classification is recognized but falls back to
  hybrid unless a graph retriever is configured.
- 2026-05-30 aircargo R7 seed follow-up: commits `32e841f`, `6b7417d`, and
  `325d63c` grow `evaluation/curated_cases_aircargo.jsonl` from 31 to 100
  grounded RU cases and raise the guard to 100 unique RU queries. Mock
  regression on the aircargo set passed 100/100 with no live APIs. The next
  R7 step is no longer local seed growth to 100; it is a staged Colab/RAGAS
  baseline or optional expansion toward 150 cases if that baseline needs more
  coverage.
- 2026-05-30 Claude CLI follow-up: `claude -p` read-only full-project review
  prompts were blocked by Anthropic cyber safeguards, and
  `claude ultrareview --timeout 30` returned "Ultrareview is currently
  unavailable." No token or safeguard adjustment URL from the CLI error was
  copied into project files. The actual Claude audit exists in
  `docs/audits/audit_claude_30_05_26.md`.
- Ripgrep search hygiene follow-up: commit `bd4c25a` adds a repo-local
  `.ignore` for `pytest-cache-files-*` so broad `rg` searches over explicit
  paths skip pytest temp directories before Windows denies access. The broad
  JavaScript/docs-site search that previously emitted `Access is denied`
  completed without those errors after adding the basename ignore pattern.
- Widget static asset follow-up: commit `6a0469d` extends the admin UI smoke
  tests to cover `/static/widget.js` and `/static/widget.html`, including the
  embed marker and iframe target used by the checked-in widget script. Focused
  verification passed with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; the unscoped
  local pytest plugin autoload path fails before collection because a globally
  installed `schemathesis` plugin imports missing `_pytest.subtests`.
- Static HTML entrypoint follow-up: commit `31996d1` parameterizes the FastAPI
  static-page smoke coverage across the checked-in UI entrypoints:
  admin/agent/analytics/chat/help/login/metrics/widget. Focused UI/static JS
  verification passed 12 tests with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, plus
  Ruff, py_compile, and `git diff --check`.
- Analytics CDN hardening follow-up: commit `d9227e2` pins the analytics page
  Chart.js dependency to `chart.js@4.5.1/dist/chart.umd.min.js`, adds
  SHA-384 SRI plus `crossorigin="anonymous"`, and adds a JS quality guard that
  fails on unpinned jsDelivr npm scripts or missing integrity. The guard failed
  before the HTML fix, then focused UI/static JS tests and lightweight a11y
  passed with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- L1 deprecation follow-up: commits `477ef2b`, `3ee6a16`, and `2e46215`
  reduce import-time deprecated surfaces without dependency lock changes.
  `agent.graph` now prefers `langchain_ollama.OllamaLLM` when available and
  keeps the existing `langchain_community` fallback; `auth.oidc` lazy-loads the
  Authlib OAuth client only when SSO is used; `vectordb._base_manager`
  lazy-loads `SemanticChunker` only when semantic chunking runs. Remaining
  `langchain_community` and Authlib references are compatibility fallback/lazy
  paths; full removal is a separate dependency/SSO migration.
- L1 verification after those commits: focused Ollama/circuit-breaker tests
  passed `14 passed`; provider/graph/Ollama tests passed `12 passed`; OIDC/JWT
  tests passed `11 passed`; vector manager semantic/base/structural tests
  passed `20 passed`; targeted Ruff, py_compile, mypy, and `git diff --check`
  passed for the changed files.
- M4/import-time coverage follow-up: commit `d0357e4` adds focused pure-helper
  tests for `agent.graph` batch grade parsing, knowledge-gap detection, and LLM
  usage accounting. Commit `127d025` lazy-loads `sentence_transformers.CrossEncoder`
  so importing `vectordb._base_manager` and `api.app` no longer instantiates the
  heavy reranker stack; `api.app` import was measured at about `5.039 s` with
  `sentence_transformers` absent from `sys.modules` after the fix. New focused
  API helper coverage lives in `tests/test_api_app_helpers.py`.
- M4 verification after those commits: `tests/test_graph_helpers.py` passed
  `5 passed`; the related graph set passed `19 passed`; focused reranker lazy
  tests passed `2 passed`; `tests/test_api_app_helpers.py` passed `8 passed`;
  the related API/vector/middleware set passed `43 passed`; targeted Ruff,
  py_compile, mypy for `vectordb/_base_manager.py`, and `git diff --check`
  passed.
- M4 graph helper follow-up: commit `30cae93` covers agentic tool-call
  normalization, agentic tool-definition contracts, and static capability
  detection for tool/schema-capable LLMs. Verification passed with
  `tests/test_graph_helpers.py`, `tests/test_agent_tools.py`, and
  `tests/test_provider_graph_integration.py` (`24 passed`), plus targeted
  Ruff, py_compile, and `git diff --check`.
- M4 targeted coverage follow-up: commits `debb828`, `c6d0f3a`, and `33ac0be`
  add the audit-requested narrow tests for `agent/tools.py`, `auth/oidc.py`,
  and `admin_review`: direct tool formatting/status branches, OIDC provider
  registration with SecretStr-like values and fake OAuth, and review-queue
  stats aggregation by tenant. Verification passed with `tests/test_agent_tools.py`
  (`10 passed`), the related agent/graph set (`20 passed`), OIDC/JWT tests
  (`13 passed`), `tests/test_review_queue.py` (`10 passed`), the related
  admin/router set (`19 passed`), plus targeted Ruff, py_compile, and
  `git diff --check`.

Notebook URL for manual Colab use:
`https://colab.research.google.com/github/brownjuly2003-code/RAG_Support_Assistant/blob/master/notebooks/rag_support_colab_remote_benchmark.ipynb`

To run another dry-run of the autopilot guardrails:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

Default safe work should come from `docs/plans/2026-05-01-backlog.md`; scheduler installation remains opt-in only.
