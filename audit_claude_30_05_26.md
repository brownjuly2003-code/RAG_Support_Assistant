# Audit Claude — RAG Support Assistant

Дата: 2026-05-30
Аудитор: Claude (Opus 4.8)
Проект: `D:\RAG_Support_Assistant`
Ветка: `master`
HEAD на момент аудита: `c2850bb` (`docs: record claude audit attempt`)
Метод: статический разбор кода + durable docs + сверка с уже выполненными gate-прогонами; тяжёлые gates (полный pytest ~17 мин, mypy, helm) **не перезапускались** — опираюсь на зафиксированный прогон Codex/AGENT_STATE от того же дня и на точечные проверки кода. Это явно помечено ниже.

> Этот аудит **не дублирует** свежий `audit_codex_30_05_26.md`. Я сверил его findings с текущим HEAD (большинство уже закрыто коммитами) и сфокусировался на том, что просили отдельно: **RAG-пайплайн и актуальность реализации**. Новые findings — преимущественно в RAG-слое и не фигурировали в прошлых аудитах.

---

## 1. Executive Summary

Инженерно проект в сильном состоянии: зелёный pytest (748 passed / 5 skipped по прогону 30.05), coverage 71.6% > gate 70%, ruff/mypy-strict/bandit/pip-audit чистые, Helm lint/render OK, Alembic single-head `017`. Архитектура — зрелый FastAPI + LangGraph RAG-сервис с Postgres/Redis/Chroma, provider-runtime (GraceKelly/Ollama/Mistral), observability, eval-loop, review queue, multi-tenancy.

**Главный вывод по RAG:** пайплайн архитектурно **соответствует state-of-the-art 2026** (Agentic RAG + Hybrid + RRF + cross-encoder rerank + CRAG grade + Self-RAG retry + HyDE + parent-child + semantic chunking). Но в реализации есть **конкретные дефекты качества и актуальности**, которые снижают фактическую отдачу этих методов на русскоязычном support-контенте. Они и есть основная ценность этого аудита.

| Аспект | Оценка | Комментарий |
|---|---|---|
| Архитектура RAG | 8.5/10 | Полный современный стек; правильная декомпозиция узлов LangGraph |
| **Качество реализации RAG** | **6.5/10** | Английский реранкер на RU-контенте, RRF-дедуп коллизии, наивный BM25, LLM-fan-out |
| Backend / код | 8.0/10 | Чистые gates, но `graph.py` (2105) и `api/app.py` (1932) — крупные центры сложности |
| Безопасность | 7.5/10 | H1 XSS закрыт; security headers/CSP добавлены; остаётся token в localStorage |
| Тесты / CI | 8.0/10 | Широкий suite + integration; слабое покрытие critical orchestration (37–56%) |
| Observability / Ops | 9.0/10 | Prometheus ~50 метрик, OTel, alert rules, retention, backup/restore, Helm cronjobs |
| Актуальность стека | 8.0/10 | Современно; долговая зона — deprecation (LangChain Ollama, Authlib) |
| **Итого** | **7.7/10** | Сильный, хорошо verified проект; до публичного prod нужны RAG-fix #1 и закрытие deprecation |

---

## 2. Verification (статус gates)

| Gate | Результат | Источник |
|---|---|---|
| `pytest -p no:schemathesis` | 748 passed / 5 skipped | прогон Codex 30.05 (AGENT_STATE) — не перезапускал |
| coverage | 71.56% > gate 70% | там же |
| `ruff check .` | PASS | там же |
| mypy strict scope | PASS (18 файлов) | там же |
| bandit / pip-audit | 0 med/high; 1 ignored Chroma advisory | там же |
| helm lint/template | PASS | там же |
| alembic heads | single `017` | там же |
| **agent.html: нет `innerHTML`** | **подтверждено мной** (0 совпадений; остались только `textContent`) | grep, 30.05 |
| **reranker по умолчанию = English** | **подтверждено мной** (`settings.py:289`) | grep, 30.05 |
| **eval-качество RAG измерено?** | **НЕТ** (см. R7): 20 кейсов, 32 regression-отчёта с нулями, RAGAS не прогонялся | inspect, 30.05 |
| LLM-бэкенд для eval | **жив** (GraceKelly :8011 + Mistral) — на 30.05 подтверждено пользователем; eval-прогон разблокирован | user, 30.05 |

