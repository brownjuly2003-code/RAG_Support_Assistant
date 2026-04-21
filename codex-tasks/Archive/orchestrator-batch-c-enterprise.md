# Batch C — Enterprise Hardening (orchestrator)

Три независимых enterprise-фичи. Порядок произвольный, НО encryption-at-rest
(task-113) должен идти **ДО** differentiation-батча (Batch D), так как
новые таблицы там тоже должны использовать `EncryptedText`.

## Preconditions
- Batch A + Batch B смержены (Archive/ содержит 102-110)
- `pytest tests/ -q` → 250+ passed
- Postgres + Redis up

## Порядок

### 1. task-112 (SSO/OIDC) — **DO FIRST**
Наименее инвазивно — новые endpoints + миграция users полей. Не трогает
graph/pipeline. Самая чистая таска.

```bash
alembic upgrade head
pytest tests/test_oidc_flow.py -v
pytest tests/ -q  # 253+ passed
git commit -m "SSO via authlib: Google + Azure AD OIDC (task-112)"
```

### 2. task-111 (OpenTelemetry) — **DO SECOND**
Тоже относительно изолировано (dep + instrumentation), но трогает
api/app.py и graph.py (manual spans). Лучше после SSO чтобы SSO endpoints
тоже попали в OTel traces out-of-the-box.

```bash
# Start Jaeger для local verification
docker compose up -d jaeger
OTEL_ENABLED=true pytest tests/test_otel.py -v
OTEL_ENABLED=false pytest tests/ -q  # 250+ passed, no regressions
git commit -m "OpenTelemetry SDK: distributed tracing w/ auto-instrumentation (task-111)"
```

### 3. task-113 (encryption at rest) — **LAST, RISKIEST**
Трогает schema (миграция типа колонки). **Делай в выделенную сессию**:
- Резервная копия БД **перед** миграцией
- Миграция encryption требует наличия `DB_ENCRYPTION_KEY` в env
- Тестировать на dev БД сначала

```bash
# BACKUP FIRST
docker exec rag-postgres pg_dump -U rag rag > backup-$(date +%Y%m%d).sql

export DB_ENCRYPTION_KEY=$(openssl rand -base64 32)
alembic upgrade head

# Verify ciphertext
docker exec rag-postgres psql -U rag -c "SELECT content FROM messages LIMIT 1"  # should show \x... bytes
pytest tests/ -q  # 255+ passed
git commit -m "Encryption at rest: pgcrypto for sensitive fields (task-113)"
```

### 4. Archive
```bash
git mv codex-tasks/task-11{1,2,3}-*.md codex-tasks/Archive/
git mv codex-tasks/orchestrator-batch-c-enterprise.md codex-tasks/Archive/
git commit -m "Archive Batch C enterprise specs (111-113)"
```

## DONE WHEN (batch)
- [ ] 4 коммита + 1 archive
- [ ] 255+ passed, ruff clean
- [ ] Google SSO login flow работает (manually verified или mock)
- [ ] Jaeger UI показывает span tree на тестовом запросе
- [ ] `SELECT` из messages/audit_log показывает ciphertext, app видит plaintext
- [ ] README обновлён: env vars SSO/OTel/encryption

## STOP conditions
- **task-113** критическая: если миграция encryption фейлится — откат
  БД из бэкапа, НЕ коммить schema change без round-trip теста пройденного
- **task-112**: если corporate IdP mock-тест не падает но реальный Google
  возвращает 400 — проверь redirect_uri regex в Google Console (частая
  причина). Не блокер — коммит scaffolding, real integration в separate task
- **task-111**: если OTel ломает существующие тесты — значит инструментация
  не no-op при `OTEL_ENABLED=false`. Fix: убедись что init_otel возвращает
  рано без побочных эффектов

## Notes
- Key management для task-113: используем env var в dev/compose. В prod
  (Helm) — values.yaml ссылается на k8s Secret → mountet как env. **Не
  хранить key в git.**
- OTel и Langfuse coexist: OTel для infra traces, Langfuse для LLM-specific.
  Не дублируй — manual spans только там где Langfuse не даёт покрытия.
