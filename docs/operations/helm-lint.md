# Helm lint runbook

Аудитория: разработчик / SRE. Документ описывает локальную проверку chart `deploy/helm/` перед PR или ручным релизом.

## Что проверяем

- `helm lint deploy/helm/ --strict`
- `helm template` with required production Secret/CORS values and persistence variants
- optional `kubectl apply --dry-run=client` **only when an API server is available** (kind/live)

## Предварительные требования

- `helm` 3.x
- `kubectl` (for dry-run gate)
- Docker + `kind` when exercising the kubectl dry-run path

Все команды ниже запускать из корня репозитория.

Defaults set `env.RAG_ENV=production`. Production render therefore requires
explicit `env.CORS_ORIGINS` and non-empty Secret keys (or
`secrets.existingSecret`). Empty Secret placeholders alone will fail closed.

## Команды

Shared production-like `--set` bundle (dummy values for local render only):

```bash
helm lint deploy/helm/ --strict

# Default managed claims (data 10Gi / backups 20Gi / reports 5Gi)
helm template rag-lint deploy/helm/ \
  --set env.CORS_ORIGINS=https://support.example.com \
  --set secrets.DATABASE_URL=postgresql://rag:rag@postgres:5432/rag_assistant \
  --set secrets.JWT_SECRET=lint-jwt-secret-not-for-prod \
  --set secrets.SESSION_SECRET_KEY=lint-session-secret-not-for-prod \
  --set secrets.ADMIN_PASSWORD_HASH='$2b$12$lintadminhashplaceholder000000000000000000000000000' \
  --set secrets.DB_ENCRYPTION_KEY=lint-db-encryption-key-not-for-prod \
  > /tmp/rendered-default.yaml

# existingClaim overrides (no chart-managed PVCs for those stores)
helm template rag-lint deploy/helm/ \
  --set env.CORS_ORIGINS=https://support.example.com \
  --set secrets.DATABASE_URL=postgresql://rag:rag@postgres:5432/rag_assistant \
  --set secrets.JWT_SECRET=lint-jwt-secret-not-for-prod \
  --set secrets.SESSION_SECRET_KEY=lint-session-secret-not-for-prod \
  --set secrets.ADMIN_PASSWORD_HASH='$2b$12$lintadminhashplaceholder000000000000000000000000000' \
  --set secrets.DB_ENCRYPTION_KEY=lint-db-encryption-key-not-for-prod \
  --set persistence.data.existingClaim=ext-data \
  --set persistence.backups.existingClaim=ext-backups \
  --set persistence.reports.existingClaim=ext-reports \
  > /tmp/rendered-existing.yaml

# Non-production: data persistence may be disabled
helm template rag-lint deploy/helm/ \
  --set env.RAG_ENV=development \
  --set persistence.data.enabled=false \
  --set secrets.DATABASE_URL=postgresql://rag:rag@postgres:5432/rag_assistant \
  --set secrets.JWT_SECRET=lint-jwt-secret-not-for-prod \
  --set secrets.SESSION_SECRET_KEY=lint-session-secret-not-for-prod \
  --set secrets.ADMIN_PASSWORD_HASH='$2b$12$lintadminhashplaceholder000000000000000000000000000' \
  --set secrets.DB_ENCRYPTION_KEY=lint-db-encryption-key-not-for-prod \
  > /tmp/rendered-dev-disabled.yaml

# Production + data persistence disabled must fail closed
helm template rag-lint deploy/helm/ \
  --set env.CORS_ORIGINS=https://support.example.com \
  --set secrets.DATABASE_URL=postgresql://rag:rag@postgres:5432/rag_assistant \
  --set secrets.JWT_SECRET=lint-jwt-secret-not-for-prod \
  --set secrets.SESSION_SECRET_KEY=lint-session-secret-not-for-prod \
  --set secrets.ADMIN_PASSWORD_HASH='$2b$12$lintadminhashplaceholder000000000000000000000000000' \
  --set secrets.DB_ENCRYPTION_KEY=lint-db-encryption-key-not-for-prod \
  --set persistence.data.enabled=false
```

This command itself must exit non-zero. Do not mask the status with `; echo ...` or similar. The Helm error text must name `persistence.data.enabled`.

Optional kubectl dry-run **with** a local API server:

```bash
kind delete cluster --name rag-helm-lint || true
kind create cluster --name rag-helm-lint
kubectl apply --dry-run=client -f /tmp/rendered-default.yaml
kind delete cluster --name rag-helm-lint
```

Для PowerShell вместо `/tmp/rendered-*.yaml` используйте `$env:TEMP\rag-rendered-*.yaml`.

## Почему client dry-run может требовать kind/live API

Актуальные версии `kubectl` даже с `--dry-run=client` (and often with
`--validate=false`) всё равно делают API discovery. Without a reachable API
server they can fail on `failed to download openapi`, `unable to recognize`,
or connection refused to `localhost:8080`. That is a **local-environment /
API discovery gate**, not proof that the rendered manifests are invalid.

Locally verified without a cluster: `helm lint`, `helm template` default /
existingClaim / non-production-disabled renders, and production data-disabled
fail-closed. Remaining gate for dry-run validation: kind or another live API.

## Пример вывода

```text
==> Linting deploy/helm

1 chart(s) linted, 0 chart(s) failed

# from a successful template with required --set values:
# PersistentVolumeClaim/...-data, ...-backups, ...-reports
# Deployment mounts /app/data when persistence.data.enabled
# storage-dependent CronJobs present when their persistence flags are on
```

## Ожидаемые warnings

Допустимых warnings нет. Ожидаемое состояние:

- `helm lint deploy/helm/ --strict` завершает работу с exit 0
- production-like `helm template` with CORS + Secret values exit 0 and emits managed PVCs
- production + `persistence.data.enabled=false` fails closed (non-zero)
- `kubectl apply --dry-run=client -f rendered.yaml` exit 0 **only when** an API server is available (kind/live); absence of API discovery is not a chart defect

Related: [backup-restore.md](backup-restore.md), [DEPLOYMENT.md](../DEPLOYMENT.md).
