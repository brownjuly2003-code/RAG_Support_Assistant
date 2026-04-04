# scripts/

## check_alerts.py

Проверяет метрики из SQLite против порогов. Запускай каждые 5 минут через cron или scheduler.

### Запуск вручную

```bash
python scripts/check_alerts.py
python scripts/check_alerts.py --dry-run
```

### Cron

```cron
*/5 * * * * cd /path/to/rag-support-assistant && python scripts/check_alerts.py >> data/alerts.log 2>&1
```

### Настройка в `.env`

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `ALERT_WEBHOOK_URL` | пусто | Slack/Telegram incoming webhook |
| `ALERT_ESCALATION_PCT` | `35` | % эскалаций за 24 часа |
| `ALERT_QUALITY_MIN` | `65` | минимальный avg quality за 7 дней |
| `ALERT_LOW_QUALITY_PCT` | `30` | % ответов с quality < 60 за 7 дней |
| `ALERT_P95_LATENCY_SEC` | `12` | p95 latency за 24 часа |
| `ALERT_THUMBS_DOWN_PCT` | `20` | % thumbs-down за 7 дней |
| `ALERT_THUMBS_DOWN_MIN_N` | `50` | минимум feedback для thumbs-down alert |

Состояние hysteresis хранится в `data/alerts_state.json`.
Лог алертов пишется в `data/alerts.log`.
