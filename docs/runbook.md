# RAG Support Assistant Runbook

> Краткий runbook для дежурного оператора.

## Что важно помнить

- Все алерты проверяются через `python scripts/check_alerts.py`.
- Hysteresis включён: webhook уходит только если одно и то же правило нарушено 2 запуска подряд.
- Основной источник истины по метрикам: `GET /api/metrics`.
- Основной источник истины по состоянию инфраструктуры: `GET /api/health`.
- SQLite трассировка лежит в `data/tracing/traces.db`.

## Быстрая диагностика

```powershell
# Текущий снимок метрик
Invoke-RestMethod http://localhost:8000/api/metrics | ConvertTo-Json -Depth 6

# Состояние зависимостей
Invoke-RestMethod http://localhost:8000/api/health | ConvertTo-Json -Depth 6

# Ручной прогон алертов без отправки webhook
python scripts/check_alerts.py --dry-run

# Последние записи журнала алертов
Get-Content data/alerts.log -Tail 40
```

Открой в браузере:

- `http://localhost:8000/static/metrics.html` для общего статуса.
- `http://localhost:8000/traces-ui` для просмотра последних трасс.

## Порядок разбора

1. Сначала проверь `/api/health`. Если `ollama` или `chromadb` в статусе `error`, сначала чини инфраструктуру.
2. Потом открой `/api/metrics` и сравни, какая метрика красная.
3. Затем смотри конкретные trace_id через SQL и страницу `/traces-ui/{trace_id}`.

## Алерты и действия

### `escalation_rate > 35%` за 24 часа

Что значит: слишком много запросов уходит на маршрут `human`.

Диагностика:

```powershell
sqlite3 data/tracing/traces.db "
SELECT trace_id, started_at, finished_at, final_route, final_quality
FROM traces
WHERE final_route = 'human'
  AND julianday(started_at) >= julianday('now', '-1 day')
ORDER BY started_at DESC
LIMIT 20;
"
```

После этого открой подозрительные трассы:

```powershell
Invoke-RestMethod http://localhost:8000/traces/<trace_id> | ConvertTo-Json -Depth 8
```

Что делать:

1. Если `/api/health` показывает проблему с `ollama`, восстанови Ollama и повтори dry-run.
2. Если проблема в `chromadb`, проверь наличие и целостность векторной базы, затем переиндексируй документы через `POST /api/upload`.
3. Если инфраструктура здорова, но `final_quality` у проблемных трасс низкий, обнови базу знаний и проверь последние загруженные документы.
4. Если эскалации растут без явных инфраструктурных ошибок, посмотри шаги `retrieve`, `grade_docs` и `evaluate` в `/traces-ui/{trace_id}`.

### `avg_quality < 65` за 7 дней

Что значит: средняя итоговая оценка ответов деградировала.

Диагностика:

```powershell
sqlite3 data/tracing/traces.db "
SELECT ROUND(AVG(final_quality), 1) AS avg_quality,
       COUNT(final_quality) AS scored_traces
FROM traces
WHERE final_quality IS NOT NULL
  AND julianday(started_at) >= julianday('now', '-7 day');
"
```

```powershell
sqlite3 data/tracing/traces.db "
SELECT trace_id, started_at, final_quality, final_route
FROM traces
WHERE final_quality IS NOT NULL
  AND julianday(started_at) >= julianday('now', '-7 day')
ORDER BY final_quality ASC
LIMIT 20;
"
```

Что делать:

1. Открой худшие trace_id в `/traces-ui/{trace_id}` и проверь, что было найдено на шаге `retrieve`.
2. Если контекст нерелевантен, обнови документы и повторно загрузи их через `POST /api/upload`.
3. Если контекст нормальный, но ответы всё равно слабые, прогони `python evaluation/benchmark_runner.py`.
4. Если деградация совпала с изменением retrieval-настроек, пересмотри `RAG_RETRIEVAL_TOP_K` и `RAG_RERANK_TOP_K`.

### `low_quality_share > 30%` за 7 дней

Что значит: слишком большая доля ответов имеет `final_quality < 60`.

Диагностика:

