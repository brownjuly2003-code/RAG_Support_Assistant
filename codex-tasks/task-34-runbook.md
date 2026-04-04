# Task 34 — docs/runbook.md: operational playbook

## Goal
Создать `docs/runbook.md` — краткий runbook для оператора:
что означает каждый алерт, как диагностировать и что делать.
Без Codex это не сделать — нужна связка всех метрик + порогов + команд.

## Background
Пороги из `.env.example` и `scripts/check_alerts.py`:
- `escalation_rate > 35%` (24h)
- `avg_quality < 65` (7d)
- `low_quality_share > 30%` (7d)
- `p95_latency > 12s` (24h)
- `thumbs_down_rate > 20%` (7d, при n >= 50)

Инструменты диагностики, уже существующие в проекте:
- `GET /api/metrics` — текущий снапшот
- `GET /api/health` — статус Ollama / ChromaDB / SQLite
- `python scripts/check_alerts.py --dry-run` — ручная проверка
- `data/alerts.log` — лог алертов
- `/static/metrics.html` — браузерный дашборд

## Files to create
- `docs/runbook.md`

---

## docs/runbook.md

```markdown
# RAG Support Assistant — Runbook

> Оперативный справочник для дежурного оператора.

## Быстрая диагностика

```bash
# Текущий снапшот метрик
curl http://localhost:8000/api/metrics | python -m json.tool

# Состояние сервисов
curl http://localhost:8000/api/health

# Ручная проверка алертов
python scripts/check_alerts.py --dry-run

# Лог алертов
tail -40 data/alerts.log
```

Или открой в браузере: http://localhost:8000/static/metrics.html

---

## Алерты и действия

### escalation_rate > 35% (24h)

**Что значит:** больше трети запросов уходит к оператору автоматически.

**Диагностика:**
```bash
# Последние эскалированные запросы
sqlite3 data/traces.db "
  SELECT question, final_quality, final_route, started_at
  FROM traces
  WHERE final_route = 'human'
    AND julianday(started_at) >= julianday('now', '-1 day')
  ORDER BY started_at DESC LIMIT 20;"
```

**Действия:**
1. Если качество ответов низкое (quality < 60) — проверь доступность Ollama: `curl http://localhost:11434/api/tags`
2. Если Ollama недоступна — перезапусти: `ollama serve` или `docker compose restart ollama`
3. Если Ollama работает, но качество низкое — возможно устарела база знаний. Загрузи новые документы через `POST /api/upload`
4. Если эскалации по `route=error` — смотри лог ошибок: `grep '"route":"error"' data/traces.db` или логи приложения

---

### avg_quality < 65 (7d)

**Что значит:** средний балл качества ответов за неделю ниже порога.

**Диагностика:**
```bash
sqlite3 data/traces.db "
  SELECT ROUND(AVG(final_quality), 1), COUNT(*)
  FROM traces
  WHERE julianday(started_at) >= julianday('now', '-7 day')
    AND final_quality IS NOT NULL;"
```

**Действия:**
1. Проверь последние загруженные документы — возможно добавили нерелевантный контент
2. Если база знаний актуальна — рассмотри увеличение `RAG_RERANK_TOP_K` (5 → 7)
3. Запусти бенчмарк: `python evaluation/benchmark_runner.py`

---

### low_quality_share > 30% (7d)

**Что значит:** более 30% ответов имеют quality < 60 за неделю.

**Диагностика:**
```bash
sqlite3 data/traces.db "
  SELECT question, final_quality, started_at
  FROM traces
  WHERE final_quality < 60
    AND julianday(started_at) >= julianday('now', '-7 day')
  ORDER BY final_quality ASC LIMIT 20;"
```

**Действия:**
1. Найди паттерны в вопросах с низким качеством — возможно нужен новый раздел в базе знаний
2. Если много вопросов вне области — рассмотри улучшение промпта в `graph/graph.py`

---

### p95_latency > 12s (24h)

**Что значит:** 95-й перцентиль времени ответа превышает 12 секунд.

**Диагностика:**
```bash
# Самые медленные запросы
sqlite3 data/traces.db "
  SELECT question,
    ROUND((julianday(finished_at) - julianday(started_at)) * 86400, 1) AS sec,
    started_at
  FROM traces
  WHERE finished_at IS NOT NULL
    AND julianday(started_at) >= julianday('now', '-1 day')
  ORDER BY sec DESC LIMIT 10;"

# Статус Ollama
curl http://localhost:11434/api/tags
```

**Действия:**
1. Если Ollama перегружена — проверь загрузку GPU/CPU: `nvidia-smi` или `top`
2. Если нет GPU — рассмотри уменьшение `RAG_RETRIEVAL_TOP_K` (20 → 10)
3. Если проблема в reranking — попробуй `RAG_RERANK_TOP_K=3`
4. При хронической перегрузке — масштабируй Ollama на отдельный хост

---

### thumbs_down_rate > 20% (7d, n >= 50)

**Что значит:** пользователи ставят дизлайки более чем каждому пятому ответу.

**Диагностика:**
```bash
curl http://localhost:8000/api/feedback/stats
```

```bash
sqlite3 data/traces.db "
  SELECT t.question, t.final_quality, f.reason
  FROM feedback f
  JOIN traces t ON f.trace_id = t.trace_id
  WHERE f.rating = 'down'
    AND julianday(f.ts) >= julianday('now', '-7 day')
  ORDER BY f.ts DESC LIMIT 20;"
```

**Действия:**
1. Изучи причины (`reason`) — пользователи часто пишут что не так
2. Если ответы технически верны, но пользователи недовольны — проблема в формате/тоне
3. Если ответы неверны — обнови базу знаний

---

## Перезапуск сервиса

```bash
# Docker
docker compose restart app

# Напрямую
pkill -f "python main.py"
python main.py &

# Проверить что поднялся
curl http://localhost:8000/api/health
```

## Сброс состояния алертов (hysteresis)

```bash
# Сбросить все счётчики
echo '{}' > data/alerts_state.json
```
```

---

## CONSTRAINTS
- Создать только `docs/runbook.md`
- Не изменять никакие другие файлы
- Все команды должны работать с существующей структурой проекта
- `pytest tests/ -v` — проходит (runbook ничего не ломает)

## DONE WHEN
- [ ] `docs/runbook.md` создан
- [ ] Охватывает все 5 алертов из `check_alerts.py`
- [ ] Для каждого алерта: SQL-диагностика + конкретные действия
- [ ] `pytest tests/ -v` — все тесты зелёные