> Я не перезапускал тяжёлые gates сознательно (resource boundary + они отработаны сегодня же). Если нужен независимый прогон — скажи, запущу `pytest -p no:schemathesis --basetemp=.tmp/pytest`.

### 2.1 Эмпирическая верификация (что реально прогонялось/проверялось 30.05)

Чтобы аудит был доказательным, а не статической «картой», ключевые findings подтверждены исполнением кода и независимым чтением, а не только рассуждением:

| Проверка | Метод | Результат |
|---|---|---|
| R1 — реранкер на RU | прогон `get_reranker()` на EN/RU парах | **gap EN +17.87 vs RU +0.99** — разделение падает ~18× ✔ measured |
| R2 — RRF-коллизия | репро на реальном `_rrf_merge` (header 251 симв) | **2 чанка → 1, chunk0 потерян** ✔ confirmed |
| R3/R4 — LLM-fan-out | выверка всех узлов графа | **≈15 вызовов/ответ** (прежний «10–11» занижен) ✔ counted |
| R5 — BM25 токенизация | чтение `_base_manager.py:199,219` | `.lower().split()`, без RU-лемматизации ✔ confirmed |
| H1 XSS (Codex) закрыт? | grep `innerHTML` в `agent.html` | 0 совпадений, только `textContent` ✔ closed |
| M1 security headers | grep в `api/app.py` | headers есть, **CSP отсутствует** ✔ partial |
| UX memory-leak (`rec.md` апрель) закрыт? | чтение `chat.html:1362` | event-delegation внедрён ✔ fixed |
| auth/oidc | чтение `auth/oidc.py` | SecretStr-aware, чистый tenant-mapping; authlib → deprecation L1 ✔ |

Не покрыто прогоном (честные границы): полный RAGAS-замер качества (это и есть R7 — staged-задача), agentic tool-loop под `RAG_AGENTIC_MODE` (дефолт off), нагрузочный тест, docs-site Astro.

---

## 3. RAG-пайплайн — разбор и актуальность (ядро аудита)

### 3.1 Что реализовано (карта узлов LangGraph)

`agent/graph.py:1467` `build_support_graph`:

```
classify_complexity → transform_query(+HyDE) → retrieve → grade_docs(CRAG)
   → generate → verify_facts → evaluate → route_or_retry
       ├─ retry → rewrite_query → retrieve → …   (Self-RAG, max 2 iter)
       ├─ auto  → suggest_questions → log → END
       └─ human/error → log/handle_error → END
```

Retrieval (`vectordb/_base_manager.py` `HybridRetriever`): vector (Chroma, BGE-M3) + BM25 → RRF (k=60) → cross-encoder rerank → top-5. Плюс agentic tool-loop (`_run_agentic_flow`, `search_kb`/`check_order_status`/`create_ticket`) под флагом `RAG_AGENTIC_MODE`.

**Вердикт по актуальности:** это honestly 2026-современный дизайн. Все 5 топ-методов из `docs/research/rag-landscape-2026.md` присутствуют. GraphRAG отсутствует — но он же сам обоснованно отложен (дорог, нужен при >10K doc). Здесь претензий нет.

### 3.2 Findings (новые, RAG-специфичные)

---

#### R7 — Качество RAG **никогда не измерено** на реальных данных — **HIGH (foundational)**

Файлы: `evaluation/curated_cases.jsonl`, `reports/regression/*`, `evaluation/ragas_eval.py`

Машинерия оценки — first-class (RAGAS, regression gate, curated dataset, drift, nightly). Но **достоверных замеров нет**:
- `evaluation/curated_cases.jsonl` = **20 кейсов** (для grounding/precision/recall статистически мало).
- 32 отчёта в `reports/regression/` — **все нулевые**: pass rate 0.00%, latency 0.0ms, cost $0, gate=fail (режим `live-provider-benchmark`, но прогоны фактически пустые — LLM не отвечал, вероятно Groq geo-block / Mistral 429 на момент тех запусков).
- `evaluation/ragas_eval.py` ни разу не доведён до отчёта (присутствует только в `.mypy_cache`).

**Impact:** faithfulness / context-precision / context-recall / answer-relevancy — неизвестны. Все остальные RAG-улучшения (R1–R5) **недоказуемы** без baseline. Это потолок оценки: «отличный RAG» при неизмеренном качестве — гипотеза, а не факт.

