# Backup & restore runbook

Аудитория: оператор / SRE. Предполагается знание Docker Compose и Kubernetes.

Документ описывает текущую реализацию репозитория `RAG_Support_Assistant` и не скрывает её ограничения. Здесь используется фактическое имя ключа из кода: `DB_ENCRYPTION_KEY`.

## 0. Что резервируем

| Компонент | Критичность | RPO target | RTO target | Источник истины / комментарий |
|---|---|---:|---:|---|
| Postgres (`rag_assistant`) | critical | 1h | 30m | Основное состояние приложения: `users`, `sessions`, `messages`, `audit_log`, `escalated_tickets`, `eval_results`, `knowledge_gaps`, `kb_drafts`, `document_stats` |
| ChromaDB (`data/vectordb/chroma`) | high | 24h | 2h | Векторный индекс по tenant-коллекциям `rag_docs_<tenant>`; ускоряет восстановление, но может быть rebuilt |
| Uploaded docs (`data/uploads`) | critical | 24h | 1h | Фактический источник для `scripts/reindex.py`; без них rebuild Chroma невозможен |
| `DB_ENCRYPTION_KEY` | critical | immutable | 5m | Хранить отдельно от бэкапов данных; без ключа часть Postgres-данных невосстановима |
| SQLite traces (`data/tracing/traces.db`) | medium | 24h | 30m | Операционные трейсы, feedback и `/api/metrics`; не блокируют трафик, но важны для аудита и постмортемов |
| Redis (`redisdata` / `redis://...`) | low | none | none | Только LLM cache (`LLM_CACHE_ENABLED`); допускается потеря |

### Важные ограничения текущего репо

- `scripts/reindex.py --all` rebuild-ит Chroma из `data/uploads`, а не из Postgres. Потеря и `data/uploads`, и Chroma одновременно означает ручное повторное наполнение знаний.
- `scripts/rotate_encryption_key.py` существует, но это заглушка: он проверяет env wiring и не переписывает ciphertext. Для реальной ротации используйте SQL-процедуру из раздела `2.3`.
- Операционные трейсы и feedback сейчас живут в `data/tracing/traces.db`; их нужно бэкапить отдельно от Postgres.
- Helm chart в `deploy/helm/` не содержит `Secret` для `DB_ENCRYPTION_KEY` и не содержит `PersistentVolumeClaim` для `/app/data`. В production это надо добавить до первого релиза, иначе uploads / Chroma / SQLite traces будут эфемерными.
- Ollama-модели не резервируем: они derivable и повторно подтягиваются стандартным деплоем.

### Базовые переменные

Все команды ниже запускать из корня репозитория.

```bash
timestamp="$(date -u +%Y%m%d%H%M%S)"
BACKUP_ROOT="${BACKUP_ROOT:-archive/backups}"
BACKUP_BUCKET="${BACKUP_BUCKET:-s3://rag-support-backups}"
mkdir -p \
  "$BACKUP_ROOT/postgres" \
  "$BACKUP_ROOT/chromadb" \
  "$BACKUP_ROOT/uploads" \
  "$BACKUP_ROOT/sqlite"
```

## 1. Backup procedure

### 1.1 Postgres

#### Docker Compose

```bash
docker compose exec -T postgres sh -lc '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc
' > "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump"

pg_restore -l "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" > /dev/null

aws s3 cp \
  "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" \
  "$BACKUP_BUCKET/postgres/postgres-${timestamp}.dump"
```

Проверка после выгрузки:

```bash
docker compose exec -T postgres sh -lc '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT extname FROM pg_extension WHERE extname = '\''pgcrypto'\'';"
'
```

#### Kubernetes

Текущий chart читает `DATABASE_URL` из ConfigMap `RELEASE-config`. Для production лучше переопределить `DATABASE_URL` из Secret или Vault и экспортировать его в оболочку перед запуском команды.

