# Research: мониторинг production RAG-сервиса (2025)

## Goal
При 1000+ запросов в день для FastAPI + LangGraph + Ollama + ChromaDB + SQLite нужен lightweight-monitoring без тяжёлой внешней инфраструктуры.

Локальный контекст проекта:

- уже есть `traces`
- уже есть `trace_steps`
- уже есть `feedback`
- `feedback` хранит `up/down`
- в текущей схеме latency можно восстановить как `finished_at - started_at`
- точный HTTP error rate из текущей схемы не восстановить: отдельного `status_code` или `error_type` сейчас нет

## Q1: Ключевые метрики для production RAG support-сервиса

Официальные источники хорошо согласуются по самим классам сигналов:

- Google SRE: latency, errors, traffic, saturation как базовые "golden signals"
- LangSmith / TruLens: качество ответа, groundedness / answer relevance, human feedback, trace-level observability

Но конкретные числа-пороги для local-first RAG почти всегда приходится задавать как стартовые SLO, а потом калибровать по своей истории. Поэтому пороги ниже — это рекомендуемые начальные thresholds для этого проекта, а не "общепринятый industry standard для всех RAG".

### Топ-7 метрик с порогами тревоги

1. `p50_latency`
   норма: `<= 4s`
   тревога: `> 6s` в окне 30 минут

2. `p95_latency`
   норма: `<= 8s`
   тревога: `> 12s` в окне 30 минут

3. `p99_latency`
   норма: `<= 15s`
   тревога: `> 20s` в окне 30 минут

4. `escalation_rate`
   норма: `10-25%`
   тревога: `> 35%` за 24 часа или `> +15 п.п.` к своей 7-дневной базе

5. `avg_quality_score` и `low_quality_share`
   норма: `avg_quality >= 75`, доля ответов `< 60` не выше `15%`
   тревога: `avg_quality < 65` или `low_quality_share > 30%` за 24 часа

6. `error_rate`
   норма: `< 1%`
   тревога: `> 5%` за 5 минут или `> 2%` за 30 минут

7. `thumbs_down_rate`
   норма: `< 10%`
   тревога: `> 20%` за 7 дней при размере выборки хотя бы `50` feedback events

Источник:

- Google SRE объясняет, что latency и errors должны быть симптомами первого класса, а не второстепенными метриками
- LangSmith и TruLens дополняют это LLM/RAG-специфичными сигналами: quality, groundedness, human feedback, trace analytics

Практический вывод:

- Для вашего стека тревоги должны быть завязаны не только на "жив ли API", но и на деградацию маршрутизации и качества.
- `escalation_rate`, `quality_score` и `thumbs_down_rate` для support-RAG не менее важны, чем HTTP health.

## Q2: Lightweight monitoring без Prometheus/Grafana/Datadog

### Вариант 1 — SQLite-based analytics

Рекомендуемый вариант для текущего проекта.

Как добавить aggregated views и periodic checks:

- держать источник истины в SQLite, потому что traces и feedback уже там
- каждые 5 минут запускать scheduled-check script
- script считает агрегаты за `5m`, `30m`, `24h`, `7d`
- script сравнивает значения с порогами и пишет:
  - локальный JSON snapshot
  - alert log
  - webhook в Slack/Telegram при нарушении

Почему это лучший вариант:

- минимум новых зависимостей
- нет отдельного collector
- не нужно поднимать Prometheus/Grafana ради 1000 req/day
- хорошо ложится на текущую архитектуру и существующий traces UI

### Вариант 2 — OpenTelemetry минимальный

Стоимость внедрения в FastAPI:

- низкая, если нужен только базовый instrumentation layer
- средняя, если нужен полноценный OTLP backend и нормальный dashboard

Годится ли для `1000 req/day` без collector overhead:

- как библиотека instrumentation — да
- как "минимальная production monitoring система сама по себе" — нет, потому что OTel без backend почти ничего не показывает

Вывод:

- OTel имеет смысл, если вы заранее планируете потом отгружать telemetry наружу
- если цель на ближайший релиз — быстро и дёшево увидеть деградацию, `SQLite-first` проще и выгоднее

### Вариант 3 — простой `/api/metrics` endpoint

Формат:

- `JSON` — лучший минимальный вариант для внутреннего UI и scheduled checker
- Prometheus exposition format имеет смысл только если вы реально будете его скрейпить