**Fix (разблокировано — GraceKelly :8011 и Mistral живы на 30.05):**
1. Расширить curated-датасет до **100–150 RU-кейсов** по доменам поддержки (заказы/возвраты/оплата/ошибки/доставка), с `expected.*` и `human_verdict`.
2. Прогнать `scripts/nightly_eval.py` + RAGAS на текущей конфигурации → зафиксировать **baseline**-цифры.
3. Повторить после R1 (reranker) → дельта.
4. Вынести цифры в README и в этот аудит. Включить regression-gate в CI на RU-сете (он уже есть, но кормится 20 кейсами).

---

#### R1 — Реранкер English-only на русскоязычном продукте — **HIGH**

Файлы: `config/settings.py:286-289`, `vectordb/_base_manager.py:133-156`, `260-272`

Дефолт: `RAG_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"` — модель обучена на **английском** MS MARCO (что прямо отмечено комментарием `settings.py:286`: «English»). При этом:
- эмбеддер мультиязычный `BAAI/bge-m3`,
- продукт отвечает по-русски (промпты, ответы, UI на русском),
- мультиязычная пара `BAAI/bge-reranker-v2-m3` уже выписана рядом в комментарии (`settings.py:287`), но **не выбрана дефолтом**.

**Impact:** reranking — по собственному research-документу «обязательный слой» и финальный фильтр перед генерацией (`_rerank` режет до top-5). English cross-encoder на русских парах query/passage даёт near-random скоринг → в промпт попадают subоптимальные документы → падает точность ответа и citation-релевантность. Это самый дорогой по эффекту дефект: страдает именно тот слой, который должен повышать precision.

**Эмпирическое подтверждение (прогон 30.05 на дефолтной модели `ms-marco-MiniLM-L-6-v2`):**

| Язык | score(relevant) | score(irrelevant) | gap |
|---|---|---|---|
| EN (вопрос про возврат) | +6.55 | −11.32 | **+17.87** (чистое разделение) |
| RU (тот же смысл) | +8.50 | +7.51 | **+0.99** |

На русском реранкер дал нерелевантному пассажу («график работы доставки») +7.5 при запросе про возврат товара — почти как релевантному. Различающая способность падает в **~18 раз**. В реальном top-20→top-5, где десятки кандидатов набирают +7±1, итоговый порядок становится шумом. Дефект измерен, не гипотеза.

**Fix:**
- Переключить дефолт на `BAAI/bge-reranker-v2-m3` (пара к BGE-M3, multilingual).
- Прогнать A/B на `evaluation/curated_cases.jsonl` (RU-кейсы) через `scripts/regression_eval.py` — сравнить retrieval_hit_rate / quality до и после.
- Учесть, что bge-reranker-v2-m3 тяжелее MiniLM (568M vs 22M) → проверить latency на CPU; при недостатке ресурсов рассмотреть `bge-reranker-base` или GPU.

---

#### R2 — RRF-дедуп по префиксу контента ломается на contextual headers — **MEDIUM**

Файлы: `vectordb/_base_manager.py:248,253` (`_rrf_merge`), сопряжено с `RAG_CONTEXTUAL_HEADERS=true` (дефолт)

Ключ дедупликации в RRF — `doc.page_content[:200]` (`RRF_DOC_KEY_CHARS`). Фича contextual headers **префиксует чанки одинаковым заголовком документа/секции** перед эмбеддингом. Значит два разных чанка одного документа могут совпасть по первым 200 символам → в `scores`/`doc_map` они схлопываются в один ключ, и **один чанк молча теряется** (плюс перетирается в `doc_map`).

**Impact:** при включённых contextual headers (а это дефолт) hybrid-fusion может терять валидные кандидаты ещё до reranking. Тихая потеря recall, которую не видно в логах.

**Эмпирическое подтверждение (репро на реальном `HybridRetriever._rrf_merge`, 30.05):** два разных чанка одного документа (`chunk0`, `chunk1`) с общим contextual-header длиной 251 симв на входе → на выходе RRF **1 чанк** (`chunk0` схлопнут в `chunk1`). При header ≤200 симв потери нет — то есть баг срабатывает именно на длинных сгенерированных заголовках, которые contextual headers и создают.

