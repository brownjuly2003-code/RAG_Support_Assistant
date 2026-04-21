# Task 135 — Prompt / experiment registry

## Goal
Versioning и registry для промптов, модельных настроек, retrieval flags. Каждое изменение (prompt / model / top_k / reranker / hybrid / hyde) — это experiment с ID, metadata и ссылкой на regression run. Без registry изменения делают "наощупь" и результаты не сопоставимы.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- Текущие промпты: `agent/prompts.py` (модуль с константами / templates). Нет версии, нет истории.
- Текущие retrieval flags: `config/settings.py` — `hybrid_search`, `semantic_chunking`, `contextual_headers`, `agentic_mode`, `retrieval_top_k`, `rerank_top_k`, `rrf_k`, `quality_threshold`, etc.
- Еval history: `scripts/nightly_eval.py` пишет в `eval_results` таблица (migration 005).

## Deliverables
1. **`evaluation/experiments/`** директория + пустой `.gitkeep`.
2. **`evaluation/experiment_schema.py`**:
   - Pydantic `Experiment` model:
     ```python
     class Experiment(BaseModel):
         id: str  # slug: "2026-04-22-prompt-concise-answers"
         name: str
         created_at: datetime
         created_by: str  # user email / "system"
         description: str
         prompt_overrides: dict[str, str]  # key → full text
         settings_overrides: dict[str, Any]  # e.g. {"retrieval_top_k": 10}
         parent_experiment_id: str | None  # предок
         status: Literal["draft", "running", "completed", "deployed", "archived"]
         tags: list[str]
     ```
   - `load_experiment(path) -> Experiment`, `save_experiment(exp, path)`.
3. **`scripts/experiment_new.py`**:
   - CLI: `python scripts/experiment_new.py --name "concise-answers" --from <parent_id|current> --description "..."`.
   - Создаёт `evaluation/experiments/<id>.yaml` с полным snapshot текущих prompts + settings (или от parent, если указан).
   - Status = `draft` по умолчанию.
4. **`scripts/experiment_apply.py`**:
   - CLI: `python scripts/experiment_apply.py <exp_id> --mode <dry-run|stage|deploy>`.
   - `dry-run` — печатает diff vs current.
   - `stage` — создаёт `config/experiment_override.yaml` с overrides; settings loader читает его при `EXPERIMENT_ID=<id>` env.
   - `deploy` — merge overrides в `config/settings.py` / `agent/prompts.py` (writes + git diff summary), меняет status=`deployed`.
5. **`config/settings.py`**:
   - Settings loader читает `config/experiment_override.yaml` если `EXPERIMENT_ID` env задан, merges over defaults.
   - Изменение: поведение backward-compatible — без env ничего не применяется.
6. **Admin endpoint**:
   - `GET /admin/experiments` — список experiments + status + latest eval link.
   - `GET /admin/experiments/{id}` — full details.
   - `POST /admin/experiments/{id}/archive` — status=`archived`.
7. **Prompt registry** (`agent/prompts.py`):
   - Каждая prompt-константа получает `prompt_id: str` суффикс (например `SUMMARIZE_PROMPT_V1`, `REWRITE_PROMPT_V1`).
   - `agent/prompt_registry.py`: функция `get_prompt(name: str, experiment: Experiment | None = None) -> str` — возвращает override из experiment или default.
   - Существующие потребители `agent/graph.py` переведены на `get_prompt("summarize", experiment)` вместо прямого import.
8. **Tests** (`tests/test_experiment_registry.py`) — 6+ тестов:
   - `Experiment` pydantic валидация.
   - `experiment_new.py` создаёт YAML от `current`.
   - `experiment_new.py --from <parent>` копирует overrides.
   - `experiment_apply.py --mode dry-run` не меняет файлы.
   - `experiment_apply.py --mode stage` создаёт override YAML; settings читает его.
   - `get_prompt` возвращает override если в experiment, default иначе.
9. **README** — раздел "Experiments" с workflow (new → apply stage → eval → deploy).

## Acceptance
- `python scripts/experiment_new.py --name test-concise` создаёт валидный YAML.
- `EXPERIMENT_ID=<id> python -c "from config.settings import get_settings; print(get_settings().retrieval_top_k)"` показывает override.
- `pytest tests/test_experiment_registry.py` — зелёный.
- Существующие тесты (arc 102-122) не сломаны.
- pytest ≥ 319 + 6 new = 325+. Ruff clean.

## Notes
- **Parallel-safe with**: task-133, task-134, task-137, task-139.
- **Blocks**: task-136 (regression runner ссылается на experiment_id).
- YAML для experiments (не JSON): человеку проще редактировать вручную в dev-цикле.
- experiment_id slug format: `YYYY-MM-DD-<name-slug>`, все lowercase, `-` разделители.
- Не превращать `experiment_apply deploy` в автоматический merge в git — только file changes + printed summary; commit делает user.
- Не ломать существующую логику загрузки settings — override только при явном `EXPERIMENT_ID` env.
