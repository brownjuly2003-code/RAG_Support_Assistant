# Task 30 — static/metrics.html: внутренняя страница мониторинга

## Goal
Простая HTML-страница, которая показывает снапшот метрик из `GET /api/metrics`.
Автоматически обновляется каждые 30 секунд.
Доступна по `/static/metrics.html` (уже отдаётся через StaticFiles mount).

## File to create
- `static/metrics.html`

## Также изменить
- `static/chat.html` — добавить ссылку в шапку рядом с "?" кнопкой
- `static/help.html` — добавить ссылку на metrics в секцию для операторов

---

## static/metrics.html

Использовать тот же CSS-стиль что в `static/help.html`:
- тёмная тема, те же CSS-переменные (скопировать `:root {}` блок)
- карточки-секции как в help.html (`.hero`, `section`)

Структура страницы:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Метрики — RAG Support Assistant</title>
  <style>
    /* скопируй CSS из static/help.html — те же переменные, те же card-стили */
    /* добавить: */
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
    .metric-card { background: var(--bg-bot-msg); border: 1px solid var(--border-color);
                   border-radius: 12px; padding: 16px; }
    .metric-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
    .metric-value { font-size: 28px; font-weight: 700; color: var(--accent); }
    .metric-unit  { font-size: 12px; color: var(--text-secondary); }
    .status-ok    { color: #10b981; }
    .status-warn  { color: #f59e0b; }
    .status-alert { color: #ef4444; }
    .refresh-ts   { font-size: 12px; color: var(--text-secondary); text-align: right; }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Метрики системы</h1>
      <p class="refresh-ts" id="refreshTs">Загрузка...</p>
    </div>

    <section>
      <h2>Latency (24h)</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">p50</div>
          <div class="metric-value" id="p50">—</div>
          <div class="metric-unit">сек</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">p95</div>
          <div class="metric-value" id="p95">—</div>
          <div class="metric-unit">сек / порог 12</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">p99</div>
          <div class="metric-value" id="p99">—</div>
          <div class="metric-unit">сек</div>
        </div>
      </div>
    </section>

    <section>
      <h2>Качество и маршрутизация</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Avg quality (7d)</div>
          <div class="metric-value" id="avgQuality">—</div>
          <div class="metric-unit">/ 100 · порог ≥65</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Escalation rate (24h)</div>
          <div class="metric-value" id="escalationRate">—</div>
          <div class="metric-unit">% · порог ≤35%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Thumbs-down (7d)</div>
          <div class="metric-value" id="thumbsDown">—</div>
          <div class="metric-unit">% · порог ≤20%</div>
        </div>
      </div>
    </section>

    <section>
      <h2>Ошибки</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Likely failures (24h)</div>
          <div class="metric-value" id="failureRate">—</div>
          <div class="metric-unit">%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Всего трасс (24h)</div>
          <div class="metric-value" id="totalTraces">—</div>
          <div class="metric-unit">запросов</div>
        </div>
      </div>
    </section>

    <a href="/chat" class="back-link">← Вернуться в чат</a>
  </div>

  <script>
    // Пороги (должны совпадать с R2-рисерчем и ALERT_* env)
    const THRESHOLDS = {
      p95: 12, avgQuality: 65, escalationRate: 35, thumbsDown: 20, failureRate: 5
    };

    function colorClass(value, threshold, lowerIsBetter = false) {
      if (value === null || value === undefined) return '';
      const bad = lowerIsBetter ? value < threshold : value > threshold;
      const warn = lowerIsBetter ? value < threshold * 1.1 : value > threshold * 0.8;
      return bad ? 'status-alert' : (warn ? 'status-warn' : 'status-ok');
    }

    function set(id, value, unit, cls) {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = value ?? '—';
      if (cls) el.className = 'metric-value ' + cls;
    }

    async function refresh() {
      try {
        const resp = await fetch('/api/metrics');
        if (!resp.ok) throw new Error(resp.status);
        const m = await resp.json();

        const lat = m.latency || {};
        set('p50', lat.p50_sec, 's', colorClass(lat.p50_sec, 6));
        set('p95', lat.p95_sec, 's', colorClass(lat.p95_sec, THRESHOLDS.p95));
        set('p99', lat.p99_sec, 's', colorClass(lat.p99_sec, 20));

        const q = m.quality || {};
        set('avgQuality', q.avg_quality, '', colorClass(q.avg_quality, THRESHOLDS.avgQuality, true));

        const esc = m.escalation || {};
        set('escalationRate', esc.rate_pct, '%', colorClass(esc.rate_pct, THRESHOLDS.escalationRate));
        set('totalTraces', esc.total_traces, '');

        const fb = m.feedback || {};
        set('thumbsDown', fb.thumbs_down_rate_pct, '%', colorClass(fb.thumbs_down_rate_pct, THRESHOLDS.thumbsDown));

        const err = m.errors || {};
        set('failureRate', err.likely_failure_rate_pct, '%', colorClass(err.likely_failure_rate_pct, THRESHOLDS.failureRate));

        document.getElementById('refreshTs').textContent =
          'Обновлено: ' + new Date().toLocaleTimeString('ru-RU');
      } catch (e) {
        document.getElementById('refreshTs').textContent = 'Ошибка загрузки: ' + e.message;
      }
    }

    refresh();
    setInterval(refresh, 30000);
  </script>
</body>
</html>
```

---

## static/chat.html — добавить кнопку в шапку

Рядом с кнопкой "?" (ссылка на help) добавить:
```html
<a href="/static/metrics.html" target="_blank" class="btn-icon" title="Метрики" style="text-decoration:none;font-size:12px;font-weight:700;">M</a>
```

---

## CONSTRAINTS
- Создать только `static/metrics.html`
- Изменить только `static/chat.html` (одна строка — кнопка M)
- Цвета: зелёный = OK, жёлтый = близко к порогу (80%), красный = превышение
- Автообновление каждые 30 сек через `setInterval`
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `static/metrics.html` существует
- [ ] Страница открывается по `/static/metrics.html`
- [ ] Показывает p50/p95/p99, avg_quality, escalation_rate, thumbs_down, failure_rate
- [ ] Значения окрашены: зелёный/жёлтый/красный по порогам
- [ ] В шапке chat.html есть кнопка M → открывает metrics в новой вкладке
- [ ] `pytest tests/ -v` — проходит