**Fix:** строить RRF-ключ по стабильному идентификатору, а не по тексту: `metadata["doc_id"]/chunk_id` (или `chunk_id` + хэш полного `page_content`), а не по префиксу. Добавить тест с двумя чанками, имеющими общий 200-символьный префикс.

---

#### R3 — Per-document последовательный LLM-grade избыточен и медленный — **MEDIUM**

Файл: `agent/graph.py:831-918` (`make_grade_docs_node`)

`grade_docs` (CRAG) делает **отдельный `llm.invoke` на каждый документ** в цикле, последовательно (`graph.py:854`). Документы туда приходят уже после reranking (`retriever` возвращает `merged[:rerank_k]`, дефолт 5) — то есть это 5 LLM-вызовов поверх уже отранжированного cross-encoder'ом top-5. Слой во многом **дублирует** работу реранкера: и тот, и другой оценивают релевантность, но grade платит за это 5 LLM-roundtrip'ов.

**Impact:** +5 последовательных LLM-вызовов на каждый ответ. Вместе с classify/transform/HyDE/generate/verify/evaluate/suggest это даёт **~10–11 последовательных `llm.invoke` на один ответ** (см. R4) при `REQUEST_TIMEOUT_SEC=30`. Латентность и стоимость растут линейно, а маржинальная польза grade поверх reranker невелика.

**Fix (на выбор):**
- Заменить per-doc LLM-grade на **порог по rerank `relevance_score`** (он уже считается) — 0 доп. вызовов; LLM-grade оставить только как fallback при низкой уверенности реранкера.
- Либо **батчить** грейдинг в один structured-output вызов (список вердиктов) вместо N вызовов.
- Логика `preserved_top_doc` (`graph.py:902`) — корректный предохранитель, но он маскирует именно проблему «grade выкинул всё, что нашёл reranker».

---

#### R4 — LLM call fan-out на один ответ — **MEDIUM (архитектурный)**

Файлы: `agent/graph.py` узлы classify/transform(+hyde)/grade/generate/verify_facts/evaluate/suggest

**Точный счётчик (выверен чтением всех узлов, 30.05 — мой прежний «~10–11» был занижен):**

| Узел | Вызовов | Примечание |
|---|---|---|
| classify_complexity | 1 | |
| transform_query | 1 (+1 HyDE) | HyDE дефолт off |
| grade_docs | ≤5 | по 1 на каждый retrieved doc (`graph.py:854`) |
| generate | 1 | |
| **verify_facts** | **1 + N_claims** | extract (1) + по 1 на claim (≤10); consensus-режим множит на reliability_level (`graph.py:1100-1134`) |
| evaluate | 1 | |
| suggest_questions | 1 | только route=auto |
| **Итого (типичный ответ, 4 claim)** | **≈15** | все последовательные |
| + один Self-RAG retry | **+~13** | rewrite(1)+grade(5)+generate(1)+verify(5)+evaluate(1) |

**Impact:** не 10–11, а **≈15 синхронных LLM-вызовов на типичный ответ** (worst-case с retry ~28). На локальном GraceKelly/Ollama это десятки секунд; `REQUEST_TIMEOUT_SEC=30` будет регулярно срабатывать; `MAX_CONCURRENT_PIPELINES=8` × 15 вызовов = насыщение LLM-бэкенда. Это «цена» 2026-Agentic-RAG, но её стоит сделать управляемой.

**Fix:** свести R3 (минус ~5 вызовов), сделать `verify_facts`/`evaluate` опциональными для `complexity=simple`, рассмотреть параллелизацию независимых критиков. Замерить per-node латентность (трейсы уже пишут `duration_ms` на каждый `trace_llm_call` — данные есть).

---

#### R5 — Наивная токенизация BM25 для русского — **MEDIUM**

Файлы: `vectordb/_base_manager.py:199-200` (build), `219-222` (query)

BM25 строится на `chunk.page_content.lower().split()` и запрос токенизируется так же (`query.lower().split()`). Для русского это слабо: нет лемматизации/стемминга, словоформы («заказ/заказа/заказе») не схлопываются, пунктуация липнет к токенам. BM25 — keyword-половина hybrid search — на RU работает заметно хуже потенциала.

Дополнительно: BM25-индекс строится **в памяти на каждый retriever** из переданных `chunks` (`__init__:196`), т.е. зависит от того, что слой выше держит полный список чанков в RAM — не масштабируется на крупный корпус.

