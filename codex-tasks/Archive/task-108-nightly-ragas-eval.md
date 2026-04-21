# Task 108 — Nightly RAGAS eval + drift detection

## Context
RQ-2 (eval gate в CI) уже сделан — PR блокируется если golden Q&A
faithfulness/precision падают. Но это гардарил на **коде**. В production
метрики плывут из-за:
- Изменений в KB (новые/обновлённые документы)
- Drift LLM (если облачный провайдер меняет модель)
- Изменений трафика (новые типы вопросов)

Нужен **production drift alert** независимый от CI.

## Goal
Cron-job (nightly) который:
1. Сэмплирует N=50 production traces за последние 24h (из `tracing` DB)
2. Прогоняет RAGAS: context_precision, faithfulness, answer_relevance
3. Сравнивает с rolling 7-day baseline
4. Если |delta| > threshold (напр. 10%) — alert в Slack/email

## Files to change
- `scripts/nightly_eval.py` — новый script (вызывается cron/k8s CronJob)
- `evaluation/drift.py` — новый: логика сравнения с baseline + alert
- `db/models.py` — новая таблица `EvalResult` (date, metric_name, value, sample_size, drift_alert)
- `alembic/versions/005_eval_results.py` — миграция
- `deploy/helm/templates/cronjob.yaml` — k8s CronJob (0 2 * * *)
- `monitoring/alert_rules.yml` — Prometheus rule `rag_eval_drift > 0.1`
  (если prefer Prometheus vs direct Slack)
- `tests/test_nightly_eval.py` — test что скрипт работает на мок-traces

## Implementation sketch

### scripts/nightly_eval.py
```python
import asyncio, datetime as dt
from db.session import get_session
from evaluation.ragas_eval import evaluate
from evaluation.drift import detect_drift, send_alert

SAMPLE_SIZE = 50
DRIFT_THRESHOLD = 0.10  # 10%

async def main():
    since = dt.datetime.utcnow() - dt.timedelta(hours=24)
    traces = await sample_traces(since, n=SAMPLE_SIZE)
    if len(traces) < 10:
        logger.warning("Too few traces (%d), skip eval", len(traces))
        return
    results = await evaluate(traces)  # dict: metric_name → value
    await save_eval_result(results)
    for metric, value in results.items():
        baseline = await get_baseline(metric, days=7)
        drift = abs(value - baseline) / baseline if baseline else 0
        if drift > DRIFT_THRESHOLD:
            await send_alert(metric, baseline, value, drift)

if __name__ == "__main__":
    asyncio.run(main())
```

### evaluation/drift.py
Alert channels:
- Slack webhook (`ALERT_SLACK_WEBHOOK` env)
- Email via SMTP (опционально, reuse существующего SMTP config если есть)
- Prometheus gauge `rag_eval_drift_{metric}` (primary — Alertmanager сам
  routing в Slack/email/PagerDuty делает)

Гибрид: predominantly — Prometheus metric (single source of truth для
alerting). Script только **пишет** gauge, Prometheus + Alertmanager
решают когда alert'нуть.

### CronJob (deploy/helm/templates/cronjob.yaml)
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: rag-nightly-eval
spec:
  schedule: "0 2 * * *"  # 02:00 UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: eval
            image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
            command: ["python", "scripts/nightly_eval.py"]
          restartPolicy: OnFailure
```

## CONSTRAINTS
- RAGAS потребует LLM calls на eval → бюджет. Sample 50 traces ≈ 150-200
  LLM calls — допустимо раз в сутки
- Baseline rolling 7-day — первая неделя работы скрипта alert'ы
  отключены (cold start, нет baseline)
- Traces sample — **только successful**, не эскалированные (те уже
  помечены как "плохие", не нужно их evaluat'ить)
- PII в traces — уже redacted (COMP-2 done), можно слать в облачный eval
  LLM если настроен

## DONE WHEN
- [ ] `python scripts/nightly_eval.py` работает end-to-end на dev DB
- [ ] Миграция 005 (`EvalResult`) прошла
- [ ] CronJob в Helm chart, `helm template` валидный
- [ ] Prometheus gauge `rag_eval_drift` виден в `/metrics`
- [ ] Alert rule добавлен в `monitoring/alert_rules.yml`
- [ ] Test: искусственный drift → gauge > threshold → Prometheus alert
      fires (test через amtool или unit test самого alert rule)
- [ ] 240+ passed
- [ ] Commit: "Nightly RAGAS eval + drift alert via Prometheus gauge (task-108)"