Сложность реализации:

- низкая
- хороший next step поверх SQLite analytics

Вывод:

- оптимальная комбинация: `SQLite aggregates + /api/metrics JSON + scheduled alert checker`

## Q3: Интеграция с существующим SQLite tracing

Ниже SQL, который работает с вашей реальной схемой `traces`, `trace_steps`, `feedback`.

### Escalation rate за последние 24h

```sql
SELECT
    COUNT(*) AS total_traces,
    SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END) AS escalated_traces,
    ROUND(
        100.0 * SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        1
    ) AS escalation_rate_pct
FROM traces
WHERE julianday(started_at) >= julianday('now', '-1 day');
```

### Average quality_score за последние 7 дней

```sql
SELECT
    COUNT(final_quality) AS scored_traces,
    ROUND(AVG(final_quality), 1) AS avg_quality,
    ROUND(
        100.0 * SUM(CASE WHEN final_quality < 60 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(final_quality), 0),
        1
    ) AS low_quality_share_pct
FROM traces
WHERE final_quality IS NOT NULL
  AND julianday(started_at) >= julianday('now', '-7 day');
```

### p95 latency за последние 24h

```sql
WITH latencies AS (
    SELECT
        (julianday(finished_at) - julianday(started_at)) * 86400.0 AS latency_sec
    FROM traces
    WHERE finished_at IS NOT NULL
      AND julianday(started_at) >= julianday('now', '-1 day')
),
ranked AS (
    SELECT
        latency_sec,
        ROW_NUMBER() OVER (ORDER BY latency_sec) AS rn,
        COUNT(*) OVER () AS total
    FROM latencies
)
SELECT ROUND(MIN(latency_sec), 2) AS p95_latency_sec
FROM ranked
WHERE rn >= total * 0.95;
```

### p50 / p99 latency шаблон

```sql
WITH latencies AS (
    SELECT
        (julianday(finished_at) - julianday(started_at)) * 86400.0 AS latency_sec
    FROM traces
    WHERE finished_at IS NOT NULL
      AND julianday(started_at) >= julianday('now', '-1 day')
),
ranked AS (
    SELECT
        latency_sec,
        ROW_NUMBER() OVER (ORDER BY latency_sec) AS rn,
        COUNT(*) OVER () AS total
    FROM latencies
)
SELECT
    ROUND(MIN(CASE WHEN rn >= total * 0.50 THEN latency_sec END), 2) AS p50_latency_sec,
    ROUND(MIN(CASE WHEN rn >= total * 0.99 THEN latency_sec END), 2) AS p99_latency_sec
FROM ranked;
```

### Thumbs down rate за последние 7 дней

```sql
SELECT
    COUNT(*) AS total_feedback,
    SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END) AS thumbs_down,
    ROUND(
        100.0 * SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        1
    ) AS thumbs_down_rate_pct
FROM feedback
WHERE julianday(ts) >= julianday('now', '-7 day');
```

### Thumbs up/down по маршруту за последние 7 дней

```sql
SELECT
    COALESCE(t.final_route, 'unknown') AS route,
    SUM(CASE WHEN f.rating = 'up' THEN 1 ELSE 0 END) AS up_count,
    SUM(CASE WHEN f.rating = 'down' THEN 1 ELSE 0 END) AS down_count
FROM feedback f
LEFT JOIN traces t ON t.trace_id = f.trace_id
WHERE julianday(f.ts) >= julianday('now', '-7 day')
GROUP BY COALESCE(t.final_route, 'unknown')
ORDER BY route;
```

### Current-schema proxy для error rate

Точного error rate сейчас нет, потому что в схеме нет HTTP status / terminal error field.
Лучший proxy без изменения схемы:

```sql
SELECT
    COUNT(*) AS total_started,
    SUM(
        CASE
            WHEN finished_at IS NULL
             AND julianday(started_at) < julianday('now', '-15 minute')
            THEN 1 ELSE 0
        END
    ) AS likely_failed,
    ROUND(
        100.0 * SUM(
            CASE
                WHEN finished_at IS NULL
                 AND julianday(started_at) < julianday('now', '-15 minute')
                THEN 1 ELSE 0
            END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS likely_failure_rate_pct
FROM traces
WHERE julianday(started_at) >= julianday('now', '-1 day');
```

