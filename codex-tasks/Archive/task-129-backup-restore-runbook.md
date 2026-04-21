# Task 129 — Backup / restore runbook

## Goal
Написать операционный runbook для резервного копирования и восстановления системы. С encryption at rest (task-113) и per-tenant ChromaDB (task-96) процедура нетривиальна и требует документирования, иначе disaster recovery = рулетка.

## Context
- Repo: `D:\RAG_Support_Assistant` (FastAPI + LangGraph + ChromaDB + Ollama, Postgres, Redis).
- Компоненты, требующие резервирования:
  - **Postgres** — основное состояние: users, tenants, traces, audit, escalations, eval_results, knowledge_gaps, kb_drafts, document_stats, trace_costs. Миграции 001-011 через Alembic.
  - **ChromaDB** — vector store, per-tenant изоляция (task-96). Файлы на диске (persistent client) или внешний сервис — смотреть `vectordb/manager.py` для текущей схемы.
  - **Redis** — LLM response cache (task-100), feature-flagged. Не критичен, но warm-up после restore ускорит прогрев.
  - **Encryption key** (`ENCRYPTION_KEY`, task-113) — без него Postgres-данные частично непригодны (AES-шифрованные колонки + pgcrypto). **Самая критичная секция runbook** — ротация / компрометация / потеря ключа.
  - **Uploaded documents** — если хранятся на диске (`data/`, `ingestions/`) или в object storage.
- Deploy контексты:
  - Docker Compose — `docker-compose.yml` (dev/single-host).
  - Helm chart — `deploy/helm/` (k8s prod).
- Ротация ключа: `scripts/rotate_encryption_key.py` (task-113, нужно проверить, что он есть и рабочий).
- Reindex: `scripts/reindex.py` — для rebuild Chroma из Postgres source-of-truth, если vector store потерян.

## Deliverables
`docs/operations/backup-restore.md`:

