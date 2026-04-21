# Task 118 — Weekly quality reports в Slack/email

## Context
AN-3 из commercial-plan. Analytics dashboard (task-117) требует чтобы
admin **зашёл** и посмотрел. Weekly digest — push-формат, не pull.
Каждый понедельник 09:00 → admin получает в Slack/email сводку прошлой
недели.

## Goal
Cron-job формирует markdown-отчёт и отправляет через существующие
alert channels (Slack webhook + SMTP).

## Files to change
- `scripts/weekly_report.py` — новый
- `reports/renderer.py` — markdown-генератор
- `config/settings.py` — `REPORT_SLACK_WEBHOOK`, `REPORT_EMAIL_RECIPIENTS`,
  `REPORT_SMTP_HOST/PORT/USER/PASS` (reuse existing если есть)
- `deploy/helm/templates/cronjob-report.yaml`
- `.github/workflows/weekly-report.yml` (альтернатива для managed deployments)
- `tests/test_weekly_report.py`

## Implementation sketch

### reports/renderer.py
```python
async def generate_report(tenant_id: str, week_start: datetime, week_end: datetime) -> str:
    analytics = await gather_analytics(tenant_id, week_start, week_end)
    prev_week = await gather_analytics(tenant_id, week_start - timedelta(days=7), week_start)

    md = f"""# RAG Support Weekly Report — {week_start:%Y-%m-%d} to {week_end:%Y-%m-%d}

**Tenant:** {tenant_id}

## Key metrics
| Metric | This week | Last week | Δ |
| --- | ---: | ---: | ---: |
| Total questions | {analytics['total_q']} | {prev_week['total_q']} | {delta_pct(analytics['total_q'], prev_week['total_q'])} |
| Resolution rate | {analytics['resolution_rate']:.1%} | {prev_week['resolution_rate']:.1%} | {delta_pp(analytics['resolution_rate'], prev_week['resolution_rate'])} |
| Avg quality score | {analytics['avg_quality']:.2f} | {prev_week['avg_quality']:.2f} | ... |
| Total cost | ${analytics['total_cost']:.2f} | ... | ... |

## Top 5 topics
{render_topics_table(analytics['top_topics'])}

## Knowledge gaps (new this week)
{render_gaps(analytics['new_gaps'])}

## Stale docs requiring review
{render_stale(analytics['stale_docs'])}

## Anomalies
{render_anomalies(analytics['anomalies'])}
"""
    return md
```

### scripts/weekly_report.py
```python
async def main():
    tenants = await get_all_active_tenants()
    for tenant in tenants:
        md = await generate_report(tenant.id, week_start, week_end)
        if tenant.slack_webhook:
            await send_slack(tenant.slack_webhook, md)
        if tenant.report_emails:
            await send_email(tenant.report_emails, f"Weekly report — {week_start}", md)

if __name__ == "__main__":
    asyncio.run(main())
```

### Email formatting
Markdown → HTML через `markdown2` library для email (Slack читает markdown
нативно).

## CONSTRAINTS
- Per-tenant: каждый tenant получает свой отчёт, не дождь одного admin'а
- Tenant может не иметь настроенный Slack/email → log "skipped, no channel
  configured"
- Attachment: опционально — прикрепить CSV с detailed trace list
- Время генерации — может быть 30-60 сек на tenant (heavy queries); job
  запускается однократно в неделю, OK
- Dedup: если reports уже отправлены за эту неделю (checkbox в
  `report_history` table) — не слать повторно при ручном rerun

## DONE WHEN
- [ ] `python scripts/weekly_report.py --tenant TEST --dry-run` печатает
      markdown в stdout
- [ ] Slack webhook получает сообщение (mocked в тесте)
- [ ] Email отправляется (mocked SMTP в тесте)
- [ ] Report содержит сравнение с прошлой неделей (deltas)
- [ ] CronJob в Helm, расписание `0 9 * * 1` (Mon 09:00)
- [ ] 280+ passed
- [ ] Commit: "Weekly quality report: Slack + email digest (task-118)"
