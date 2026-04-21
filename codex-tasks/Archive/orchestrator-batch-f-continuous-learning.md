# Orchestrator — Batch F (Continuous Learning Lab, arc 6)

## Overview
8 tasks (133-140) замыкают learning loop вокруг существующих traces/feedback/KB tooling. Foundation — review queue; над ним строятся curated dataset, regression eval, backlog. Experiment registry — параллельный трек. Evaluators и threshold analyzer — независимые дополнения.

## Tasks
| # | Task | Blocked by | Parallel with | Est. hours |
|---|------|------------|----------------|-----------|
| 133 | Review queue | — | 135, 137, 139 | 4-5 |
| 134 | Curated dataset builder | 133 | 135, 137, 139 | 3-4 |
| 135 | Prompt/experiment registry | — | 133, 137, 139 | 4-5 |
| 136 | Regression runner | 134 + 135 | 137, 138, 139, 140 | 5-6 |
| 137 | Online evaluators | — | 133, 134, 135, 138, 139, 140 | 4-5 |
| 138 | Weekly improvement backlog | 133 | 135, 136, 137, 139, 140 | 3-4 |
| 139 | Threshold recommendations | — | все кроме себя | 3-4 |
| 140 | Review export/import | 133 | 134, 135, 136, 137, 138, 139 | 2-3 |

## Recommended execution order

### Round 1 (parallel, 4 tasks) — foundation + independent tracks
Запустить параллельно:
- **task-133** (review queue) — критичный foundation.
- **task-135** (experiment registry) — независимый трек.
- **task-137** (online evaluators) — независимый.
- **task-139** (threshold recommendations) — независимый.

Ждать завершения всех 4 перед Round 2.

### Round 2 (parallel, 3 tasks) — зависят от 133
После merge task-133:
- **task-134** (curated dataset) — needs review_queue confirmed statuses.
- **task-138** (weekly backlog) — needs review_queue source.
- **task-140** (review export/import) — needs review_queue CRUD.

### Round 3 (1 task) — финальный gate
После merge task-134 и task-135:
- **task-136** (regression runner) — needs curated dataset + experiment registry.

## Commit & verify strategy
После каждого Round:
1. `pytest tests/ -q` — все зелёные.
2. `ruff check .` — clean.
3. Verification sweep per task по acceptance criteria (прочитать spec-файл, проверить evidence в коде).
4. Commit отдельно per task (НЕ merge-commit batch'ем — легче bisect'ить регрессию).
5. Если Codex клеймит "done" но acceptance не покрыта — написать fix-task (как task-130/131/132).

## Success criteria для Arc 6
- 319 tests → ~370+ passing (8 tasks × ~6 tests each = 48+ new).
- Ruff clean.
- Working tree clean.
- Все 8 тасков в Archive/.
- README содержит разделы: Review queue, Curated dataset, Experiments, Regression eval, Online evaluators, Improvement backlog, Threshold tuning, Offline review workflow.
- `reports/` директория содержит реальные свежие artifacts (улучшения backlog, threshold recs, regression reports).

## Out of scope Arc 6
- Provider abstraction (Claude/Gemini/OpenAI backends) — Candidate C of arc-6 proposal, возможный arc-7.
- Production backup/restore/chaos — Candidate B, возможный arc-7.
- Voice / WhatsApp channels — не канала задача, а learning задача.

## Risks / watchouts
- **Feedback шум**: review queue легко переполнить false positives. Threshold default должен быть консервативным (quality<80 → review; перестраиваемо через task-139).
- **Curated dataset переобучение**: при <50 cases regression runner даст нестабильный signal. В ранние недели — не gating, informational.
- **Experiment override mechanism**: если забыть сбросить `EXPERIMENT_ID` env — прод будет крутить staged experiment. Fail-fast на старте в production если `EXPERIMENT_ID` set + `RAG_ENV=production` (add to settings.validate).
- **Online evaluators perf**: timeout 500ms на trace total. Если больше — skip с warning, не блокируем pipeline.
- **Regression runner нестабильность**: `temperature=0` обязателен, иначе Ollama даёт вариативность и regression шумный.