```bash
export NAMESPACE="${NAMESPACE:-rag-support}"
export RELEASE="${RELEASE:-rag-support-assistant}"
export DATABASE_URL="${DATABASE_URL:-$(kubectl -n "$NAMESPACE" get configmap "$RELEASE-config" -o jsonpath='{.data.DATABASE_URL}')}"

kubectl -n "$NAMESPACE" run "pgdump-${timestamp}" \
  --rm -i --restart=Never \
  --image=postgres:16-alpine \
  --env="DATABASE_URL=$DATABASE_URL" \
  -- sh -lc 'pg_dump "$DATABASE_URL" -Fc' \
  > "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump"

pg_restore -l "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" > /dev/null

aws s3 cp \
  "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" \
  "$BACKUP_BUCKET/postgres/postgres-${timestamp}.dump"
```

#### Retention policy

- Hourly: хранить 7 суток.
- Daily: хранить 4 недели.
- Monthly: хранить 12 месяцев.
- Реализовать lifecycle-политикой на bucket, а не `find -delete` на хосте.

### 1.2 ChromaDB

Текущий persist directory общий для всех tenant-коллекций. Поэтому нужны два вида бэкапа:

1. Полный snapshot каталога `data/vectordb/chroma` для быстрого полного restore.
2. Отдельные tenant-архивы через export коллекций для точечного восстановления одного tenant.

#### Docker Compose: полный snapshot каталога

```bash
tar -C data/vectordb -czf \
  "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz" \
  chroma

aws s3 cp \
  "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz" \
  "$BACKUP_BUCKET/chromadb/chroma-dir-${timestamp}.tar.gz"
```

#### Docker Compose: tenant export

```bash
export BACKUP_STAMP="$timestamp"

python - <<'PY'
import json
import os
from pathlib import Path

import chromadb

from config.settings import get_settings
from vectordb.manager import _collection_name

upload_root = Path("data/uploads")
tenants = ["default"]
if upload_root.exists():
    tenants.extend(sorted(p.name for p in upload_root.iterdir() if p.is_dir()))

settings = get_settings()
client = chromadb.PersistentClient(path=str(settings.vectordb_chroma_dir))
out_root = Path("archive/backups/chromadb")
out_root.mkdir(parents=True, exist_ok=True)
stamp = os.environ["BACKUP_STAMP"]

for tenant_id in tenants:
    collection_name = _collection_name(tenant_id)
    try:
        collection = client.get_collection(collection_name)
    except Exception:
        continue
    payload = collection.get(include=["documents", "metadatas", "embeddings"])
    out_path = out_root / f"{tenant_id}-{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"{tenant_id}: {collection.count()} entries -> {out_path}")
PY

gzip -f "$BACKUP_ROOT"/chromadb/*.json
aws s3 cp "$BACKUP_ROOT/chromadb/" "$BACKUP_BUCKET/chromadb/" --recursive --exclude "*" --include "*.json.gz"
```

#### Kubernetes

Для production в k8s этот раздел работает только если `/app/data` вынесен на PVC или object storage. В текущем chart это нужно добавить отдельно.

Полный snapshot каталога из работающего pod:

```bash
export NAMESPACE="${NAMESPACE:-rag-support}"
export RELEASE="${RELEASE:-rag-support-assistant}"

kubectl -n "$NAMESPACE" exec "deployment/${RELEASE}-app" -- \
  tar -C /app/data/vectordb -czf - chroma \
  > "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz"
```

Point-in-time restore одного tenant через export коллекции:

```bash
export TENANT_ID="${TENANT_ID:-default}"
kubectl -n "$NAMESPACE" exec "deployment/${RELEASE}-app" -- sh -lc "
  export TENANT_ID='$TENANT_ID'
  python - <<'PY'
import gzip
import json
import os
import sys

import chromadb

from config.settings import get_settings
from vectordb.manager import _collection_name

tenant_id = os.environ['TENANT_ID']
settings = get_settings()
client = chromadb.PersistentClient(path=str(settings.vectordb_chroma_dir))
collection = client.get_collection(_collection_name(tenant_id))
payload = collection.get(include=['documents', 'metadatas', 'embeddings'])
sys.stdout.buffer.write(gzip.compress(json.dumps(payload, ensure_ascii=False).encode('utf-8')))
PY
" > "$BACKUP_ROOT/chromadb/${TENANT_ID}-${timestamp}.json.gz"
```

