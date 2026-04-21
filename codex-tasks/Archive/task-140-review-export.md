# Task 140 — Review export / import для single-user workflow

## Goal
Single-user workflow: user забирает review queue в local file (offline review), размечает pending cases вручную (в IDE/текстовом редакторе), возвращает обратно в систему. Важно для single-user local проекта — не хочется жить через web UI для каждого case'а.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- **Зависит от task-133** (review queue table + confirmed статусы).
- User (Julia Edomskikh) — single-user, Windows 11, Python 3.13, работает через CLI и IDE. Web admin-UI для review — overhead для одного случая.
- Формат для offline review — JSONL с полной информацией (query, answer, retrieved_docs, scores) + поля для разметки.

## Deliverables
1. **`scripts/review_export.py`**:
   - CLI: `python scripts/review_export.py --status pending --tenant <id|all> --limit 50 --out review_batch_<timestamp>.jsonl`.
   - Pулей экспорта:
     - Каждая строка JSONL — один review_case со всей контекстной информацией:
       ```json
       {
         "review_id": "<review_queue.id>",
         "trace_id": "...",
         "tenant_id": "...",
         "reason": "low_quality",
         "exported_at": "2026-04-22T10:00:00Z",
         "query": "...",
         "answer": "...",
         "final_route": "auto",
         "final_quality": 65,
         "fact_score": 72,
         "duration_ms": 3400,
         "retrieved_docs": [{"title": "...", "excerpt": "...", "source": "..."}],
         "tool_calls": [{"tool": "...", "args": "..."}],
         "citations": ["[1]", "[2]"],
         "review": {
           "verdict": null,         // "good" | "bad" | "dismiss" — fill this
           "notes": "",             // human notes
           "fix_hint": "",          // e.g. "prompt tweak / add to KB / config"
           "tags": []               // ["refund", "tier-1"]
         }
       }
       ```
     - Файл содержит комментарий-header в первой строке (не валидный JSONL, просто #):
       ```
       # review_batch exported 2026-04-22T10:00:00Z — fill `review` object per line, then: python scripts/review_import.py <this file>
       ```
2. **`scripts/review_import.py`**:
   - CLI: `python scripts/review_import.py review_batch_<ts>.jsonl [--dry-run] [--tenant-override <id>]`.
   - Читает JSONL, пропускает комментарии.
   - Для каждого case:
     - Валидирует: `review_id` existing & status=pending.
     - Если `review.verdict == "good"` → status=`confirmed_good`.
     - Если `"bad"` → `confirmed_bad`.
     - Если `"dismiss"` → `dismissed`.
     - Если null → skip.
     - Сохраняет `reviewer_notes` = `notes` + `fix_hint` concatenated.
   - `--dry-run`: показать что изменится, не применять.
   - Summary: how many updated / skipped / errored.
   - Безопасность: если `review_id` уже в status ≠ pending — skip + warn.
3. **Защита от случайной перезаписи**:
   - Запись `reviewed_by` = `"<user_email>@cli"` (из env `REVIEWER_EMAIL`, требуется).
   - Не применять если `--confirm` не задан (интерактивное предупреждение для batches > 10 cases).
4. **Git-friendly workflow** (опционально, в README):
   - Рекомендация: `review_batch_*.jsonl` в user's home или `.review_local/` (в `.gitignore`), не в repo. Но dev может хранить в отдельной branch если хочет.
5. **Tests** (`tests/test_review_export_import.py`) — 6+ тестов:
   - Export создаёт JSONL с ожидаемой структурой.
   - Export фильтрует по `--status pending --tenant`.
   - Import с `verdict="good"` → `status=confirmed_good`.
   - Import с null verdict → skip, no change.
   - Dry-run не меняет БД.
   - Conflict: review уже confirmed_bad, import снова → warning, не перезаписывает.

## Acceptance
- `python scripts/review_export.py --limit 5` создаёт валидный JSONL.
- Редактировать JSONL в редакторе → `python scripts/review_import.py <file>` применяет verdicts.
- `pytest tests/test_review_export_import.py` — зелёный.
- `.gitignore` содержит `review_batch_*.jsonl` (чтобы случайно не закоммитить review data).
- pytest ≥ 327 + 6 new = 333+. Ruff clean.
- README раздел "Offline review workflow".

## Notes
- **Blocked by**: task-133 (review_queue).
- **Parallel-safe with**: task-134, task-135, task-136, task-137, task-138, task-139.
- **Blocks**: — (tail).
- Формат JSONL, не CSV: nested structures (retrieved_docs, tool_calls) читабельнее.
- Защита от случайного `review_id` collision: UUID проверяется, не int range.
- Не делать GUI — CLI + текстовый редактор это ровно то, что нужно для single-user.
- `REVIEWER_EMAIL` env var — required; без него падать с hint.
