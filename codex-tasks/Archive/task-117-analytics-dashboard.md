# Task 117 — Analytics dashboard: topics, resolution, cost

## Context
AN-1 + AN-2 из commercial-plan. `static/metrics.html` показывает текущие
системные метрики (latency, error rate), но admin не видит **продуктовых**:
- Топ-10 тем за неделю
- Resolution rate по topics (% без эскалации)
- Cost per resolution (LLM tokens × price)
- Trends over time

## Goal
Новая страница `/static/analytics.html` для admin/agent роли с
продуктовыми аналитиками. Источники данных:
- Categories (task-116) для grouping
- Traces для LLM token usage
- EscalatedTicket для resolution status

## Files to change
- `db/models.py` — расширить `traces` или добавить `token_usage` column:
  (prompt_tokens, completion_tokens, model_name, cost_usd)
- `alembic/versions/011_trace_costs.py`
- `graph.py` — каждый LLM call записывает token counts + calculated cost
- `config/settings.py` — `LLM_COST_PER_1M_TOKENS: str = "qwen2.5:0.0,gpt-4:10.0"`
  (mapping model→price, 0 для local)
- `api/app.py` — endpoints:
  - `GET /api/analytics/top-topics?days=7` — топ категорий по кол-ву запросов
  - `GET /api/analytics/resolution-rate?days=7` — per category
  - `GET /api/analytics/cost-summary?days=7` — total + per category
  - `GET /api/analytics/trends?days=30&metric=quality` — time series
- `static/analytics.html` — новый: 4 панели с Chart.js
- `tests/test_analytics.py`

## Implementation sketch

### Cost tracking (graph.py)
```python
COST_TABLE = parse_cost_config(settings.llm_cost_per_1m_tokens)

async def _record_llm_call(state, response, model_name):
    prompt_tokens = response.usage_metadata.get("input_tokens", 0)
    completion_tokens = response.usage_metadata.get("output_tokens", 0)
    cost_per_1m = COST_TABLE.get(model_name, 0.0)
    cost_usd = (prompt_tokens + completion_tokens) * cost_per_1m / 1_000_000

    await session.execute(update(TraceStep).where(
        TraceStep.trace_id == state["trace_id"],
        TraceStep.node_name == state["current_node"],
    ).values(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        model_name=model_name,
    ))
```

### Analytics queries (api/app.py)
```python
@app.get("/api/analytics/top-topics")
async def top_topics(days: int = 7, user=Depends(require_role(["admin", "agent"]))):
    since = datetime.utcnow() - timedelta(days=days)
    # Join traces → retrieved docs → categories
    stmt = (
        select(
            func.unnest(Trace.categories).label("category"),
            func.count().label("count"),
            func.avg(Trace.quality_score).label("avg_quality"),
        )
        .where(Trace.tenant_id == user.tenant_id, Trace.created_at >= since)
        .group_by("category")
        .order_by(desc("count"))
        .limit(10)
    )
    return await session.execute(stmt).all()
```

### Frontend (analytics.html)
4 Chart.js панели:
1. Bar chart — Top-10 topics
2. Horizontal bar — Resolution rate % per category
3. Line chart — Cost per day (last 30d)
4. Area chart — Quality trend per category

## CONSTRAINTS
- Cost для local LLM (qwen2.5) = 0 → показывать "self-hosted (no cost)"
  вместо $0.00
- Категории из task-116 — зависимость. Если task-116 ещё не сделан,
  fallback на "uncategorized" для всех
- Queries могут быть тяжёлыми на больших traces — добавить индексы на
  `(tenant_id, created_at)` в миграции 011
- Все endpoints tenant-scoped

## DONE WHEN
- [ ] Миграция 011 прошла, token_usage колонки есть
- [ ] Каждый LLM call пишет tokens + cost
- [ ] 4 analytics endpoints работают, tenant-scoped
- [ ] `/static/analytics.html` рисует 4 chart'а с реальными данными
- [ ] `require_role(["admin", "agent"])` — viewer получает 403
- [ ] 275+ passed
- [ ] Commit: "Analytics dashboard: topics, resolution rate, cost tracking (task-117)"