```markdown
# Backup & restore runbook

Аудитория: оператор / SRE. Предполагается знание Docker Compose или Kubernetes.

## 0. Что резервируем — overview

| Компонент | Критичность | RPO target | RTO target | Источник истины |
|-----------|-------------|------------|------------|------------------|
| Postgres | critical | 1h | 30m | — |
| ChromaDB | high | 24h | 2h | Postgres (можно reindex) |
| Encryption key | critical | immutable | 5m | offline vault |
| Redis | low | — | — | — (cache, теряем без последствий) |
| Uploaded docs (`data/`) | high | 24h | 1h | — |

## 1. Backup procedure

### 1.1 Postgres
(команды для docker-compose и для helm/k8s раздельно; `pg_dump -Fc`, хранение в S3/MinIO, retention policy)

### 1.2 ChromaDB
(зависит от persistent client: tar.gz persistent path vs snapshot API; per-tenant — один архив на tenant, НЕ объединять)

### 1.3 Encryption key
(offline storage — пошагово: где хранить, как ротировать, кто имеет доступ; никогда не бэкапить ключ в тот же vault, что данные)

### 1.4 Uploaded documents
(если `data/` на volume — snapshot; если в S3 — cross-region replication)

### 1.5 Автоматизация
(cron / k8s CronJob YAML пример, notification при failure в Prometheus alerting)

## 2. Restore procedure

### 2.1 Standard restore (данные + ключ целы)
Шаги по порядку:
1. Остановить приложение (`docker compose stop app` или `kubectl scale deployment app --replicas=0`).
2. Восстановить Postgres из backup (конкретная команда `pg_restore`).
3. Восстановить ChromaDB per-tenant архивы.
4. Восстановить uploaded docs.
5. Валидация: `/api/health/ready` возвращает 200, `/api/metrics` показывает document_count > 0 per tenant.
6. Smoke test: `curl` на `/api/ask` с тестовым query.

### 2.2 ChromaDB потерян, Postgres цел
1. Отключить приложение от Chroma (feature flag или env).
2. Запустить `scripts/reindex.py --all-tenants` (параметры: концур, batch-size).
3. Ожидаемое время: ~N минут на M документов (ориентир).
4. Валидация.

### 2.3 ENCRYPTION_KEY скомпрометирован
1. НЕМЕДЛЕННО выставить `MAINTENANCE_MODE=true` (если есть) или scale to 0.
2. Сгенерировать новый ключ.
3. Запустить `scripts/rotate_encryption_key.py --old=<old_key_env> --new=<new_key_env>` в maintenance mode.
4. Обновить секрет в Vault / k8s Secret.
5. Rollout приложения.
6. Аудит: проверить трейсы за последние 7 дней на подозрительные паттерны доступа.

### 2.4 ENCRYPTION_KEY ПОТЕРЯН
Шифрованные данные — невосстановимы. Что делать:
1. Идентифицировать зашифрованные колонки (`db/models.py` — поиск EncryptedString / pgcrypto использований).
2. Drop / NULL шифрованные данные.
3. Уведомить tenants (compliance).
4. Перегенерировать ключ; новые данные шифруются новым.

### 2.5 Полный disaster recovery
(все потеряно — пошагово с нуля до работающего состояния, включая helm install / docker compose up, миграции Alembic, reindex)

## 3. Testing restore (важно!)
- Периодичность: ежемесячно.
- Checklist:
  - [ ] Backup прошёл без ошибок (crud retry, incremental проверка).
  - [ ] Restore в staging environment из боевого бэкапа.
  - [ ] Smoke test на восстановленной копии.
  - [ ] Временные артефакты удалены.

## 4. Checklist для production cutover
(перед первым выводом бота в прод — краткий чеклист: ключ в vault, бэкапы настроены, alerts привязаны, restore протестирован)

## 5. Key decisions (not obvious)
- Per-tenant изоляция Chroma — тоже backup per-tenant, не одним архивом, чтобы случайный restore одного tenant не тронул других.
- ENCRYPTION_KEY никогда в git / env-файлах / Docker image — только runtime (K8s Secret / Vault / Docker secret).
- Retention Postgres-бэкапов: 7 дней hourly + 4 недели daily + 12 месяцев monthly (или адаптировать).
```

## Acceptance
- Все 5 разделов покрыты, не пустые.
- Каждая команда копипастабельна (конкретные версии, правильные флаги, без <placeholder>, где можно — реальные пути из репо).
- Разделено docker-compose vs k8s для каждой команды, где отличается.
- Секция 2.4 (потеря ключа) — присутствует, честная (не "всё ок"), с конкретными шагами.
- Секция 3 (тестирование restore) — с чеклистом, не просто "рекомендуется".
- Файл на русском, UTF-8, Markdown.
- Сохранён: `docs/operations/backup-restore.md` (создать `docs/operations/` если нет).

## Notes
- **НЕ писать код** — только документация.
- **НЕ запускать backup / restore** — они тестируются отдельно.
- Источники данных для команд: `docker-compose.yml`, `deploy/helm/values.yaml`, `db/models.py`, `vectordb/manager.py`, `scripts/{reindex,rotate_encryption_key}.py`.
- Проверить, что `scripts/rotate_encryption_key.py` реально существует и что он делает (task-113 должен был его создать).
- Если `scripts/reindex.py` не покрывает все tenant'ы одним вызовом — уточнить в runbook как запускать per-tenant.
- Для k8s-команд исходить из предположения, что namespace = `rag-support` (или глянуть в helm values default); если неясно — `<namespace>` как placeholder и отметить.
- Если какая-то из процедур НЕ может быть описана без запуска (например, точное время reindex) — вставить `<TBD после staging test>` и описать как оценить.
- Не включать процедуры для Ollama (модели — derivable, не backup-worthy в классическом смысле; упомянуть одной строкой).
