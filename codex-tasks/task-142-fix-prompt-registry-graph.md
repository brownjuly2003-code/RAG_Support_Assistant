# Task 142 — Fix: route agent/graph.py through prompt_registry.get_prompt (gap task-135)

## Goal
Task-135 (batch F) реализовал `agent/prompt_registry.py` с `get_prompt(name, experiment)`, который умеет возвращать override из staged experiment YAML. Но `agent/graph.py` продолжает импортировать prompts напрямую — staged experiments в deploy-lifecycle (stage-mode через `EXPERIMENT_ID` env) не достигают runtime pipeline'а. Эффект: experiment registry виден в admin UI, но в pipeline не действует до `deploy`-mode. Без этого фикса task-135 наполовину фасад.

## Context
- Repo: `D:\RAG_Support_Assistant`.
- HEAD — первый коммит арки 6 batch F (task-135 зафиксирован partial; этот спек закрывает gap).
- Существующее:
  - `agent/prompts.py` — `PROMPT_REGISTRY: dict[str, dict[str, str]]` (id + full text per promp-name) и `DEPLOYED_PROMPT_OVERRIDES: dict[str, str]` (deploy-mode overrides).
  - `agent/prompt_registry.py` — `get_prompt(name, experiment=None)` с priority: experiment arg → staged YAML (при `EXPERIMENT_ID` env) → `DEPLOYED_PROMPT_OVERRIDES` → `PROMPT_REGISTRY[name]["text"]`.
  - `config/settings.py:649` — читает `EXPERIMENT_ID` + `config/experiment_override.yaml` для settings overrides (retrieval_top_k и т.п.) — работает.
- Проблема: `agent/graph.py` импортирует промпты напрямую (`from agent.prompts import SUMMARIZE_PROMPT_V1` или аналогично). Staged prompt overrides из `experiment_override.yaml` никогда не читаются pipeline'ом. Только `DEPLOYED_PROMPT_OVERRIDES` (обновляется через `experiment_apply.py --mode deploy`, который делает in-place write в `agent/prompts.py`) реально меняет runtime.

## Deliverables

### 1. Перевод `agent/graph.py` на `get_prompt()`
- Выявить все места импорта prompts (grep `from agent.prompts import`, `from .prompts import`).
- Для каждого usage:
  - Заменить импорт константы на вызов `from agent.prompt_registry import get_prompt`.
  - В месте использования — `prompt_text = get_prompt("<name>", experiment)`.
- Experiment prop'огируется через LangGraph state (опция A — чище) или через thread-local / ContextVar на время pipeline'а (опция B — минимальная инвазия).
  - **Рекомендовано опция B**: при входе в pipeline (в `run_qa_pipeline` или эквиваленте) — один раз загрузить experiment через `load_current_experiment()` (новый helper, читает `EXPERIMENT_ID` env + YAML, возвращает `Experiment | None`), положить в `ContextVar`. `get_prompt()` без аргумента `experiment` читает ContextVar.
  - Требование: `get_prompt(name)` без experiment должен возвращать staged override если `EXPERIMENT_ID` set, иначе default.

### 2. Расширение `agent/prompt_registry.py`
- Добавить `CURRENT_EXPERIMENT: ContextVar[Experiment | None] = ContextVar("current_experiment", default=None)`.
- Helper `load_current_experiment() -> Experiment | None` — возвращает Experiment pydantic из staged YAML (если `EXPERIMENT_ID` env set и файл есть), иначе `None`.
- Helper `set_current_experiment(exp: Experiment | None)` → token для reset.
- `get_prompt(name, experiment=None)` — если experiment не передан, берёт `CURRENT_EXPERIMENT.get()`.

### 3. Pipeline entry point
- В `agent/graph.py` (либо в каком-то edge entry'а, где стартует `run_qa_pipeline`) — на входе:
  ```python
  token = set_current_experiment(load_current_experiment())
  try:
      ...pipeline body...
  finally:
      CURRENT_EXPERIMENT.reset(token)
  ```
- ContextVars asyncio-safe, per-request isolation работает.

### 4. Integration test `tests/test_prompt_registry_integration.py`
Новый файл, минимум 3 теста:
- `test_graph_uses_default_prompt_without_experiment_id` — `EXPERIMENT_ID` unset, pipeline-level invocation → prompt = default из `PROMPT_REGISTRY`.
- `test_graph_uses_staged_override_when_experiment_id_set` — `EXPERIMENT_ID=test-xyz`, `config/experiment_override.yaml` содержит `prompt_overrides: {summarize: "OVERRIDE"}`, pipeline → prompt = "OVERRIDE".
- `test_experiment_context_isolated_per_task` — concurrent pipeline runs с разными experiments не leak'ают друг в друга (запустить 2 asyncio tasks с monkey-patched ContextVar values, проверить).

Mock LLM calls в тестах — не нужен реальный Ollama.

### 5. Обновление существующего `tests/test_experiment_registry.py`
Возможно есть тест который проверяет что `agent/graph.py` НЕ использует `get_prompt` (отрицательный). Обновить если есть. Иначе — не трогать.

### 6. Документация
- `README.md` раздел "Experiments" — добавить предложение про stage-mode: "В stage-mode `EXPERIMENT_ID` env + `config/experiment_override.yaml` сразу применяется к pipeline'у на следующем запросе — runtime переключается без git-правок."

## Acceptance
- `pytest tests/test_prompt_registry_integration.py` — зелёный.
- `pytest tests/test_experiment_registry.py` — остаётся зелёным.
- `pytest tests/ -q` — не должно появиться регрессий vs prev HEAD.
- `ruff check .` — clean.
- Manual: `EXPERIMENT_ID=test-xyz` + `config/experiment_override.yaml` с `prompt_overrides` → запрос в `/chat` → pipeline видит override (можно verify через trace `state_json.prompts_used` или подобный debug output).

## Notes
- **Parallel-safe с task-141**: файлы пересекаются только в `agent/graph.py` — оба трогают этот файл. Рекомендовано запускать 141 и 142 последовательно, не параллельно. Либо выделить separate Codex-сессии и смержить diff вручную.
- **Не трогать `DEPLOYED_PROMPT_OVERRIDES`** — это deploy-mode, оставляем как есть, stage-mode уровень ниже deploy в priority chain (уже в `get_prompt`).
- **ContextVars per-loop** — уже использованы в этом репо (`get_request_id`), паттерн знаком.
- **После успеха** — переместить этот фикс-спек в `codex-tasks/Archive/`.
