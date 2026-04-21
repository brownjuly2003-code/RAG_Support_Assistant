# Task 134 — Curated dataset builder из подтверждённых review-case'ов

## Goal
Превращать review-case'ы, прошедшие human-confirmation, в reusable eval dataset с input/expected-поведением. Curated dataset — топливо для regression runner (task-136) и provider benchmark'а.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- **Зависит от task-133** (review_queue table + `confirmed_good`/`confirmed_bad` статусы).
- Уже есть: `evaluation/` модуль (task-108 nightly RAGAS), `scripts/nightly_eval.py`, schema traces с `state_json` (полный dump LangGraph state). В state_json лежат retrieved_docs, tool_calls, answer, quality_scores.
- Текущий eval dataset для RAGAS — непонятно, scripted или curated; нужна отдельная curated очередь, явно маркированная human review.

## Deliverables
1. **`scripts/build_curated_dataset.py`**:
   - CLI: `python scripts/build_curated_dataset.py --tenant <id|all> --since YYYY-MM-DD --out evaluation/curated_cases.jsonl --include-bad`.
   - Берёт из `review_queue`: `status IN ('confirmed_good','confirmed_bad')` (если `--include-bad` иначе только good).
   - Для каждого конвертирует в JSONL запись:
     ```json
     {
       "case_id": "trace-<trace_id>",
       "tenant_id": "...",
       "input": {"query": "...", "context_hint": "...", "channel": "web|telegram|email"},
       "expected": {
         "answer_contains": ["..."],
         "answer_not_contains": ["..."],
         "route": "auto|human",
         "min_quality": 70,
         "min_factuality": 70,
         "citations_min_count": 1
       },
       "human_verdict": "good|bad",
       "reviewer_notes": "...",
       "source_trace_id": "...",
       "created_at": "..."
     }
     ```
   - `expected.answer_contains` / `_not_contains` — извлекать из `reviewer_notes` или через простой heuristic: для good case — n-grams из answer'а; для bad case — оставить пустыми (только `route` и thresholds).
   - Идемпотентность: при повторном запуске dedup по `case_id`.
2. **`evaluation/curated_cases.jsonl`** — создать пустой файл с `.gitkeep` логикой (фактически placeholder, data будут записываться runtime).
3. **`evaluation/dataset.py`**:
   - `load_curated_cases(path: Path) -> list[CuratedCase]` — pydantic model.
   - `split_cases(cases, ratio=0.8) -> tuple[train, eval]` — stable sort + deterministic split по `case_id` hash.
   - `filter_cases(cases, tenant=None, tags=None, since=None) -> list[CuratedCase]`.
4. **Admin endpoint**:
   - `GET /admin/curated-dataset/stats` — count good/bad, per-tenant breakdown, по каналам.
   - `POST /admin/curated-dataset/rebuild` — триггер `build_curated_dataset.py` async, возвращает job_id. Прогресс через tracker в Redis.
5. **Prometheus**: `curated_dataset_size{verdict,tenant}`, `curated_dataset_last_build_timestamp_seconds`.
6. **Tests** (`tests/test_curated_dataset.py`) — 7+ тестов:
   - `build_curated_dataset.py` создаёт JSONL с confirmed cases.
   - `--include-bad` добавляет bad cases, без флага — только good.
   - Dedup при повторном запуске.
   - `load_curated_cases` парсит JSONL в pydantic модели.
   - `split_cases` детерминистичен (same input → same split).
   - `filter_cases` по tenant/since.
   - `/admin/curated-dataset/stats` возвращает counts.
7. **README** — секция "Curated dataset" + команда rebuild.

## Acceptance
- На seed'е review_queue со смешанными confirmed cases — `build_curated_dataset.py` создаёт валидный JSONL ≥1 строка.
- `pytest tests/test_curated_dataset.py -v` — зелёный.
- `evaluation/curated_cases.jsonl` можно импортировать из `scripts/nightly_eval.py` (не ломать его).
- pytest ≥ 327 + 7 new = 334+. Ruff clean.
- Секция README описывает формат JSONL и workflow.

## Notes
- **Blocked by**: task-133 (нужен `review_queue` с confirmed_* статусами).
- **Blocks**: task-136 (regression runner потребляет curated_cases.jsonl), task-140 (review export).
- **Parallel-safe with**: task-135, task-137, task-139.
- Pydantic model для `CuratedCase` — в `evaluation/dataset.py`, не в global models.
- JSONL, не JSON: легче append, легче diff в git.
- Не автоматически промоутить trace в curated — только через `review_queue.status` confirmation.
- Для `answer_contains` heuristic — n-grams длиной 2-3 слова, filtered stopwords; не перебарщивать с точностью.