**Impact:** недобор keyword-recall на русском; деградация hybrid до «почти только vector».

**Fix:** токенизатор с учётом RU (хотя бы regex `\w+` + casefold + опц. `pymorphy3`/snowball-стеммер), и/или вынести лексический поиск в движок (Chroma full-text / Qdrant sparse / Elasticsearch) при росте корпуса.

---

#### R6 — Reranker жёстко на CPU — **LOW**

Файл: `vectordb/_base_manager.py:152` — `CrossEncoder(model_name, device="cpu")` хардкод. При наличии GPU не используется; с тяжёлым bge-reranker-v2-m3 (R1) это станет узким местом латентности.

**Fix:** `device` из настройки/автодетекта (`cuda`/`mps`/`cpu`).

---

### 3.3 RAG — что сделано правильно (не трогать)

- Корректный RRF с k=60, fallback-цепочки (нет BM25 → vector-only; нет reranker → top-k срез).
- HyDE/parent-child/semantic chunking за флагами с graceful degradation (`HAS_*` guards).
- `temperature=0` форсится для воспроизводимых regression-прогонов.
- На каждый LLM-step пишется provider/model/usage/cost + OTel-спан — отличная база для оптимизации латентности по R4.
- Structured-output путь в grade с fallback на текст (`graph.py:858-883`) — аккуратно.
- Self-RAG ограничен `max_iterations=2` — нет риска бесконечного retry.

---

## 4. Статус findings прошлого аудита (Codex 30.05) — сверка

Большинство уже **закрыто** коммитами после аудита Codex (git log HEAD `c2850bb`):

| Codex finding | Статус | Подтверждение |
|---|---|---|
| H1 — DOM XSS в agent UI (`innerHTML`) | **CLOSED** | `git: render agent ui api data as text`; grep: 0 `innerHTML` в `agent.html` ✔ мной |
| H2 — `devalue` npm high vuln | **CLOSED** | `git: update vulnerable docs dependency` + CI audit guard |
| M1 — нет CSP/security headers, открытый OpenAPI | **PARTIAL** | headers есть (`app.py:1769-1783`: nosniff/DENY/no-referrer/HSTS), docs gated (`_docs_enabled`); **но CSP по-прежнему отсутствует** — grep `Content-Security-Policy` пуст (подтверждено мной 30.05) |
| M2 — docker-compose как prod | **CLOSED** | `git: scope default compose to local development` |
| M3 — auto-migration fail-open | **CLOSED** | `git: fail closed on production migration errors` (`AUTO_MIGRATE_FAIL_OPEN`) |
| L1 — tar.extractall filter | **CLOSED** | `git: use safe tar extraction filter (filter="data")` |
| M4 — крупные модули, слабое покрытие | **OPEN** | `graph.py` 2105 / `api/app.py` 1932; coverage 37–56% в orchestration/auth |
| L1(rest) — deprecation (LangChain Ollama, Authlib) | **OPEN** | см. §6 |
| L2 — durable docs stale | **OPEN/частично** | AGENT_STATE обновлён, но HEAD-ассерты по-прежнему волатильны |
| L3 — раздутые ignored-кэши | **OPEN** | `.mypy_cache` 438MB и т.п. — housekeeping |

**Остаточный риск по безопасности (не RAG):** bearer token агента хранится в `localStorage` (`agent.html`). XSS-вектор закрыт, но при будущем регрессе innerHTML это снова станет захватом сессии. Рекомендация: httpOnly-cookie для agent-токена или хотя бы CSP `script-src 'self'` без inline (сейчас страницы используют inline-скрипты — проверить, что CSP реально ограничивает).

---

## 5. Остальные аспекты (кратко — детали актуальны в Codex-аудите)

- **Код/архитектура:** чистые lint/type gates. Долг сложности: `agent/graph.py` (2105) и `api/app.py` (1932) — продолжать вынос в подмодули (startup/health/vector-init/admin-services); router-split уже сделан хорошо.
- **Тесты:** 142 файла, integration-suite есть. Слабые места покрытия — ровно critical-зоны: `agent/tools.py` 37%, `auth/oidc.py` 44%, `api/routers/admin_review.py` 52%, `api/app.py` 55%. Точечные тесты ветвлений важнее, чем поднятие общего порога.
- **UX/UI:** прошлые a11y/mobile провалы (`rec.md`, апрель) закрыты — Lighthouse mobile chat: perf 99 / a11y 100; axe 38 passed. Дизайн-система всё ещё per-page CSS (не критично).
- **Observability/Ops:** сильнейшая сторона — ~50 Prometheus-метрик, OTel, alert_rules, retention purge, backup/restore с verify, Helm cronjobs (eval/review/backlog/report). Здесь добавить нечего.
- **Provider runtime:** валидация профилей/плейсхолдеров (`changeme`→missing), `DAILY_COST_LIMIT_USD`, failover GraceKelly→Ollama с кэшем — продуманно.

