# Meta-task — Arc 7 / Batch J: Backup / Restore / Chaos drills

## Goal
Закрыть recoverability и operational drills поверх уже существующего базового runbook'а (`docs/operations/backup-restore.md`): snapshot backups для всех persistent stores, disposable restore verification, chaos drills для отказов Ollama/Postgres/Redis/network, post-deploy smoke suite, backup retention integrity report, DR checklist с RTO/RPO. Планируй и реализуй сам по паттерну batch G/H/I.

## Context

### Почему этот batch
Arc 6 добавил observability + partial runbook (backup-restore.md), но актуального snapshot/restore automation'а нет — юзер для восстановления должен следовать manual runbook. Для single-user local deploy это не catastrophe, но:
1. Если диск умрёт или случайная `rm -rf data/` — потеря всех trace history, curated dataset, chroma collections, uploads.
2. Если Ollama зависнет — pipeline fail'ит без graceful fallback (provider failover в batch H был, но это для LLM tier, не для connection-level).
3. Если новый deploy (после `alembic upgrade`) что-то сломает — нужно быстро понять.

Этот batch автоматизирует то, что runbook описывает words'ами: делать snapshot'ы, проверять их integrity, тренировать recovery.

### Текущее состояние
- HEAD `e063016`, 426 tests, ruff clean.
- `docs/operations/backup-restore.md` — manual runbook для Postgres + ChromaDB + uploads.
- Migrations 001-014 + потенциально 015-017 после batch I.
- Helm cronjobs for nightly eval, review queue, threshold analysis, improvement backlog, eval snapshot.
- Data directories: `data/tracing/traces.db` (SQLite), Postgres DB, ChromaDB persistent path, uploads, key manifests (pgcrypto, DB_ENCRYPTION_KEY env).
- Resilience layer: circuit breaker, timeout, retry, wall-time, semaphore вокруг Ollama.

### User context
- **Windows 11** host — scripts должны работать через Python (cross-platform) или PowerShell (`.ps1`). Bash scripts скорее всего не будут running unless WSL. Предпочесть Python CLI над shell.
- **Single-user local deploy** — нет cluster, нет AWS/S3. Snapshot'ы лежат локально (external disk рекомендация в docs) или mounted remote folder.
- **No paid cloud infra** — использовать только free local tools: `pg_dump`, tarball, rsync-like.

## Batch J scope (6 tasks, 159-164)