```powershell
sqlite3 data/tracing/traces.db "
SELECT COUNT(final_quality) AS scored_traces,
       SUM(CASE WHEN final_quality < 60 THEN 1 ELSE 0 END) AS low_quality_traces,
       ROUND(
         100.0 * SUM(CASE WHEN final_quality < 60 THEN 1 ELSE 0 END)
         / NULLIF(COUNT(final_quality), 0),
         1
       ) AS low_quality_share_pct
FROM traces
WHERE final_quality IS NOT NULL
  AND julianday(started_at) >= julianday('now', '-7 day');
"
```

```powershell
sqlite3 data/tracing/traces.db "
SELECT trace_id, started_at, final_quality, final_route
FROM traces
WHERE final_quality < 60
  AND julianday(started_at) >= julianday('now', '-7 day')
ORDER BY final_quality ASC
LIMIT 20;
"
```

Что делать:

1. Найди повторяющиеся типы неудачных вопросов по trace_id и шагам в `/traces-ui/{trace_id}`.
2. Если низкое качество связано с пробелами в базе знаний, добавь недостающие документы.
3. Если много вопросов вне домена, проверь пользовательские инструкции и эскалационный маршрут.
4. Если почти все плохие ответы идут через `auto`, пересмотри порог качества для автоответа и логику оценки.

### `p95_latency > 12s` за 24 часа

Что значит: хвост задержек слишком большой, пользователи видят долгие ответы.

Диагностика:

```powershell
sqlite3 data/tracing/traces.db "
SELECT trace_id,
       started_at,
       finished_at,
       ROUND((julianday(finished_at) - julianday(started_at)) * 86400.0, 1) AS latency_sec,
       final_route
FROM traces
WHERE finished_at IS NOT NULL
  AND julianday(started_at) >= julianday('now', '-1 day')
ORDER BY latency_sec DESC
LIMIT 10;
"
```

```powershell
Invoke-RestMethod http://localhost:11434/api/tags | ConvertTo-Json -Depth 5
```

Что делать:

1. Если Ollama отвечает медленно или нестабильно, сначала восстанови её доступность.
2. Если модель работает, но latency стабильно высокая, снизь `RAG_RETRIEVAL_TOP_K`.
3. Если узкое место в rerank, снизь `RAG_RERANK_TOP_K`.
4. Если рост задержки постоянный и связан с ресурсами хоста, вынеси Ollama на отдельную машину или усили хост.

### `thumbs_down_rate > 20%` за 7 дней при `n >= 50`

Что значит: заметная доля пользователей недовольна ответами.

Диагностика:

```powershell
Invoke-RestMethod http://localhost:8000/api/feedback/stats | ConvertTo-Json -Depth 6
```

```powershell
sqlite3 data/tracing/traces.db "
SELECT f.ts, f.trace_id, f.reason, t.final_quality, t.final_route
FROM feedback f
LEFT JOIN traces t ON t.trace_id = f.trace_id
WHERE f.rating = 'down'
  AND julianday(f.ts) >= julianday('now', '-7 day')
ORDER BY f.ts DESC
LIMIT 20;
"
```

Что делать:

1. Сначала посмотри `reason` и раздели жалобы на фактические ошибки и проблемы формата ответа.
2. Если `final_quality` тоже низкий, обнови документы и проверь retriever.
3. Если фактически ответы верны, но обратная связь плохая, пересмотри prompt и формат выдачи.
4. Если за 7 дней меньше 50 оценок, не делай вывод по rate отдельно от алерта: выборка мала.

## Перезапуск сервиса

```powershell
# Docker-вариант
docker compose restart app

# Проверка после рестарта
Invoke-RestMethod http://localhost:8000/api/health | ConvertTo-Json -Depth 6
```

Если сервис запущен локально не через Docker, перезапусти тот процесс, которым поднимался `python main.py`, и затем снова проверь `/api/health`.

## Сброс hysteresis

```powershell
Set-Content -LiteralPath data/alerts_state.json -Value '{}'
```

Используй сброс только после осознанного разбора инцидента, иначе потеряешь накопленный счётчик повторных нарушений.