### 1.3 `DB_ENCRYPTION_KEY`

`DB_ENCRYPTION_KEY` не должен лежать:

- в Git;
- в `.env` для production;
- в Docker image;
- в том же bucket / vault path, где лежат дампы данных.

#### Генерация и fingerprint

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Fingerprint для инвентаризации ключа рядом с backup manifest:

```bash
python - <<'PY'
import hashlib
import os
print(hashlib.sha256(os.environ["DB_ENCRYPTION_KEY"].encode("utf-8")).hexdigest())
PY
```

#### Где хранить

1. Основная копия: Vault / KMS / HSM.
2. Резервная копия: офлайн-носитель в sealed envelope.
3. Доступ: минимум два уполномоченных человека по dual control.

#### Обязательные правила

- Никогда не сохранять ключ в тот же `BACKUP_BUCKET`.
- Для Compose использовать runtime injection или Docker secret. `.env` допустим только для dev/single-host.
- Для Kubernetes использовать `Secret` или Vault Agent. Текущий chart нужно доработать: он умеет только `ConfigMap`, этого недостаточно.

### 1.4 Uploaded documents и SQLite traces

#### Docker Compose

Uploaded docs:

```bash
tar -C data -czf \
  "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz" \
  uploads

aws s3 cp \
  "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz" \
  "$BACKUP_BUCKET/uploads/uploads-${timestamp}.tar.gz"
```

SQLite traces:

```bash
tar -C data -czf \
  "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz" \
  tracing

aws s3 cp \
  "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz" \
  "$BACKUP_BUCKET/sqlite/sqlite-traces-${timestamp}.tar.gz"
```

#### Kubernetes

Только если `/app/data` вынесен на PVC:

```bash
kubectl -n "$NAMESPACE" exec "deployment/${RELEASE}-app" -- \
  tar -C /app/data -czf - uploads \
  > "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz"

kubectl -n "$NAMESPACE" exec "deployment/${RELEASE}-app" -- \
  tar -C /app/data -czf - tracing \
  > "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz"
```

Если uploads переедут в S3/MinIO, основной механизм защиты должен быть не `tar`, а bucket versioning + cross-region replication.

### 1.5 Автоматизация

#### Host cron для Docker Compose

```cron
0 * * * * cd /srv/rag-support-assistant && BACKUP_BUCKET=s3://rag-support-backups /bin/bash -lc 'timestamp="$(date -u +\%Y\%m\%d\%H\%M\%S)"; BACKUP_ROOT=archive/backups; mkdir -p "$BACKUP_ROOT/postgres"; docker compose exec -T postgres sh -lc '\''export PGPASSWORD="$POSTGRES_PASSWORD"; pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'\'' > "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" && aws s3 cp "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" "$BACKUP_BUCKET/postgres/postgres-${timestamp}.dump"'
15 2 * * * cd /srv/rag-support-assistant && BACKUP_BUCKET=s3://rag-support-backups /bin/bash -lc 'timestamp="$(date -u +\%Y\%m\%d\%H\%M\%S)"; BACKUP_ROOT=archive/backups; mkdir -p "$BACKUP_ROOT/chromadb" "$BACKUP_ROOT/uploads" "$BACKUP_ROOT/sqlite"; tar -C data/vectordb -czf "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz" chroma && tar -C data -czf "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz" uploads && tar -C data -czf "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz" tracing && aws s3 cp "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz" "$BACKUP_BUCKET/chromadb/chroma-dir-${timestamp}.tar.gz" && aws s3 cp "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz" "$BACKUP_BUCKET/uploads/uploads-${timestamp}.tar.gz" && aws s3 cp "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz" "$BACKUP_BUCKET/sqlite/sqlite-traces-${timestamp}.tar.gz"'
```