---

## 6. Долг актуальности (deprecation, календарный)

- `langchain_community` `Ollama`/`ChatOllama` deprecated → мигрировать на `langchain-ollama` (`agent/graph.py:213-222`, `llm/providers/ollama.py`).
- `authlib.jose` deprecated → `joserfc` (`auth/oidc.py`).
- `langchain_experimental.SemanticChunker` — experimental namespace, риск переезда API (`_base_manager.py:45`).
- Эти не ломают ничего сейчас, но это taxes-by-calendar; закрывать до того, как upstream сделает breaking.

---

## 7. Prioritized Remediation Plan

0. **R7 (HIGH, foundational):** расширить curated-датасет до 100–150 RU-кейсов → прогнать RAGAS/nightly_eval → зафиксировать baseline. *Разблокирует доказуемость всего остального; бэкенд (GK+Mistral) жив.*
1. **R1 (HIGH):** дефолтный reranker → `BAAI/bge-reranker-v2-m3`; A/B на RU curated-датасете против baseline R7, замер latency. *Самый высокий ROI по качеству ответов.*
2. **R2 (MED):** RRF-ключ по `doc_id/chunk_id`, не по префиксу контента; + регрессионный тест на общий префикс.
3. **R3+R4 (MED):** убрать per-doc LLM-grade в пользу порога по rerank-score (или батч); сделать verify/evaluate опциональными для simple; замерить per-node латентность.
4. **R5 (MED):** RU-aware токенайзер для BM25.
5. **M4 (MED):** точечные тесты на `agent/tools.py`, `auth/oidc.py`, `admin_review` + продолжить декомпозицию `graph.py`/`api/app.py`.
6. **Deprecation (LOW):** LangChain Ollama / Authlib / SemanticChunker.
7. **Housekeeping (LOW):** скрипт очистки ignored-кэшей; httpOnly для agent-токена; убрать волатильные HEAD-ассерты из durable docs.

---

## 9. Roadmap до 9.8/10 по всем фронтам

Ключевой принцип: разрыв **7.7 → 9.8 — это не новые фичи, а доказательства + доведённость**. Фич у проекта уже больше, чем у многих коммерческих. Не хватает измеренного качества и закрытия 6–7 реальных дефектов. Без метрики приёмки «9.8» — самооценка, поэтому каждая строка имеет измеримый критерий.

| Фронт | Сейчас | Что закрывает разрыв до 9.8 | Метрика приёмки |
|---|---|---|---|
| **RAG-качество** | 6.5 | R7 + R1: датасет до 100–150 RU-кейсов, RAGAS, reranker → `bge-reranker-v2-m3`, замер до/после | faithfulness ≥0.90, context-precision ≥0.85, answer-relevancy ≥0.88 на RU-сете; цифры в README |
| **RAG-пайплайн** | 8.5 | R2 (RRF-ключ), R3/R4 (порог по rerank-score вместо per-doc grade; verify/evaluate опц. для simple), R5 (RU-BM25) | p95 латентность ↓ (per-node через `duration_ms`); recall-тест на общем префиксе зелёный |
| **Backend/код** | 8.0 | Декомпозиция `graph.py`(2105)/`api/app.py`(1932) на ≤500 LOC; убрать `# type: ignore` (stubs LangChain); deprecation | mypy-strict на всём пакете (не 18 файлов); 0 deprecation warnings в pytest |
| **Тесты/CI** | 8.0 | Per-module coverage gate (`agent/tools.py` 37→85%, `auth/oidc.py` 44→85%, `admin_review` 52→85%); load-тест (k6/locust) + contract-тест API | global ≥85%, critical ≥85% per-module; load-тест в CI с зафиксированным p95 |
| **Безопасность** | 7.5 | agent-токен из `localStorage` → httpOnly-cookie; CSP `script-src 'self'` (вынести inline-скрипты); SAST (semgrep) + secret-scan (gitleaks) в CI; `threat-model.md` | CSP без `unsafe-inline`; semgrep/gitleaks зелёные; documented threat model |
| **Observability** | 9.0 | Коммитнутые Grafana-дашборды (JSON) в `monitoring/`; SLO + error-budget; per-node latency-панель | дашборд открывается из репо; SLO задокументирован |
| **Актуальность** | 8.0 | Закрыть deprecation; ADR «почему не GraphRAG сейчас»; опц. 1 frontier-метод (iterative/DeepSearch retrieval за флагом) с eval-сравнением | ADR-запись + флаг с замером |
| **UX/Продукт** | — | Проверить закрытие JS memory-leaks (`rec.md`); демо реального продукта с product-метриками (latency/recall/lighthouse), не мокап | E2E-скринкаст + product-метрики |

