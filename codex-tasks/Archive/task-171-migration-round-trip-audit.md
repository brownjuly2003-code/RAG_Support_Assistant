# Task 171 — Alembic migration round-trip audit + CI job

## Goal
Гарантировать что каждая alembic миграция 001-017 применяется и откатывается чисто на реальной Postgres, без скрытых idempotency/ENUM/JSONB багов, и что эта проверка не регрессирует. Добавить CI job, которая прогоняет полный round-trip автоматически.

## Context
- Во время ручной проверки (2026-04-23) миграция 012 упала на чистой Postgres 16 с `psycopg2.errors.DuplicateObject: type "review_queue_reason" already exists`. Root cause: `reason_enum.create(bind, checkfirst=True)` создавал ENUM, а затем `sa.Enum(*values, name="...")` в `sa.Column(...)` пытался создать тот же тип второй раз. Починено в commit `d163942` (`sa.Enum` → `postgresql.ENUM(create_type=False)`).
- Unit-тест `tests/test_review_queue.py::test_review_queue_migration_upgrade_creates_table_and_indexes` этот баг не ловил, потому что монкипатчил `postgresql.ENUM` собственным фейком и никогда не шёл через реальный Postgres.
- Та же категория ошибок могла остаться в других миграциях (004, 009, 012, 014 используют `postgresql.*` types; 008 делает `CREATE EXTENSION pgcrypto`). Нужен реальный round-trip прогон + CI защита от регрессии.
- `alembic.ini` по умолчанию смотрит на `postgresql://rag:rag_dev_password@localhost:5432/rag_assistant`; `alembic/env.py` honours `DATABASE_URL` env var. Миграция 008 требует `DB_ENCRYPTION_KEY` (fail-fast).
- CI уже есть (`.github/workflows/ci.yml`); migration round-trip job там сейчас отсутствует.

## Deliverables
- `scripts/migration_round_trip.py` — standalone Python CLI:
  - аргументы: `--database-url` (default `$DATABASE_URL`), `--verbose`.
  - шаги: `alembic upgrade head` → `alembic current` (должен быть head) → `alembic downgrade base` → `alembic current` (должен быть пусто) → `alembic upgrade head` → verify expected tables set.
  - expected tables — список, prompted из `db.models.Base.metadata.tables.keys()` плюс `alembic_version`.
  - exit codes: 0 ok, 1 upgrade failed, 2 downgrade failed, 3 re-upgrade failed, 4 table set mismatch.
  - subprocess-вызовы `alembic` с понятным stderr прокидыванием, без swallowing.
- `tests/test_migration_round_trip.py` — smoke-тест который вызывает `scripts.migration_round_trip.main(["--database-url", sqlite_url])` под SQLite-совместимым подмножеством (для miграций которые работают на SQLite — отдельная fixture; если round-trip целиком не идёт на SQLite, тест gate'ится на переменную `PG_DSN` и `pytest.skip` без неё). Тест покрывает только exit-code contract и argument parsing, не реальные DDL.
- `.github/workflows/ci.yml` — добавить job `migrations`:
  - `services.postgres` — `postgres:16-alpine` с `POSTGRES_DB=rag_assistant`, `POSTGRES_USER=rag`, `POSTGRES_PASSWORD=rag_dev_password`, health check `pg_isready`.
  - env: `DATABASE_URL=postgresql://rag:rag_dev_password@localhost:5432/rag_assistant`, `DB_ENCRYPTION_KEY=ci-test-key-32-characters-long-xyz`.
  - steps: checkout → setup-python → `pip install -r requirements.txt` → `python scripts/migration_round_trip.py`.
  - job должна запускаться на `pull_request` и `push` в `master`.
- `docs/CHANGELOG.md` — запись под новым разделом про migration-012 fix и round-trip gate.

## Acceptance criteria
- [ ] Локально: `python scripts/migration_round_trip.py --database-url postgresql://rag:rag_dev_password@localhost:55432/rag_assistant` на disposable `postgres:16-alpine` контейнере завершает с exit 0, логи показывают 17 миграций upgrade + 17 downgrade + 17 upgrade.
- [ ] Expected tables set: 17 доменных таблиц (из `db.models.Base.metadata`) + `alembic_version` (итого 18). Любое расхождение (пропуск/лишняя) → exit 4 + список diff в stderr.
- [ ] `pytest tests/test_migration_round_trip.py -q` зелёный.
- [ ] Unit suite без регрессий: `pytest tests/ --ignore=tests/integration --ignore=tests/test_a11y.py --deselect tests/test_body_size_limits.py::test_upload_path_bypasses_body_middleware -p no:schemathesis -q --tb=no --timeout=30` — всё pass.
- [ ] `ruff check scripts/ tests/` clean.
- [ ] CI job `migrations` зелёный в PR preview.
- [ ] Если раунд-трип обнаружит ещё одну проблемную миграцию (например, похожий ENUM double-create или FK cycle при downgrade) — починить по аналогии с commit `d163942` в том же PR; в коммит-месседже привести список обнаруженных проблем.

## Notes
- Для локального прогона disposable Postgres: `docker run -d --rm --name rag-pg-test -e POSTGRES_DB=rag_assistant -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag_dev_password -p 55432:5432 postgres:16-alpine`.
- Waiting-for-ready цикл обязателен: `docker exec rag-pg-test pg_isready -U rag -d rag_assistant` в loop до "accepting connections".
- `DB_ENCRYPTION_KEY` требуется миграцией 008 (pgcrypto) — использовать фиксированный dummy (`test-encryption-key-32-characters-long-xyz`), **не коммитить** реальный ключ.
- Не использовать `alembic upgrade +1` в цикле — один `alembic upgrade head` с подтверждением через `alembic current` достаточно.
- Категории потенциальных проблем, на которые стоит смотреть при ручной верификации: (1) `sa.Enum` + `postgresql.ENUM().create(checkfirst=True)` в одной миграции (как 012); (2) `postgresql.UUID` без `as_uuid=True`; (3) JSONB default values несовместимые с re-create; (4) FK cycles в downgrade; (5) отсутствие `drop_index` перед `drop_table` если индекс named-unique.
- Миграция 008 делает `CREATE EXTENSION pgcrypto` — на shared Postgres хостингах может потребовать superuser. CI postgres service создаёт свежую БД, superuser есть у role `rag` по default image.
