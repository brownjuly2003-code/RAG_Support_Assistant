# Task 127 — CI pipeline (pre-commit + GitHub Actions)

## Goal
Поднять CI, чтобы гарантия качества не зависела от памяти разработчика. Сейчас ruff / pytest запускаются вручную; в CI должны запускаться на каждый push / PR.

## Context
- Repo: `D:\RAG_Support_Assistant` (Python 3.13, FastAPI + LangGraph + ChromaDB + Ollama).
- Текущее состояние:
  - Тестов: 293 passed (unit + integration), прогон ~80s локально.
  - Линтер: `ruff check` — clean.
  - Форматтер: не настроен (возможно ruff format, не подтверждено).
  - Type checker: отсутствует (mypy не настроен).
  - Workflows: только `.github/workflows/weekly-report.yml` (artifact task-118).
  - Pre-commit: отсутствует.
- Стек зависимостей — в `pyproject.toml` и `requirements.txt` (после task-126 будет подтверждено, что они синхронны).
- Integration tests: `tests/integration/` (task-122) — возможно медленнее unit, могут требовать infra (Postgres/Redis). Unit tests — в `tests/*.py`.
- Dev-машина: Windows 11, bash. CI — Linux runners GitHub-hosted.
- Python 3.13 — runner должен поддерживать.

## Deliverables
1. **`.pre-commit-config.yaml`** в корне:
   - `ruff` — lint (fix auto-on-stash).
   - `ruff-format` — форматтер (опционально, если проект уже им форматирован — включить; если нет — не вводить насильно).
   - Базовые встроенные хуки (`pre-commit-hooks`): `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files` (limit 500 KB), `check-merge-conflict`, `detect-private-key`.
   - **НЕ** включать `pytest` в pre-commit (slow) — он в CI.
2. **`.github/workflows/ci.yml`**:
   - Trigger: `push` (all branches) + `pull_request`.
   - Job `lint`:
     - Ubuntu latest, Python 3.13.
     - Cache pip.
     - `pip install -e .[dev]` (или `-r requirements-dev.txt` — выбрать то, что соответствует manifest).
     - `ruff check .`
     - `ruff format --check .` (если формат включён в pre-commit).
   - Job `test-unit`:
     - Зависит от `lint`? — нет, пусть параллелится.
     - Ubuntu latest, Python 3.13, cache pip.
     - Сервисы — только если unit-тесты реально нуждаются (обычно нет; mock'ами обходятся). Если нуждаются (например conftest.py требует Redis/Postgres) — добавить `services:`.
     - `pytest tests/ -q --ignore=tests/integration -p no:cacheprovider`.
   - Job `test-integration`:
     - Ubuntu latest, Python 3.13.
     - `services:` — `postgres:16`, `redis:7` с минимальной конфигурацией (user/db/password для тестов).
     - Environment переменные для тестов: `DATABASE_URL`, `REDIS_URL` указать на service-контейнеры.
     - `pytest tests/integration -q`.
     - **`continue-on-error: true`** на первом прогоне — если интеграционные тесты окажутся слишком хрупкими для CI, не блокировать merge. Снимать флаг, как только стабильно зелёные 10+ прогонов подряд.
   - Job `pre-commit`:
     - Запуск `pre-commit run --all-files` — дублирует lint, но ловит другие хуки (yaml/toml/size).
3. **Badge** в `README.md`: `[![CI](https://github.com/<user>/RAG_Support_Assistant/actions/workflows/ci.yml/badge.svg)](...)` — если PR с плейсхолдером, оставь `<user>` для ручной замены.
4. **`requirements-dev.txt`** или секция `[project.optional-dependencies.dev]` в `pyproject.toml`:
   - `pytest`, `ruff`, `pre-commit`, `pytest-asyncio` (если используется), etc. Всё, что нужно для `ruff check` + `pytest tests/`.

## Acceptance
- `pre-commit install && pre-commit run --all-files` локально → всё зелёное (или с очевидными авто-фиксами).
- `.github/workflows/ci.yml` валиден: `actionlint ci.yml` (или ручная ревизия синтаксиса).
- Integration job падает gracefully (continue-on-error), если окружение неполное — не блокирует lint / unit.
- Пути / версии консистентны: Python 3.13 везде; ruff версия совпадает между `.pre-commit-config.yaml` и manifest'ом dev-deps.
- Существующий `.github/workflows/weekly-report.yml` — не тронут.
- README-секция про CI: одна короткая (3-5 строк) про как запустить тесты/линтер локально и где смотреть CI результаты.

## Notes
- Ruff версию брать **актуальную** (на 2026-04 — 0.4+). Зафиксировать точную версию, не `*`.
- `pre-commit` зафиксировать версии хуков (`rev:` exact tags), чтобы avoid drift.
- Если `pyproject.toml` уже имеет `[tool.ruff]` секцию — уважать существующие настройки; не переписывать.
- Если integration-тесты требуют Ollama — в CI подменить `OLLAMA_HOST` на несуществующий и убедиться, что тесты либо мокают, либо skip'ят (не падают).
- Секреты для `test-integration` (если DATABASE_URL требует пароля) — сгенерить inline в yml, не из GitHub Secrets (эти локальные тестовые БД). Реальные секреты в CI — только если workflow будет деплоить куда-то (не этот scope).
- НЕ включать отдельный job для `mypy` — type-check не настроен в проекте, это отдельная работа (arc-6 кандидат).
- Не забыть `fail-fast: false` в matrix (если появится), чтобы lint+test независимо отображались.
