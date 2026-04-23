# Task 173 — Real-Postgres docker-compose.test.yml + full restore_verify flow

## Goal
Закрыть Known gap Arc 7 Batch J: `scripts/restore_verify.py` сейчас проверяет только SQLite integrity + tarball extraction (layout smoke), без реального Postgres. Нужен disposable Postgres контейнер через `docker-compose.test.yml`, полноценный `pg_restore` от snapshot к свежей БД и post-restore smoke на восстановленной схеме.

## Context
- `scripts/backup_snapshot.py` делает `pg_dump -Fc` (custom format), SQLite online backup API, tarballs для `data/uploads` и ChromaDB. Exit code 0 на success.
- `scripts/restore_verify.py` сейчас:
  - разворачивает snapshot в temp root.
  - `PRAGMA integrity_check` для SQLite.
  - распаковывает tarballs и проверяет layout (файлы на месте).
  - НЕ проверяет Postgres dump — `pg_restore` не вызывается.
- Это оставляет большую часть backup surface untested: corrupted `pg_dump` файл или schema-incompatible dump на current Postgres version не будет пойман.
- `docker-compose.yml` в корне — production-like compose (app + postgres + redis + ollama + jaeger); не подходит для изолированного теста.
- `snapshot_manifest.json` содержит SHA256 и size per-component, плюс alembic revision. Restore-verify должен matched revision против live `alembic_version` после `pg_restore`.

## Deliverables
- `docker-compose.test.yml` — минимальный compose для restore testing:
  - service `postgres-test` — `postgres:16-alpine`, env `POSTGRES_DB=rag_restore_test`, `POSTGRES_USER=rag`, `POSTGRES_PASSWORD=rag_test`, port-mapping на рандомный host-port (использовать `ports: - "5432"` без host-side для auto-assign).
  - health check через `pg_isready`.
  - ephemeral storage (нет named volume).
  - network `rag-restore-test`.
- `scripts/restore_verify.py` — расширение:
  - новый флаг `--postgres-url <url>` (optional). Если задан — выполняет `pg_restore --dbname=<url> --clean --if-exists <snapshot>/postgres.dump`, затем connect + verify:
    - `SELECT version_num FROM alembic_version` = manifest'овский alembic revision.
    - `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'` = expected table count (17 + `alembic_version`).
    - все expected tables (из `db.models.Base.metadata`) — доступны для `SELECT * LIMIT 0`.
  - если `--postgres-url` не задан — behaviour без изменений (backward-compat).
  - на любой postgres-step error — exit code `EXIT_POSTGRES_VERIFY_FAILED=4` (новый), отдельно от `EXIT_SMOKE_FAILED=2`.
- `scripts/restore_verify_integration.py` — thin wrapper:
  - поднимает `docker-compose -f docker-compose.test.yml up -d postgres-test`.
  - ждёт health ready (poll `pg_isready`).
  - получает динамический порт через `docker-compose port postgres-test 5432`.
  - вызывает `restore_verify.main([...--postgres-url=postgresql://rag:rag_test@localhost:<port>/rag_restore_test, --snapshot=<path>])`.
  - на exit — всегда `docker-compose -f docker-compose.test.yml down -v`.
  - exit-code прокидывает из underlying `restore_verify.main`.
- `tests/test_restore_verify_postgres.py`:
  - тест skipped если `pytest.importorskip("docker")` или `shutil.which("pg_restore") is None` или `shutil.which("docker") is None`.
  - интеграция end-to-end: make tiny backup snapshot → run `restore_verify_integration` → assert exit 0.
  - cleanup в fixture teardown гарантирован.
- `docs/operations/backup-restore.md` — раздел «Full-restore verification» с описанием `docker-compose.test.yml` и `scripts/restore_verify_integration.py` flow.
- `docs/CHANGELOG.md` — запись.

## Acceptance criteria
- [ ] Прогон: сделать snapshot (`python scripts/backup_snapshot.py --output-dir /tmp/test-snap/`) на live dev Postgres (`postgres:16-alpine` из `docker-compose.test.yml`) → `python scripts/restore_verify_integration.py --snapshot /tmp/test-snap/<ts>/` → exit 0.
- [ ] Corrupted snapshot (`dd if=/dev/urandom of=/tmp/test-snap/<ts>/postgres.dump bs=1k count=10 conv=notrunc`) → integration script возвращает exit 4 (postgres verify failed), диагностика в stderr.
- [ ] `pytest tests/test_restore_verify_postgres.py -q` зелёный на машине с Docker; skipped (not failed) без Docker.
- [ ] Unit suite без регрессий (`restore_verify.py` без `--postgres-url` даёт прежнее поведение, 160-161 tests passing).
- [ ] `docker-compose -f docker-compose.test.yml down -v` после теста очищает container; `docker ps` не показывает висящий `postgres-test`.
- [ ] `ruff check scripts/ tests/` clean.

## Notes
- `pg_restore` требует `--clean --if-exists` чтобы дропать pre-existing schema (на первом restore схемы нет, но flag нужен для idempotency re-test).
- Альтернатива `docker-compose` — Python `testcontainers` лайбрари (`testcontainers-python`). Если CX предпочитает — приемлемо, но добавить в `requirements-dev.txt`. `docker-compose` CLI проще и уже есть в CI runners.
- Не коммитить тестовые snapshots — `data/` уже в `.gitignore`, temp paths через `tmp_path` fixture или `tempfile.mkdtemp`.
- `psql`/`pg_restore` должны быть в PATH у CX: в Ubuntu runner — `apt-get install -y postgresql-client-16`. На dev — уже установлены с Docker Desktop.
- `snapshot_manifest.json` формат: `{"alembic_revision": "017", "components": {...}}`. Revision сравнивать строкой (не числом).
- Не делать full docker-compose integration на Windows CX-окружении, если там нет Docker daemon — `docker-compose down` всегда в try/finally, и тест `pytest.skip` аккуратно.