### task-159 — Snapshot backup для всех persistent stores
Единый script, который делает атомарный snapshot всех критичных stores.
- `scripts/backup_snapshot.py` — CLI: `python scripts/backup_snapshot.py --out /path/to/backup-<timestamp>/ [--skip-chroma]`.
- Включает:
  - `pg_dump` для Postgres (если `POSTGRES_URL` set).
  - Copy SQLite `data/tracing/traces.db` (atomic через `.backup` API, не rsync во время writes).
  - ChromaDB persistent path — tarball (requires stop consumers ОR использовать Chroma's snapshot API).
  - Uploads directory — tarball.
  - Key manifest: encrypted env vars (`DB_ENCRYPTION_KEY` hash only), список установленных secrets (names, не values).
  - JSON manifest `snapshot_manifest.json` с versions (alembic revision, python, ollama model names), timestamp, sizes, integrity hashes (SHA256 per file).
- Settings: `BACKUP_DIR: str` env, `BACKUP_RETENTION_DAYS: int = 30`.
- Cronjob `deploy/helm/templates/cronjob-backup.yaml` — nightly 01:00 UTC.
- Tests: 6+ (snapshot creation, manifest validity, sizes reported, idempotent when re-run, skip-chroma flag работает, integrity hashes matched).

### task-160 — Disposable restore verification
Принцип: snapshot без проверенного restore — не backup. Этот таск автоматически создаёт disposable environment, применяет snapshot, прогоняет smoke test, reports success/failure.
- `scripts/restore_verify.py` — CLI: `python scripts/restore_verify.py --snapshot /path/to/backup-<ts>/ --report /path/to/report.md`.
- Создаёт temp Postgres (через docker-compose.test.yml) + temp SQLite paths + temp Chroma dir → applies snapshot → runs `scripts/post_deploy_smoke.py` (см. task-162) → cleanup temp env → writes report.
- Exit codes: 0 success, 1 restore failed, 2 smoke failed, 3 infra error.
- Scheduled: weekly (Sunday 04:00 UTC) через cronjob.
- Tests: 5+ (happy path, restore failure, smoke failure, cleanup даже при exception).

### task-161 — Chaos drills (Ollama / Postgres / Redis / network faults)
Контролируемые injections для проверки circuit breakers, graceful degradation, provider failover.
- `scripts/chaos_drill.py` — CLI: `python scripts/chaos_drill.py --fault <ollama_timeout|ollama_down|postgres_unavailable|redis_unavailable|network_slow|network_flaky> --duration 30 --report /path/to/drill.md`.
- Механизм: monkey-patches network layer (httpx/asyncpg/redis client) на время drill, собирает metrics (circuit breaker state transitions, failed requests count, fallback activations, recovery time), проверяет acceptance.
- Acceptance per fault:
  - `ollama_timeout` — circuit breaker opens within 3 requests, failover chain (batch H) activates на GraceKelly/Mistral при доступности, recovery в 60s после fault end.
  - `postgres_unavailable` — `/healthz/ready` returns 503, trace writes queue в memory (или fail gracefully), никаких 500 на `/api/ask`.
  - `redis_unavailable` — cache disabled gracefully, pipeline продолжает работать без LLM response cache.
  - `network_slow` — p95 latency возрастает но не >10s threshold, no timeouts if within wall-time.
  - `network_flaky` — retry logic activates, eventual success.
- Report `.md` в `reports/chaos_drills/<timestamp>-<fault>.md`: timeline, metrics, pass/fail.
- НЕ в cronjob (manual trigger) — чтобы не устраивать chaos на prod random.
- Tests: 6+ (один per fault — mocked external dependencies, drill triggers correct state changes).

### task-162 — Post-deploy smoke suite
Quick sanity check после restart / upgrade / deploy. Пробегает за 30s максимум, проверяет critical paths.
- `scripts/post_deploy_smoke.py` — CLI: `python scripts/post_deploy_smoke.py --base-url http://localhost:8000 --report /path/to/smoke.md`.
- Проверки:
  - `GET /healthz/live` и `/healthz/ready` — 200.
  - `GET /metrics` — Prometheus format, содержит ключевые метрики (rag_model_routing, llm_cost_usd_total, review_queue_pending_total).
  - `POST /api/ask` с тестовым вопросом ("What is 2+2?") — возвращает JSON с `answer`, `trace_id`, reasonable `quality_score`.
  - `GET /admin/review-queue/stats` — 200 (нужен auth).
  - `GET /api/admin/providers` — 200, содержит ожидаемых провайдеров (ollama, gracekelly, mistral).
  - Migration check — `alembic current` выводит head, не older revision.
- Integration с CI — после deploy job в `.github/workflows/ci.yml` запускает smoke.
- Tests: 5+ (каждая check — isolated + happy path + failure detection).

### task-163 — Backup retention integrity report
Для backup'ов старше N дней — проверка integrity (SHA256 match, unpack test, manifest validity), retention policy enforcement.
- `scripts/backup_integrity.py` — CLI: `python scripts/backup_integrity.py --backup-dir /path/to/backups/ --report /path/to/integrity.md`.
- Actions:
  - Scan все snapshots в directory.
  - Per snapshot: read manifest → verify SHA256 per file → test unpack (Chroma tarball, uploads tarball) → summary.
  - Retention enforcement: snapshots > `BACKUP_RETENTION_DAYS` кандидаты на deletion (НЕ auto-delete, только report).
  - Output: markdown с valid/corrupted/expired counts, per-snapshot status, recommended deletions.
- Cronjob weekly (Sunday 05:00 UTC, after restore verification).
- Tests: 4+ (valid snapshot, corrupted SHA, missing manifest, expired candidate identification).

### task-164 — Disaster recovery checklist + RTO/RPO
Formal DR document-as-spec.
- `docs/disaster-recovery.md` — structured checklist с RTO/RPO per scenario:
  - **Scenario A: `data/` fully lost** — RPO 24h (nightly snapshot), RTO 45min (restore_verify + smoke).
  - **Scenario B: Postgres corrupted** — RPO 24h, RTO 30min.
  - **Scenario C: Ollama models lost** — RTO 2h (re-download через `ollama pull`), RPO 0 (models не changed).
  - **Scenario D: Full host compromise** — RTO 1 day (fresh install + snapshot restore), RPO 24h.
  - **Scenario E: Encryption key lost** (`DB_ENCRYPTION_KEY`) — **unrecoverable** (pgcrypto encrypted fields gone) → document mitigation (key escrow in password manager).
- Each scenario: required inputs (what must be backed up), procedure (exact commands), verification (что проверить после), estimated time.
- Включает mappings на scripts из task-159/160/162.
- Tests: doc lint only (markdownlint не обязателен), но наличие всех Scenario A-E — через test pattern match (`tests/test_dr_checklist.py`, 2+ тестов).

## CRITICAL SAFEGUARDS

- **Никогда не запускать destructive operations** в chaos_drill или restore_verify на production paths — только temp dirs.
- **Backup НЕ коммитить в git** — уже в `.gitignore` (`data/`). Tests должны использовать temp_path fixtures.
- **Encryption key snapshot** — только SHA256 hash + key name, никогда raw value.
- **Postgres dumps** могут содержать PII — document что snapshots должны быть encrypted at rest (external encrypted disk или `age`/`gpg`-encrypted tarball). Этот batch не делает encryption — только note в DR checklist.
- **Chaos drills не запускать в CI pipeline** — они mock'ают external services, но могут destabilize concurrent tests. Только manual trigger.

## Deliverables

### Docs
- `codex-tasks/orchestrator-batch-j-backup-restore-chaos.md`.
- `codex-tasks/task-159-snapshot-backup.md` ... `task-164-disaster-recovery-checklist.md`.
- `docs/disaster-recovery.md` (task-164 deliverable).
- Update `codex-tasks/arc-7-proposal.md` статус batch J.

### Code
- 5 scripts: `backup_snapshot.py`, `restore_verify.py`, `chaos_drill.py`, `post_deploy_smoke.py`, `backup_integrity.py`.
- 3 cronjobs (backup, integrity, restore_verify).
- Settings: `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, chaos drill не требует settings (CLI only).
- `docker-compose.test.yml` — disposable Postgres для restore verify.
- CI integration: smoke job в `.github/workflows/ci.yml`.

### Closure
- Verification sweep per task.
- Per-task commits (или arc-level как batch G/H).
- Archive specs.
- CHANGELOG Arc 7 Batch J section.

## Acceptance
- `pytest tests/ -q` — 426 + ~28 new tests = 454+ passing.
- `ruff check .` — clean.
- `python scripts/backup_snapshot.py --out tmp/test-backup/` создаёт valid snapshot с manifest.
- `python scripts/restore_verify.py --snapshot tmp/test-backup/ --report tmp/restore.md` — exit 0 на happy path.
- `python scripts/post_deploy_smoke.py --base-url http://localhost:8000` против running instance — exit 0.
- `docs/disaster-recovery.md` содержит все 5 scenarios A-E.
- Working tree clean.

## Workflow rules
- По паттерну batch G/H/I.
- Windows-compatibility: все scripts должны работать на Windows 11 (Python, не bash). Докер через Windows Docker Desktop.
- Не требовать paid cloud infra — всё local-first.

## Out of scope
- Offsite backup replication (rclone/rsync remote) — задокументировать в DR checklist как recommended, не автоматизировать.
- Multi-region DR — не актуально для single-user local.
- Automated encryption of backups — задокументировать в runbook, не automate (требует настройки key management).
- Full chaos engineering framework типа ChaosMonkey — этот batch делает targeted manual drills, не production chaos.
- Backup replication между разными хостами — требует инфры.

## How to start
1. `docs/operations/backup-restore.md` — existing manual runbook, основа для DR checklist.
2. `codex-tasks/Archive/meta-arc-7-batch-g-provider-abstraction.md` + `-h-*` — образцы meta.
3. `utils/circuit_breaker.py` — existing resilience layer (reuse для chaos drill acceptance checks).
4. `conftest.py` — existing test fixtures для disposable Postgres/SQLite (reuse для restore_verify infra).
5. `scripts/nightly_eval.py` / `scripts/kb_gap_detector.py` — образцы schedule-able scripts с cronjob pairing.

## Risks
- **Postgres pg_dump requires running Postgres** — если Postgres не запущен, snapshot fail'ит. Добавить precheck + graceful skip.
- **ChromaDB snapshot atomicity** — Chroma не любит copies во время writes. Использовать `chroma_client.persist()` + short freeze window, или document как limitation.
- **Windows `pg_dump` availability** — может требовать PATH setup. Fallback на docker-run `postgres:15 pg_dump ...` если local не найден.
- **Test disposable Postgres** — `docker-compose.test.yml` требует Docker Desktop running на Windows. Tests должны skip если docker unavailable (не fail CI).
- **Chaos drill на Windows network** — monkey-patching httpx вместо реальных network faults (iptables недоступен). OK — это юнит-level chaos, не full network drill.

---

**Если meta достаточно — начинай. Critical gap — один вопрос и продолжай.**
