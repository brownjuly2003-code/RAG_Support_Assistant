# Task R2 — Research: мониторинг production RAG-сервиса (2025)

## Goal
При 1000+ req/day нужно знать: система деградирует? какие метрики важны?
когда бить тревогу? Выяснить best practices для lightweight production monitoring.

## Context
- Стек: FastAPI + LangGraph + Ollama (локальная LLM) + ChromaDB + SQLite
- Трейсинг уже есть: SQLite хранит trace_id, route, quality_score, latency
- Фидбек уже есть: таблица feedback с up/down
- Нет: внешнего мониторинга, алертов, дашборда

## Research questions

### Q1: Ключевые метрики для production RAG support-сервиса

Найди: что отслеживают зрелые RAG-системы поддержки в 2025?

```
[Топ-7 метрик с порогами тревоги — конкретные числа]:
1. [метрика]: норма [...], тревога [...]
2. [метрика]: норма [...], тревога [...]
...
[Источник: ...]
```

**Обязательно включи:**
- Latency (p50, p95, p99) — нормы для RAG с локальной LLM
- Escalation rate (доля human-route) — сколько нормально?
- Quality score distribution — когда average падение — сигнал?
- Error rate — порог для алерта
- Feedback rate (thumbs down / total responses)

### Q2: Lightweight мониторинг без тяжёлых зависимостей

Varианты без Prometheus/Grafana/Datadog для local-first деплоя:

```
[Вариант 1 — SQLite-based analytics (уже есть в проекте):] 
[Как добавить aggregated views, периодические checks: ...]

[Вариант 2 — OpenTelemetry минимальный:] 
[Стоимость внедрения в FastAPI: ...]
[Годится ли для 1000 req/day без collector overhead: ...]

[Вариант 3 — простой /api/metrics endpoint (текстовый):] 
[Формат: plain text или JSON? Prometheus exposition format?]
[Сложность реализации: ...]
```

### Q3: Интеграция с существующим SQLite трейсингом

У нас уже есть таблицы `traces` (trace_id, final_route, final_quality, latency) и `feedback`.
Как вытащить из них нужные агрегаты без доп. инфраструктуры?

```
[SQL-запросы для ключевых метрик — дай реальный SQL]:

-- Escalation rate за последние 24h
[SELECT ...]

-- Average quality_score за последние 7 дней  
[SELECT ...]

-- p95 latency за последние 24h
[SELECT ...]

-- Thumbs down rate за последние 7 дней
[SELECT ...]
```

### Q4: Алертинг без внешних сервисов

Как реализовать простые алерты в локальном деплое:
- Email (SMTP) — сложность vs ценность?
- Запись в файл + logrotate + grep?
- Webhook (Slack/Telegram) — насколько стандартно?
- Scheduled check (cron) vs inline check в FastAPI

```
[Рекомендуемый минимальный алерт-механизм для нашего стека: ...]
[Реализация: ...]
[Источник: ...]
```

### Q5: LangSmith / TruLens для production monitoring

Из eval-metrics-2025.md — LangSmith и TruLens упомянуты как варианты.
Годятся ли для production monitoring (не только batch eval)?

```
[LangSmith: подходит для онлайн мониторинга? стоимость при 1000 req/day? ...]
[TruLens: есть ли production dashboard для ongoing monitoring? ...]
[Рекомендация: использовать или хватит SQLite: ...]
```

---

## Output: Implementation plan

```
РЕКОМЕНДУЕМЫЙ ПОДХОД:
[lightweight / SQLite-first / внешний сервис]

Ключевые метрики для алертов (конкретные пороги):
1. escalation_rate > [X]% → алерт
2. avg_quality < [Y] → алерт
3. error_rate > [Z]% → алерт
4. p95_latency > [N]s → алерт

Реализация за минимум усилий:
[шаги с конкретными файлами которые нужно добавить]
```

## CONSTRAINTS
- Только заполнить `[...]`, сохранить как `docs/research/production-monitoring-2025.md`
- SQL-запросы должны работать с реальной схемой: таблицы `traces`, `trace_steps`, `feedback`
- Никаких изменений в коде

## DONE WHEN
- [ ] `docs/research/production-monitoring-2025.md` существует
- [ ] Есть таблица 7 метрик с порогами
- [ ] Есть реальные SQL-запросы для агрегаций
- [ ] Есть конкретная рекомендация по алертингу
- [ ] Все `[...]` заполнены