#### Пример CronJob для k8s

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: rag-support-postgres-backup
  namespace: rag-support
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: postgres:16-alpine
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: rag-support-db
                      key: DATABASE_URL
                - name: BACKUP_BUCKET
                  value: s3://rag-support-backups
              command:
                - sh
                - -lc
                - |
                  apk add --no-cache aws-cli
                  timestamp="$(date -u +%Y%m%d%H%M%S)"
                  pg_dump "$DATABASE_URL" -Fc > "/tmp/postgres-${timestamp}.dump"
                  aws s3 cp "/tmp/postgres-${timestamp}.dump" "$BACKUP_BUCKET/postgres/postgres-${timestamp}.dump"
```

#### Failure notification

Alert в Prometheus / Alertmanager:

```yaml
- alert: RagBackupJobFailed
  expr: max_over_time(kube_job_status_failed{namespace="rag-support",job_name=~"rag-support-postgres-backup.*"}[1h]) > 0
  for: 10m
  labels:
    severity: critical
  annotations:
    summary: "RAG backup job failed"
    description: "Последний backup job завершился ошибкой и требует ручной проверки."
```

## 2. Restore procedure

### 2.1 Standard restore: данные и ключ целы

#### Docker Compose

1. Остановить приложение, чтобы не было новых записей:

```bash
docker compose stop app
```

2. Восстановить Postgres:

```bash
cat "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" | docker compose exec -T postgres sh -lc '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_restore \
    -h 127.0.0.1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-privileges
'
```

3. Восстановить uploads и SQLite traces:

```bash
mv data/uploads "data/uploads.pre-restore.${timestamp}" 2>/dev/null || true
mv data/tracing "data/tracing.pre-restore.${timestamp}" 2>/dev/null || true

mkdir -p data
tar -C data -xzf "$BACKUP_ROOT/uploads/uploads-${timestamp}.tar.gz"
tar -C data -xzf "$BACKUP_ROOT/sqlite/sqlite-traces-${timestamp}.tar.gz"
```

4. Восстановить Chroma snapshot:

```bash
mv data/vectordb/chroma "data/vectordb/chroma.pre-restore.${timestamp}" 2>/dev/null || true
mkdir -p data/vectordb
tar -C data/vectordb -xzf "$BACKUP_ROOT/chromadb/chroma-dir-${timestamp}.tar.gz"
```

5. Поднять приложение и довести схему до `head`:

```bash
docker compose up -d app
docker compose exec -T app alembic upgrade head
```

6. Валидация:

```bash
curl -fsS http://localhost:8000/api/health/ready | jq .
curl -fsS http://localhost:8000/api/health | jq .
curl -fsS http://localhost:8000/metrics | grep -E '^rag_component_up'
```

Проверка количества документов по tenant:

```bash
docker compose exec -T app python - <<'PY'
import chromadb
from config.settings import get_settings

client = chromadb.PersistentClient(path=str(get_settings().vectordb_chroma_dir))
for item in client.list_collections():
    name = getattr(item, "name", item)
    collection = client.get_collection(name)
    print(f"{name}: {collection.count()}")
PY
```

Smoke test:

```bash
curl -fsS -X POST http://localhost:8000/api/ask \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Проверка после restore","tenant_id":"default"}' | jq .
```

#### Kubernetes

1. Остановить трафик:

```bash
kubectl -n "$NAMESPACE" scale deployment "${RELEASE}-app" --replicas=0
```

2. Восстановить Postgres:

```bash
cat "$BACKUP_ROOT/postgres/postgres-${timestamp}.dump" | \
kubectl -n "$NAMESPACE" run "pgrestore-${timestamp}" \
  --rm -i --restart=Never \
  --image=postgres:16-alpine \
  --env="DATABASE_URL=$DATABASE_URL" \
  -- sh -lc 'pg_restore "$DATABASE_URL" --clean --if-exists --no-owner --no-privileges'