### Самая выгодная последовательность (по ROI)

1. **R7** — eval-фундамент (baseline). Без него RAG-улучшения недоказуемы. *Бэкенд жив → выполнимо сейчас.*
2. **R1** — reranker → `bge-reranker-v2-m3`, тот же eval → дельта. Ожидаемо крупнейший скачок faithfulness/precision.
3. **R3/R4** — срезать LLM-fan-out (порог по rerank-score) → замер латентности до/после.
4. **R2, R5** — RRF-ключ и RU-BM25 (тестируются без LLM).
5. Параллельно и независимо от RAG: backend-декомпозиция + per-module coverage + security (httpOnly/CSP/SAST).

### Runtime-замечания для eval-прогона (R7/R1)

- GraceKelly (:8011) + Mistral подтверждены живыми на 30.05 → `live`-режим доступен.
- `bge-reranker-v2-m3` ≈ 568M (vs MiniLM 22M) — будет скачан при первом запуске; на CPU проверить латентность (см. R6 — `device` сейчас захардкожен в `cpu`).
- Прогон делать раздельными python-процессами (build-eval-set → run-eval → render-report), не одним; кэшировать промежуточные артефакты — иначе page-thrash на большом числе LLM-вызовов.
- `temperature=0` форсируется для воспроизводимости (уже в коде).

---

## 8. Final Assessment

**Readiness: сильная локальная/CI-готовность; перед публичным prod-экспозом обязательны R7 (измерить качество), R1 (реранкер) и закрытие deprecation.**

Backend, observability и безопасность за последние сутки подтянуты до хорошего уровня (XSS закрыт, headers/CSP/compose/migration hardening внедрены). Два реальных, ранее не отловленных пробела — оба в RAG-слое:

1. **R7 — качество RAG не измерено**: машинерия eval first-class, но достоверных цифр (faithfulness/precision/recall) нет; 20 кейсов и 32 нулевых отчёта. Это потолок оценки.
2. **R1 — финальный precision-фильтр (reranker) работает английской моделью на русском контенте**, плюс RRF-коллизии, наивный BM25 и LLM-fan-out.

Это не «архитектура устарела» (она современна, 2026-SOTA), а «реализация недонастроена под язык и стоимость, а качество не доказано». Бэкенд (GraceKelly + Mistral) жив → R7/R1 выполнимы сейчас.

**Путь к 9.8/10** — в §9: не новые фичи, а измеренное качество + закрытие 6–7 дефектов с метриками приёмки. Реалистичная последовательность: R7 (baseline) → R1 (дельта) → R3/R4 (латентность) → backend/coverage/security параллельно.

### Самооценка аудита

После доказательного прохода: **R1, R2, R3/R4, R5 — подтверждены исполнением/выверкой (§2.1)**, статус findings Codex и UX/security проверены независимо. Остаётся один непокрытый блок — полный RAGAS-замер качества (R7), который сам по себе staged-задача с живым стеком. Аудит из «карты» стал «картой с доказательствами по каждому RAG-finding, кроме итогового eval». Граница честная и явно обозначена.

*Конец аудита. Обновлено 2026-05-30 (v3): добавлена §2.1 эмпирическая верификация (R1 измерен: gap EN 17.87 → RU 0.99; R2 репро подтверждён; R3/R4 точный счёт ≈15 вызовов; UX-leak закрыт; CSP отсутствует), R7, дорожная карта до 9.8.*
