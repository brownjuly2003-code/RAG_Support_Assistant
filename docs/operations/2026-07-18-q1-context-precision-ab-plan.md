# Q1 — context_precision A/B (offline, 100-case aircargo) — run plan

- Дата: 2026-07-18.
- Аудит-источник: `audit_grok_16_07_26.md` — finding **Q1** (§1 Top-5, §7.1–7.3,
  §14, §16 Q1a). RAGAS baseline (2026-06-05,
  `reports/ragas/20260605T214926Z-e728353a-aircargo-ragas.md`):
  **context_precision ≈ 0.51** (слабое звено — в top-k много шума),
  **context_recall ≈ 0.92** (отлично), faithfulness 0.766, answer_relevancy 0.833.
- Продуктовая ставка аудита (дословно §17): «attack context_precision with a
  *measured* A/B on the existing 100-case aircargo harness — **not new retrieval
  strategies**». Рычаги §7.2/§7.3: **rerank top-k, grade_docs, parent-window
  expansion chars**, на тех же 100 кейсах.
- Scope: подготовка. **Тяжёлый прогон — на Mac, одной командой.** На Windows
  гоняется только mock-smoke (без моделей). Продакшн-дефолты НЕ меняются — A/B
  варьирует ручки только внутри своих arm'ов.

## Что это НЕ

- Не новый retrieval-strategy (factcard/GraphRAG/router — за своими гейтами, §13
  non-goals). Не CI-gate (это отдельный шаг Q1b). Не меняет
  `config/settings.py` / `agent/graph.py` / прод-поведение.

## Артефакты

- Скрипт: `scripts/ab_context_precision.py` (новый).
- Тест (pure-logic): `tests/test_ab_context_precision.py` (новый, 7 passed).
- Этот run-doc.

## Переиспользование (не реимплементация)

| Что | Откуда берётся |
|---|---|
| embed (BGE-M3) + RRF-пул + rerank (bge-reranker-v2-m3) | `scripts/ab_remote_contextual.py` `--stage pools/rerank --arm C` (два процесса — модели не резидентны одновременно) |
| parent-window expansion | `vectordb._base_manager.HybridRetriever._expand_parents` (+ `select_chunks`, `vectordb.manager.add_contextual_headers`) — чистый текст, без моделей |
| grade_docs (CRAG-фильтр) | `agent.graph.make_grade_docs_node` (реальный прод-узел; LLM = external-mistral) |
| context_precision / context_recall | `evaluation.ragas_eval.context_precision` / `context_recall` (тот же код, что дал baseline 0.51) |
| keyword FULL/PART/MISS guard | `scripts.ab_remote_contextual._kw_status` (метрика D2-baseline) |
| faithfulness / answer_relevancy (opt-in judge) | `evaluation.ragas_eval.RAGEvaluator` + `scripts.aircargo_ragas_free.FreeChatLLM/_generate_answer` (external-mistral) |

Тяжёлый embed+rerank выполняется **один раз**; каждый arm — дешёвый
post-processing над одним и тем же reranked-пулом (slice → expand → grade),
поэтому вся сетка стоит примерно как один прогон ретривера.

## Сетка arm'ов (8; 6 детерминированных + 2 opt-in grade)

Дизайн: one-factor-at-a-time вокруг прод-дефолта + 2 комбинированных + 2 grade.
Прод-дефолты (`config/settings.py`): `rerank_top_k=5`, `parent_expansion` on
`window=2 / max_chars=3600`. Arm `prod` = D2 baseline (keyword FULL 96 / PART 3 /
MISS 1, `2026-06-13-adaptive-retrieval-phase0.md`).

| arm | rerank_k | window/max_chars | grade | зачем |
|---|---:|---|:---:|---|
| **prod** | 5 | 2/3600 | — | текущий прод (D2) — reference |
| k3 | 3 | 2/3600 | — | уже top-k → precision↑, риск recall |
| k8 | 8 | 2/3600 | — | шире top-k → проверка recall-headroom |
| no-expand | 5 | off | — | изолирует precision-цену parent-window |
| light-expand | 5 | 1/2400 | — | консервативная экспансия (rollback-config из settings) |
| k3-light-expand | 3 | 1/2400 | — | комбинированная ставка на precision |
| grade | 5 | 2/3600 | on | CRAG-фильтр поверх прод (opt-in, external-mistral) |
| k3-grade | 3 | 2/3600 | on | уже top-k + CRAG (opt-in, external-mistral) |

Механика precision: `context_precision` — rank-weighted (1/rank) доля
query+expected-keyword'ов в каждом doc'е; меньше k и меньше «размывающего»
текста → выше precision, а recall/FULL — страховочные ручки. Порядок в каждом
arm'е точно как в проде: rerank → slice top-k → parent-expand → (grade).

## SHIP / NO-SHIP

Критерии (в скрипте — `ShipCriteria`, печатаются в отчёте):

- **context_precision** вырос осмысленно: **Δ ≥ +0.05** абсолютно vs `prod`
  (движение к commercial RQ-2 ≥0.8; сам порог 0.8 — цель Q1b, не этого шага).
- **context_recall не ниже ~0.90** (baseline ~0.92–0.975; страховка от «зарезали
  шум вместе с сигналом»).
- **keyword FULL ≥ 96 и MISS ≤ 1** — без регрессии vs D2 (96/3/1).

Arm проходит все три → `SHIP-CANDIDATE`. Иначе → `no-ship` с причиной.
**NO-SHIP — валидный исход**: если ни один arm не поднимает precision без пробоя
recall/FULL, прод-дефолты остаются как есть (дисциплина Phase-5, §3 «evidence
culture»). Никакой правки `settings.py` этот скрипт не делает и не предполагает
до отдельного решения владельца.