```

3. Восстановить PVC / object storage для `uploads`, `tracing`, `vectordb/chroma`.

Текущий chart не создаёт PVC, поэтому универсальной `kubectl`-команды здесь нет. Используйте storage-layer snapshot restore для конкретного класса хранилища и только потом возвращайте replicas приложения.

4. Поднять приложение:

```bash
kubectl -n "$NAMESPACE" scale deployment "${RELEASE}-app" --replicas=2
kubectl -n "$NAMESPACE" rollout status deployment "${RELEASE}-app" --timeout=180s
```

5. Валидация:

```bash
kubectl -n "$NAMESPACE" port-forward "deployment/${RELEASE}-app" 8000:8000
curl -fsS http://127.0.0.1:8000/api/health/ready | jq .
curl -fsS http://127.0.0.1:8000/api/health | jq .
```

### 2.2 ChromaDB потерян, uploads и ключ целы

Важно: текущий `scripts/reindex.py` rebuild-ит векторную базу только из `data/uploads`. Если uploads тоже потеряны, этот сценарий не работает.

#### Docker Compose

```bash
docker compose stop app
mv data/vectordb/chroma "data/vectordb/chroma.lost.${timestamp}" 2>/dev/null || true
mkdir -p data/vectordb
docker compose run --rm app python scripts/reindex.py --all
docker compose up -d app
```

#### Kubernetes

Только при наличии PVC с `/app/data`:

```bash
kubectl -n "$NAMESPACE" exec "deployment/${RELEASE}-app" -- python scripts/reindex.py --all
```

Ожидаемое время: `<TBD после staging test>`.

Проверка:

```bash
docker compose exec -T app python - <<'PY'
import chromadb
from config.settings import get_settings
client = chromadb.PersistentClient(path=str(get_settings().vectordb_chroma_dir))
for item in client.list_collections():
    name = getattr(item, "name", item)
    print(name, client.get_collection(name).count())
PY
```

### 2.3 `DB_ENCRYPTION_KEY` скомпрометирован

Цель: как можно быстрее прекратить запись новых ciphertext старым ключом, перевыпустить секрет и пере-зашифровать чувствительные колонки.

#### Немедленные действия

```bash
docker compose stop app
kubectl -n "$NAMESPACE" scale deployment "${RELEASE}-app" --replicas=0
```

Сгенерировать новый ключ и сохранить его в offline vault. Не удаляйте старый ключ, пока не завершена ротация.

#### Не использовать

```bash
python scripts/rotate_encryption_key.py
```

Этот скрипт сейчас не выполняет rewrite ciphertext и не подходит для production rotation.

#### Реальная ротация в Postgres

Ниже SQL-процедура, которая пере-шифрует те же колонки, что миграция `008_enable_pgcrypto.py`.

```bash
cat <<'SQL' | docker compose exec -T postgres sh -lc '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 \
    -v old_key="$OLD_DB_ENCRYPTION_KEY" \
    -v new_key="$NEW_DB_ENCRYPTION_KEY"
'
BEGIN;
UPDATE messages
SET content = pgp_sym_encrypt(
  pgp_sym_decrypt(content, :'old_key'),
  :'new_key',
  'cipher-algo=aes256,compress-algo=0'
)
WHERE content IS NOT NULL;

UPDATE audit_log
SET detail = pgp_sym_encrypt(
  pgp_sym_decrypt(detail, :'old_key'),
  :'new_key',
  'cipher-algo=aes256,compress-algo=0'
)
WHERE detail IS NOT NULL;

UPDATE escalated_tickets
SET user_question = pgp_sym_encrypt(
      pgp_sym_decrypt(user_question, :'old_key'),
      :'new_key',
      'cipher-algo=aes256,compress-algo=0'
    ),
    ai_draft = CASE
      WHEN ai_draft IS NULL THEN NULL
      ELSE pgp_sym_encrypt(
        pgp_sym_decrypt(ai_draft, :'old_key'),
        :'new_key',
        'cipher-algo=aes256,compress-algo=0'
      )
    END,
    operator_response = CASE
      WHEN operator_response IS NULL THEN NULL
      ELSE pgp_sym_encrypt(
        pgp_sym_decrypt(operator_response, :'old_key'),
        :'new_key',
        'cipher-algo=aes256,compress-algo=0'
      )
    END
