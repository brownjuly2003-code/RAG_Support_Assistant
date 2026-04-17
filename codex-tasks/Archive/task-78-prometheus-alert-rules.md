# Task 78 — OBSERVABILITY: Prometheus alert rules as code

## Goal
За task-72..76 мы накопили набор метрик:
`rag_component_up`, `rag_circuit_breaker_state`,
`rag_circuit_breaker_transitions_total`, `rag_ollama_retry_events_total`,
`rag_requests_total`, `rag_request_duration_seconds`, `rag_quality_score`,
`rag_escalation_total`, `rag_feedback_total`, `rag_active_sessions`,
`rag_vector_store_documents`.

Но **ни одного alert rule в репо не лежит** — каждый, кто деплоит проект,
пишет alertmanager-правила с нуля. Это значит:
- Одни команды задеплоят без алертов вообще.
- Другие напишут правила с неправильными порогами («breaker open > 1min»
  = паника при любом reset_timeout).
- Мы потеряли возможность эволюционировать alert-пороги вместе с кодом
  (правила лежат в отдельной инфре, не ревьюятся вместе с PR).

Упаковать alert rules в `monitoring/alert_rules.yml` + простой тест, который
парсит YAML и валидирует структуру. Файл будет подключаться в Prometheus
через `rule_files:` либо в Alertmanager напрямую (стандарт Prom
https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

## Files to create
- `monitoring/alert_rules.yml` — группы алертов
- `tests/test_alert_rules.py` — 4 теста: YAML валиден, все алерты имеют
  обязательные поля, expressions ссылаются на существующие метрики,
  `for` и severity корректны

## Files to change
- `README.md` — одна строка про `monitoring/alert_rules.yml`

---

## 1. `monitoring/alert_rules.yml`

Группы (в порядке критичности):

```yaml
groups:
  - name: rag-resilience
    interval: 30s
    rules:
      - alert: CircuitBreakerOpen
        expr: rag_circuit_breaker_state == 2
        for: 5m
        labels:
          severity: warning
          component: ollama
        annotations:
          summary: "Circuit breaker '{{ $labels.name }}' OPEN for 5m+"
          description: |
            Breaker has been OPEN for over 5 minutes, meaning Ollama has been
            failing repeatedly. Automatic HALF_OPEN probes have not recovered.
            Check Ollama logs and consider manual reset via
            POST /api/admin/circuit-breaker/reset once upstream is healthy.
          runbook_url: "internal://runbooks/ollama-down"

      - alert: HighRetryExhaustion
        expr: |
          rate(rag_ollama_retry_events_total{event="exhausted"}[5m])
          / ignoring(event) rate(rag_ollama_retry_events_total{event="attempt"}[5m])
          > 0.1
        for: 10m
        labels:
          severity: warning
          component: ollama
        annotations:
          summary: "Retry exhaustion >10% over 10min"
          description: |
            More than 10% of Ollama retry chains are exhausting all attempts.
            Upstream is unstable — breaker may be about to open. Check network
            latency to Ollama and model cold-start times.

      - alert: HighRetryRecoveryRate
        expr: |
          rate(rag_ollama_retry_events_total{event="retry"}[5m])
          / ignoring(event) rate(rag_ollama_retry_events_total{event="attempt"}[5m])
          > 0.3
        for: 15m
        labels:
          severity: info
          component: ollama
        annotations:
          summary: "Ollama flapping: >30% requests need retry"
          description: |
            Requests succeed but only after retries — p95 latency will be
            elevated. Consider investigating Ollama stability.

  - name: rag-health
    interval: 30s
    rules:
      - alert: ComponentDown
        expr: rag_component_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Component {{ $labels.component }} is DOWN"
          description: |
            Health probe for {{ $labels.component }} has been failing for 2+
            minutes. Check /api/health for details and component-specific
            logs.

      - alert: ComponentDegradedOften
        expr: |
          avg_over_time(rag_component_up[1h]) < 0.95
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Component {{ $labels.component }} uptime <95% over last 1h"
          description: |
            {{ $labels.component }} is flapping (uptime 95-99% over 1h).
            Not fully down but unstable — investigate.

  - name: rag-quality
    interval: 1m
    rules:
      - alert: HighEscalationRate
        expr: |
          sum(rate(rag_escalation_total[15m]))
          / sum(rate(rag_requests_total[15m]))
          > 0.35
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Escalation rate >35% over 15min"
          description: |
            More than 35% of requests are being routed to human. Either
            knowledge base is insufficient, or LLM quality has dropped.
            Check quality_score trend and recent document ingestions.

      - alert: LowQualityScoreAvg
        expr: |
          avg_over_time(rag_quality_score_sum[7d])
          / avg_over_time(rag_quality_score_count[7d])
          < 65
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Average answer quality <65 over 7d"
          description: |
            7-day average quality score has dropped below 65. Investigate
            prompt changes, model changes, or knowledge-base drift.

      - alert: ThumbsDownSpike
        expr: |
          rate(rag_feedback_total{rating="down"}[1h])
          / rate(rag_feedback_total[1h])
          > 0.2
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: ">20% negative feedback over 30min"

  - name: rag-latency
    interval: 30s
    rules:
      - alert: HighP95Latency
        expr: |
          histogram_quantile(0.95,
            sum(rate(rag_request_duration_seconds_bucket[5m])) by (le)
          ) > 12
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency >12s over 10min"
          description: |
            95th percentile request duration has exceeded 12 seconds for 10+
            minutes. Check Ollama CPU/GPU load, concurrent request count,
            and retry metrics (retries inflate latency).
```

**Замечания:**
- Все пороги должны соответствовать дефолтам из `.env.example` и
  `ALERT_*` переменным в `Settings` (например, `ALERT_ESCALATION_PCT=35`
  → `HighEscalationRate: > 0.35`). Если дефолты разъехались — ориентируемся
  на `.env.example`, синхронизируем.
- `expr` проверяется тестом на корректность имён метрик (grep по
  `monitoring/prometheus.py`).
- `for:` защищает от мгновенных всплесков. Короче 2 минут — только для
  критических.
- `runbook_url` — опциональное поле. Можно удалить, если runbook'и не
  ведутся отдельно.

---

## 2. `tests/test_alert_rules.py`

```python
"""Validate monitoring/alert_rules.yml structure and metric references."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)


ALERT_RULES_FILE = Path(__file__).resolve().parent.parent / "monitoring" / "alert_rules.yml"


@pytest.fixture(scope="module")
def rules_doc() -> dict:
    assert ALERT_RULES_FILE.exists(), f"missing {ALERT_RULES_FILE}"
    with ALERT_RULES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_yaml_is_valid_and_has_groups(rules_doc: dict) -> None:
    assert "groups" in rules_doc
    assert isinstance(rules_doc["groups"], list)
    assert len(rules_doc["groups"]) >= 3  # resilience, health, quality, latency


def test_every_alert_has_required_fields(rules_doc: dict) -> None:
    for group in rules_doc["groups"]:
        assert "name" in group
        assert "rules" in group
        for rule in group["rules"]:
            # Allow recording rules; skip if no alert field
            if "alert" not in rule:
                continue
            assert "expr" in rule, f"{rule['alert']} missing expr"
            assert "for" in rule, f"{rule['alert']} missing for"
            assert "labels" in rule, f"{rule['alert']} missing labels"
            assert "severity" in rule["labels"], f"{rule['alert']} missing severity"
            assert rule["labels"]["severity"] in ("info", "warning", "critical")
            assert "annotations" in rule, f"{rule['alert']} missing annotations"
            assert "summary" in rule["annotations"], f"{rule['alert']} missing summary"


def test_expressions_reference_declared_metrics(rules_doc: dict) -> None:
    """Each rag_* metric in expr must be declared in monitoring/prometheus.py."""
    prom_file = ALERT_RULES_FILE.parent / "prometheus.py"
    prom_source = prom_file.read_text(encoding="utf-8")

    # Metrics declared as Prom names (string literals "rag_*")
    declared = set(re.findall(r'"(rag_[a-z_]+)"', prom_source))
    # Alembic pedantry: Counter "rag_ollama_retry_events_total" in source
    # becomes "rag_ollama_retry_events_total" as-is — no _bucket/_sum/_count
    # suffix. Histograms autogenerate _bucket/_sum/_count; Summaries autogenerate
    # _sum/_count. Accept these suffixes when matching.
    suffix_variants = {"", "_bucket", "_sum", "_count", "_total"}

    referenced = set(re.findall(r"\brag_[a-z_]+\b", _flatten_exprs(rules_doc)))

    missing: list[str] = []
    for name in referenced:
        # strip a known suffix if present, then check base existence
        found = False
        for suf in sorted(suffix_variants, key=len, reverse=True):
            if suf and name.endswith(suf):
                base = name[: -len(suf)]
                if base in declared or name in declared:
                    found = True
                    break
        if not found and name not in declared:
            # final chance: exact match
            if name not in declared:
                missing.append(name)

    assert not missing, f"Undeclared metrics in alert_rules.yml: {missing}"


def test_for_durations_are_reasonable(rules_doc: dict) -> None:
    """`for: 0s` or missing → false positives; `for: >1h` → alert fatigue."""
    for group in rules_doc["groups"]:
        for rule in group["rules"]:
            if "alert" not in rule:
                continue
            dur = rule.get("for", "0s")
            assert dur.endswith(("s", "m", "h"))
            # super-rough sanity: between 30s and 2h
            num = int(dur[:-1])
            unit = dur[-1]
            sec = {"s": 1, "m": 60, "h": 3600}[unit]
            total_sec = num * sec
            assert 30 <= total_sec <= 7200, (
                f"{rule['alert']} has unreasonable for={dur}"
            )


def _flatten_exprs(rules_doc: dict) -> str:
    """Concat all `expr:` strings for regex scanning."""
    out: list[str] = []
    for group in rules_doc["groups"]:
        for rule in group["rules"]:
            expr = rule.get("expr", "")
            if isinstance(expr, str):
                out.append(expr)
    return "\n".join(out)
```

---

## 3. `README.md`

В раздел Monitoring добавить одну строку перед описанием scripts/check_alerts.py:

```
Prometheus alert rules упакованы в `monitoring/alert_rules.yml`. Подключаются
через `rule_files` в `prometheus.yml`.
```

---

## CONSTRAINTS
- Никаких новых зависимостей. `PyYAML` уже есть в `requirements.txt`
  (если нет — тест `skip`'ается, не падает).
- `pytest tests/ -v` — **117+ passed** (113 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Все `expr:` должны ссылаться на метрики, реально экспортируемые в
  `monitoring/prometheus.py` (тест это проверяет).
- Пороги в alert-правилах должны соответствовать дефолтам из
  `config/settings.py` (`ALERT_*` переменные) — если расходятся,
  синхронизировать.

## DONE WHEN
- [ ] `monitoring/alert_rules.yml` существует, валидный YAML, ≥3 групп
- [ ] Все алерты имеют `expr`, `for`, `labels.severity`, `annotations.summary`
- [ ] Все `rag_*` метрики в `expr` объявлены в `monitoring/prometheus.py`
- [ ] `for:` везде в диапазоне 30s..2h
- [ ] README упоминает `alert_rules.yml`
- [ ] `tests/test_alert_rules.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 117+ passed
- [ ] `ruff check .` — 0 errors