Вывод:

- `latency`, `escalation`, `quality`, `feedback` уже можно агрегировать прямо сейчас
- `error_rate` лучше сделать отдельной first-class метрикой в следующем изменении схемы или API logging

## Q4: Алертинг без внешних сервисов

### Что реально стоит делать

Рекомендуемый минимальный alert-механизм для вашего стека:

- scheduled check каждые 5 минут
- SQL против SQLite
- hysteresis: слать alert только если порог нарушен 2 запуска подряд
- delivery:
  - webhook в Slack/Telegram как основной канал
  - локальный `alerts.log` как backup trail

### Что не стоит делать как primary mechanism

- `inline` проверки внутри FastAPI request path
  - будут добавлять latency
  - могут дублировать алерты
  - смешивают serving path и ops-логику

- только `file + grep`
  - годится как fallback
  - плохо работает как основной alert transport

- SMTP-first
  - можно, но обычно больше operational friction, чем пользы, если уже доступен webhook

Вывод:

- `scheduled checker + webhook + alert log` — лучший minimum viable alerting

## Q5: LangSmith / TruLens для production monitoring

### LangSmith

- подходит для online monitoring, human review, online evaluators, trace analytics
- есть self-hosted / hybrid варианты
- хорош, если вам нужен не просто alerting, а полноценный observability/evaluation слой

Ограничение для вашего кейса:

- для `1000 req/day` local-first стека это уже другой operational tier
- если использовать online evaluators c judge LLM, стоимость и сложность быстро растут

### TruLens

- подходит для production-style dashboard
- силён именно в RAG-specific observability: RAG Triad, feedback functions, dashboard
- имеет более прямую связку с groundedness / answer relevance, чем голый SQLite

Ограничение:

- всё ещё тяжелее, чем ваш текущий стек реально требует на данном объёме

### Рекомендация

- сейчас: `SQLite-first`
- позже, если понадобится richer dashboard по groundedness/relevance: смотреть в сторону `TruLens`
- `LangSmith` брать только если появится явная потребность в platform-level eval/trace workflow и команда готова к отдельному сервисному слою

## Output: Implementation plan

```text
РЕКОМЕНДУЕМЫЙ ПОДХОД:
lightweight / SQLite-first / без внешнего collector

Ключевые метрики для алертов (конкретные пороги):
1. escalation_rate > 35% -> алерт
2. avg_quality < 65 или low_quality_share > 30% -> алерт
3. likely_failure_rate > 5% за 5m или > 2% за 30m -> алерт
4. p95_latency > 12s -> алерт
5. thumbs_down_rate > 20% за 7d при sample >= 50 -> алерт

Реализация за минимум усилий:
1. Добавить SQLite aggregate helpers в sqlite_trace.py
2. Добавить GET /api/metrics (JSON) в api/app.py
3. Добавить scripts/check_alerts.py с порогами и webhook delivery
4. Добавить env-параметры порогов и webhook URL в config/settings.py или .env.example
5. Опционально добавить простую internal monitoring page поверх /api/metrics
```

## Sources

- Google SRE, Monitoring Distributed Systems:
  https://sre.google/sre-book/monitoring-distributed-systems/
- OpenTelemetry Python getting started:
  https://opentelemetry.io/docs/languages/python/getting-started/
- LangSmith evaluation concepts:
  https://docs.langchain.com/langsmith/evaluation-concepts
- LangSmith evaluation:
  https://docs.langchain.com/langsmith/evaluation
- LangSmith intermediate-step evaluation:
  https://docs.langchain.com/langsmith/evaluate-on-intermediate-steps
- TruLens dashboard:
  https://www.trulens.org/getting_started/dashboard/
- TruLens RAG Triad:
  https://www.trulens.org/getting_started/core_concepts/rag_triad/
- TruLens feedback / embeddings:
  https://www.trulens.org/reference/trulens/feedback/embeddings/

## Confidence summary

| Theme | Confidence | Basis |
|---|---|---|
| Какие метрики смотреть | High | SRE + LangSmith + TruLens согласуются |
| SQLite-first как первый шаг | High | уже есть нужные таблицы и low request volume |
| Конкретные численные пороги | Medium | это recommended starting thresholds, а не vendor defaults |
| SQL по traces/feedback | High | основано на реальной схеме проекта |