WHERE user_question IS NOT NULL;
COMMIT;
SQL
```

Для Kubernetes используйте тот же SQL через временный `postgres:16-alpine` pod против `$DATABASE_URL`.

#### После ротации

1. Обновить Secret / Vault path новым ключом.
2. Отозвать доступ к старому ключу.
3. Поднять приложение.
4. Проверить последние 7 дней трейсов на аномальные паттерны доступа.

Пример проверки локальных трейсов:

```bash
sqlite3 data/tracing/traces.db "
SELECT trace_id, started_at, final_route, final_quality
FROM traces
WHERE julianday(started_at) >= julianday('now', '-7 day')
ORDER BY started_at DESC
LIMIT 50;
"
```

### 2.4 `DB_ENCRYPTION_KEY` потерян

Честный ответ: зашифрованные значения невосстановимы. Без старого ключа нельзя расшифровать:

- `messages.content`
- `audit_log.detail`
- `escalated_tickets.user_question`
- `escalated_tickets.ai_draft`
- `escalated_tickets.operator_response`

#### Порядок действий

1. Немедленно остановить приложение.
2. Попытаться восстановить ключ из offline vault / sealed envelope.
3. Если ключ не найден, сохранить только незашифрованную часть системы и очистить irrecoverable данные.
4. Сгенерировать новый `DB_ENCRYPTION_KEY`.
5. Уведомить tenants и compliance: история сообщений и эскалаций частично или полностью потеряна.

#### SQL для salvage без старого ключа

`messages.content` и `escalated_tickets.user_question` объявлены как `NOT NULL`, поэтому здесь нужен не `NULL`, а удаление строк.

```bash
cat <<'SQL' | docker compose exec -T postgres sh -lc '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
'
BEGIN;
DELETE FROM messages;
UPDATE audit_log SET detail = NULL WHERE detail IS NOT NULL;
DELETE FROM escalated_tickets;
COMMIT;
SQL
```

После этого:

```bash
docker compose up -d app
docker compose exec -T app alembic upgrade head
```

Новые данные будут шифроваться новым ключом, но старые ciphertext уже потеряны навсегда.

### 2.5 Полный disaster recovery

#### Docker Compose

1. Подготовить новый хост и вернуть runtime secrets: `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `DB_ENCRYPTION_KEY`, `RAG_ENV`.
2. Поднять только инфраструктуру:

```bash
docker compose up -d postgres redis
```

3. Восстановить Postgres из дампа по процедуре `2.1`.
4. Восстановить `data/uploads`, `data/tracing`, `data/vectordb/chroma`.
5. Если Chroma snapshot нет, выполнить:

```bash
docker compose run --rm app python scripts/reindex.py --all
```

6. Поднять приложение:

```bash
docker compose up -d ollama ollama-init app
docker compose exec -T app alembic upgrade head
```

7. Выполнить валидацию и smoke test.

#### Kubernetes

1. Восстановить `DB_ENCRYPTION_KEY` через Secret / Vault.
2. Подготовить persistent storage для `/app/data` и внешний Postgres.
3. Выполнить `helm upgrade --install` текущего chart.
4. Держать `deployment/${RELEASE}-app` в `replicas=0`, пока не восстановлены данные.
5. Восстановить Postgres, затем PVC/object storage.
6. Если Chroma snapshot отсутствует, выполнить `scripts/reindex.py --all` в maintenance window.
7. Вернуть рабочее число реплик и дождаться `rollout status`.

## 3. Testing restore

Периодичность: ежемесячно.

### Full-restore verification

Для полной проверки `pg_dump -Fc` нужен отдельный disposable Postgres, а не
только распаковка snapshot layout. Для этого в репозитории есть
`docker-compose.test.yml` с единственным сервисом `postgres-test`
(`postgres:16-alpine`, random host-port через `ports: - "5432"`, без named
volume, healthcheck через `pg_isready`).

Стандартный flow:

```bash
python scripts/backup_snapshot.py --out /tmp/test-snap/20260423T120000Z
python scripts/restore_verify_integration.py \
  --snapshot /tmp/test-snap/20260423T120000Z
```

Что делает `scripts/restore_verify_integration.py`:

1. `docker-compose -f docker-compose.test.yml up -d postgres-test`
2. ждёт readiness через `pg_isready`
3. получает выделенный host-port через `docker-compose port postgres-test 5432`
4. вызывает `python scripts/restore_verify.py --postgres-url ...`
5. всегда выполняет `docker-compose -f docker-compose.test.yml down -v`