## Прогон на Mac — ОДНА команда

Рецепт (AGENT_STATE.md, «Mac-прогон recipe», 2026-06-14 Track F/F1):
SSH `deproject-mac` (192.168.1.133, key-based), репо `~/RAG_Support_Assistant`,
venv `.venv` (py3.11), профиль `external-mistral`. Ключ Mistral — из
`D:\TXT\Mistral_API.txt`, передаётся в `/tmp/mk.env` **без печати значения**.

```bash
# 0) с Windows: положить ключ на Mac (значение не печатается)
key=$(grep -oE '[A-Za-z0-9_-]{28,}' /d/TXT/Mistral_API.txt | head -1)
printf 'export MISTRAL_API_KEY=%s\n' "$key" | ssh deproject-mac 'cat > /tmp/mk.env && chmod 600 /tmp/mk.env'

# 1) на Mac
ssh deproject-mac
cd ~/RAG_Support_Assistant && git pull --ff-only

# 2) ОДНА команда: строит пул (embed+rerank, два процесса) + гоняет всю сетку
set -a && . /tmp/mk.env && set +a && \
RAG_DEVICE=mps RAG_EMBED_BATCH=8 RAG_RERANK_BATCH=8 \
LLM_PROVIDER_PROFILE=external-mistral OLLAMA_REQUEST_TIMEOUT_SEC=120 \
.venv/bin/python scripts/ab_context_precision.py --build-pool \
    --with-grade --with-judge --results-dir reports/ragas

# 3) вычистить ключ
rm -f /tmp/mk.env
```

`--build-pool` внутри запускает `scripts/ab_remote_contextual.py --stage pools
--arm C` затем `--stage rerank --arm C` (эмбеддер и реранкер — в отдельных
процессах, не резидентны вместе; батчи 8 под 8 GB unified memory). Результат —
`reports/ragas/<run_id>-q1-context-precision-ab.{json,md}` + строка-summary в
stdout со списком `ship_candidates`.

Варианты:
- **Дёшево, без LLM** (только context_precision/recall + FULL/PART/MISS по всем 6
  детерминированным arm'ам): убрать `--with-grade --with-judge` и `/tmp/mk.env` —
  ключ не нужен.
- **Пул уже построен** (`.tmp/ab_candidates_phase2_C.json` есть): убрать
  `--build-pool`, добавить `--rerank-artifact .tmp/ab_candidates_phase2_C.json`.
- **Fallback без one-command**: три шага руками —
  `ab_remote_contextual.py --stage pools --arm C` →
  `... --stage rerank --arm C` →
  `ab_context_precision.py --rerank-artifact .tmp/ab_candidates_phase2_C.json [...]`.
- Если Mac занят/долго — Kaggle (штатный путь проекта, см. AGENT_STATE Phase-5).

## Ожидаемое время (mps, batch 8)

| Этап | Оценка |
|---|---|
| pools C (embed корпуса aircargo, ~сотни чанков) | ~3–6 мин |
| rerank C (100 кейсов × RRF-пул) | ~3–8 мин |
| детерминированная сетка (6 arm'ов, slice+expand+метрики) | секунды |
| grade arm'ы (2 × 100 кейсов, 1 batch-LLM/кейс, mistral-small) | ~5–10 мин |
| judge (baseline + winner × 100 кейсов × generate+faithfulness+relevancy) | ~15–25 мин |
| **итого `--with-grade --with-judge`** | **~30–50 мин** |
| **итого детерминированный (без LLM)** | **~10–15 мин** |

Стоимость: только opt-in LLM-слои платные (mistral-small, суб-долларовый
порядок на 100 кейсов; judge/grade spacing `min_interval` встроен).

## Smoke на Windows (сделано, без моделей)

```
python scripts/ab_context_precision.py --mock --stub-grade --results-dir .tmp/q1_smoke
```

- 3 mock-кейса (FULL/–/MISS), `NullExpander` (без корпуса), grade — офлайн-стаб
  `_StubGradeLLM` через **реальный** `make_grade_docs_node` (доказывает
  plumbing state→graded_docs: `prod` ctx_precision 0.2452 → `grade` 0.2727 —
  стаб отфильтровал IRRELEVANT-док). Все 8 arm'ов + таблица + verdict'ы рендерятся.
- Pure-logic тест: `python -m pytest tests/test_ab_context_precision.py -q
  -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-q1` → **7 passed**.
- `ruff check scripts/ab_context_precision.py tests/test_ab_context_precision.py`
  → All checks passed.

На Windows тяжёлый путь (`--build-pool`, реальный `--with-grade/--with-judge`) НЕ
запускается: guard-правило «no heavy на Windows», embed/rerank/LLM только на Mac.

## После прогона

1. Прочитать `reports/ragas/<run_id>-q1-context-precision-ab.md` — таблица +
   verdict по каждому arm'у.
2. Если есть `SHIP-CANDIDATE` — это КАНДИДАТ, не мёрж: решение о смене дефолтов
   (`RAG_RERANK_TOP_K` / `RAG_PARENT_EXPANSION_*` / grade) — за владельцем,
   отдельным PR, с этим отчётом как evidence.
3. Если пусто — NO-SHIP, дефолты не трогаем; зафиксировать факт в закрытии Q1a.
4. Дальше (не в этом scope): Q1b — nightly RAGAS drift job + CI quality floor
   (§16, только после того как precision осмысленно сдвинулся).
