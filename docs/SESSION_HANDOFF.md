# Session handoff

**Обновлено:** 2026-08-03

**Назначение:** короткий источник истины для следующей Codex-сессии. История
решений остаётся в [`AGENT_STATE.md`](../AGENT_STATE.md), активный порядок работ
— в [`BACKLOG.md`](../BACKLOG.md) и [`plan_sol_23_07_26`](../plan_sol_23_07_26).

## Вход в следующую сессию

1. Выполнить `git status --short --branch` и `git log -5 --oneline`.
2. Прочитать верхний блок `AGENT_STATE.md`, этот handoff и верх `BACKLOG.md`.
3. Считать `git status` авторитетнее сохранённых hash/count, если они разошлись.
4. Не начинать больше одного атомарного среза за пользовательский turn.

Последняя завершённая реализация — `f899ba5` (`feat(config): add index
retention budget`); status rollup — `8d93ded`. Текущий HEAD может быть новее
только на docs-only handoff-коммит. Ветка содержит локальные непушенные коммиты;
push/deploy не разрешены автоматически.

## Текущее состояние шага 4.8d

Локально реализованы и проверены:

- atomic manifest publish и validated rollback;
- trusted tenant-bound retention inventory;
- строгий bounded policy `max_versions >= 2`;
- fail-closed executor с последовательным prune inventory;
- lazy Chroma adapter, где только `NotFoundError` считается idempotent success;
- `VECTORDB_RETENTION_MAX_VERSIONS` с default `2` (active + previous).

Настройка бюджета читает env лениво. Пустое, дробное или нечисловое значение
останавливает создание `Settings`; целое значение `< 2` останавливает
`Settings.validate()` до dependency/network probe.

## Что пока не реализовано

- `vectordb/manager.py` не импортирует и не вызывает
  `record_retention_collection` или `execute_chroma_retention`;
- production publish flow не записывает новую versioned collection в retention
  inventory;
- runtime не запускает bounded deletion после publish;
- нет operator endpoint/CLI для retention и rollback;
- нет immutable/versioned original uploads и расширенного fault injection;
- live PostgreSQL/Redis/Celery/Chroma drills не выполнялись.

Следовательно, конфигурация retention сейчас валидируется, но не меняет runtime
поведение. Ни один реальный Chroma client не создавался для retention; коллекции
не перечислялись, не открывались и не удалялись.

## Проверка последнего implementation-среза

- TDD: 8 ожидаемых failures до реализации, затем 8 focused passes.
- Смежный gate: **99 passed**, две известные deprecation-warning (Starlette/httpx
  и LangChain `Ollama`).
- Scoped Ruff: clean.
- Python 3.11 + mypy 1.19.1 + NumPy 2.4.4 для `config/settings.py`: clean.
- Прямой Python 3.11 contract для default/override/malformed/range: passed.
- Count/boundary search подтвердил: новый setting встречается только в config,
  docs и tests, runtime consumer отсутствует.
- `git diff --check` для implementation и status commits: clean.

Воспроизводимые локальные команды:

```powershell
$handoffTests = @(
    "tests/test_retention_settings.py"
    "tests/test_index_retention.py"
    "tests/test_chroma_retention.py"
    "tests/test_index_version_manifest.py"
    "tests/test_index_staging.py"
    "tests/test_index_runtime_switch.py"
    "tests/test_chunks_restore.py"
    "tests/test_tenant_index_lock.py"
    "tests/test_provider_settings.py"
    "tests/test_magic_numbers_settings.py"
    "tests/test_settings_production_secrets.py"
)
python -m pytest $handoffTests -q -p no:cacheprovider --basetemp=.tmp/pytest-4.8d3e
python -m ruff check config/settings.py tests/test_retention_settings.py
uv run --isolated --python 3.11 --with mypy==1.19.1 --with numpy==2.4.4 python -m mypy config/settings.py --no-incremental --show-error-codes
```

Pytest на этом Windows-host нужно запускать с уникальным ignored basetemp,
например `--basetemp=.tmp/pytest-<slice>`: глобальный
`C:\Users\uedom\AppData\Local\Temp\pytest-of-uedom` недоступен. Не повторять
сырой aggregate без этой коррекции.

Полный `requirements-dev.lock` сейчас не разрешается через `uv` на Windows:
unmarked `nvidia-cufile==1.15.1.6` имеет только Linux wheels. Это отдельная
portability-задача; не маскировать её изменением retention-кода и не делать
повторные raw install attempts без нового диагностического среза.

## Рекомендуемый следующий локальный срез

**4.8d3f — publication inventory wiring only (не начат).**

Цель: под существующим tenant lock добавить новую успешно validated versioned
collection в trusted inventory как часть publish workflow. В этом срезе не
запускать Chroma deletion и не добавлять operator API.

Перед реализацией зафиксировать тестами failure semantics вокруг двух durable
операций — inventory record и manifest publish:

- ошибка inventory write не должна менять active manifest;
- ошибка manifest publish не должна оставлять живой unpublished candidate;
- код не должен удалять collection, которая уже стала manifest-active;
- stale inventory entry после cleanup, если выбран такой порядок операций,
  должна быть явно доказана безопасной для будущего idempotent prune;
- Qdrant и fact-card paths не должны затрагиваться;
- runtime не должен list/get неизвестные Chroma collections.

Точки входа: `vectordb/manager.py`, `vectordb/index_retention.py`,
`tests/test_index_runtime_switch.py`, `tests/test_index_retention.py`.
После green focused gate остановиться; wiring самого
`execute_chroma_retention` — отдельный последующий срез.

## Защищённое локальное состояние

На момент handoff существовали пользовательские untracked-артефакты. Не
удалять и не stage их без отдельного запроса:

- `.grok-prompts/`, `.pytest_tmp*/`;
- `_NEXT_SESSION.md`, `FLANT_DOGFOOD_FINDINGS.md`;
- `RAG Explainer.html`, `_ref_presentation3.html`, `plan_for_pres.md`;
- `pres.html`, `presentation.html`, `rag_new_explanation.md`;
- `docs/architecture-data-flow.html`, `scripts/check_architecture_diagram.py`.

Не читать `.env` и не обращаться к live services без явного opt-in. Файла
`.autopilot/BLOCKED.md` на момент handoff нет.