Postgres-ветка внутри `scripts/restore_verify.py` делает не smoke-layout, а
реальный restore:

- `pg_restore --clean --if-exists --dbname=<url> <snapshot>/postgres/postgres.dump`
- проверяет `alembic_version.version_num` против `snapshot_manifest.json`
- проверяет количество таблиц в `public`
- делает `SELECT * LIMIT 0` для всех ORM-таблиц из `db.models.Base.metadata`

Коды возврата:

- `0` — все restore/check steps зелёные
- `2` — layout smoke провалился
- `4` — ошибка `pg_restore` или post-restore проверки Postgres

Если нужно убедиться, что контейнер не завис после прогона:

```bash
docker-compose -f docker-compose.test.yml ps
docker-compose -f docker-compose.test.yml down -v
```

### Обязательный сценарий

1. Взять последний hourly backup Postgres и последний daily backup uploads / Chroma / SQLite.
2. Развернуть изолированный staging environment.
3. Восстановить все артефакты строго по разделу `2.1`.
4. Зафиксировать реальное время до:
   - готовности `/api/health/ready`;
   - завершения `pg_restore`;
   - появления ненулевых коллекций Chroma;
   - успешного smoke test `/api/ask`.
5. Сравнить фактические RPO / RTO с целевыми значениями из раздела `0`.

### Чеклист

- [ ] Backup отработал без ошибок.
- [ ] `pg_restore -l` на последнем dump проходит.
- [ ] Restore выполнен в staging из production backup.
- [ ] `GET /api/health/ready` возвращает `200`.
- [ ] Проверка коллекций Chroma показывает `count() > 0` для ожидаемых tenant.
- [ ] `POST /api/ask` проходит с валидным token.
- [ ] Отдельно протестирован сценарий `2.2` с rebuild через `scripts/reindex.py --all`.
- [ ] Зафиксировано время rebuild Chroma: `<TBD после staging test>`.
- [ ] Временные локальные артефакты удалены или перемещены в защищённый архив.

## 4. Checklist для production cutover

- [ ] `DB_ENCRYPTION_KEY` хранится в Vault / Secret, не в Git и не в ConfigMap.
- [ ] Backup bucket настроен с lifecycle: `7d hourly + 4w daily + 12m monthly`.
- [ ] Для k8s добавлены PVC или object storage для `/app/data`.
- [ ] Backup Postgres выполняется ежечасно.
- [ ] Backup `data/uploads`, `data/vectordb/chroma`, `data/tracing` выполняется ежедневно.
- [ ] Restore из последнего production backup проверен в staging.
- [ ] Есть отдельная офлайн-копия `DB_ENCRYPTION_KEY`.
- [ ] Alertmanager / Prometheus настроены на failure backup jobs.
- [ ] Документирован ответственный за восстановление и доступ к секретам.
- [ ] Команда знает, что `scripts/rotate_encryption_key.py` пока не рабочий для боевой ротации.

## 5. Key decisions

- Per-tenant isolation в Chroma существует на уровне collection name (`rag_docs_<tenant>`), но storage layout общий. Поэтому point restore одного tenant должен идти через export/import коллекции, а не через raw copy одного файла.
- `scripts/reindex.py --all` использует `data/uploads` как вход. Postgres не является источником для rebuild embeddings в текущей версии.
- `DB_ENCRYPTION_KEY` нельзя хранить рядом с данными. Бэкап ключа и бэкап Postgres должны быть разведены по разным системам контроля доступа.
- Текущий Helm chart неполон для production backup/restore: нет `Secret` для `DB_ENCRYPTION_KEY` и нет PVC-манифестов для `/app/data`.
- Трейсы и feedback всё ещё пишутся в `data/tracing/traces.db`; потеря этого файла не ломает ответы, но ломает расследование инцидентов и `/api/metrics`.
- `scripts/rotate_encryption_key.py` сейчас только подтверждает, что env variables переданы; фактическую ротацию выполняем SQL-процедурой.
- Ollama-модели не включаем в backup scope: при DR их нужно заново подтянуть стандартным деплоем.
