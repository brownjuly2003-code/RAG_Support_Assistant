# Task 94 — ADMIN UI: статическая страница поверх admin endpoint'ов

## Goal
task-74/84/85/90 добавили 7 admin endpoint'ов:
- POST /api/admin/circuit-breaker/reset
- DELETE /api/admin/traces?older_than_days=N
- DELETE /api/admin/audit-log?older_than_days=N
- GET /api/admin/audit
- GET /api/admin/traces
- GET /api/admin/traces/{id}
- (+ task-81/82/83/86 метрики через /api/metrics)

Пользоваться ими сейчас можно только через `curl` или Postman. Operator
поддержки не будет админить из терминала. Нужна минимальная **статическая**
страница — без SPA-фреймворков, одна HTML + один JS + немного CSS.

**Ключевая особенность задачи:** работа **только в `static/`**. Ноль
пересечений с backend — идеальный кандидат для параллельного исполнения
с любой другой задачей.

## Files to change
- `api/app.py` — 1 строка (если login-gate нужен): serve `/admin`
  возможно, но чаще `static/admin.html` уже автоматически доступен
  через существующий `StaticFiles` mount. Проверить и только при
  необходимости.

## Files to create
- `static/admin.html` — 4 tab'а: Breaker, Traces, Audit, Metrics
- `static/admin.js` — fetch-обёртки + отрисовка
- `static/admin.css` — стили (минимальные, не overdesign)
- `tests/test_admin_ui.py` — 2 теста (страница отдаётся, auth проверка)

---

## 1. `static/admin.html`

Одностраничник, табы через `<details>` или простые buttons+div-переключение.
UI должен быть **очень тихим** — дефолт: белый фон, моноширинный текст для
JSON, без анимаций, без эмодзи (user preferences из памяти).

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RAG Admin</title>
<link rel="stylesheet" href="/static/admin.css">
</head>
<body>
<header>
  <h1>RAG Support Assistant — Admin</h1>
  <div class="auth">
    <label>Bearer Token: <input id="token" type="password" autocomplete="off"></label>
    <button id="save-token">Save</button>
  </div>
</header>

<nav class="tabs">
  <button data-tab="breaker" class="active">Circuit Breaker</button>
  <button data-tab="traces">Traces</button>
  <button data-tab="audit">Audit Log</button>
  <button data-tab="metrics">Metrics</button>
</nav>

<main>
  <section id="tab-breaker" class="active">
    <h2>Circuit Breaker</h2>
    <button id="btn-reset">Reset Breaker</button>
    <pre id="breaker-output"></pre>
  </section>

  <section id="tab-traces">
    <h2>Recent Traces</h2>
    <label>Limit: <input id="traces-limit" type="number" value="50" min="1" max="500"></label>
    <button id="btn-load-traces">Load</button>
    <table id="traces-table"><thead><tr><th>trace_id</th><th>started</th><th>finished</th><th></th></tr></thead><tbody></tbody></table>
    <pre id="trace-detail"></pre>
  </section>

  <section id="tab-audit">
    <h2>Audit Log</h2>
    <label>Actor: <input id="audit-actor"></label>
    <label>Action: <input id="audit-action"></label>
    <label>Limit: <input id="audit-limit" type="number" value="50" min="1" max="500"></label>
    <button id="btn-load-audit">Load</button>
    <table id="audit-table"><thead><tr><th>ts</th><th>actor</th><th>action</th><th>resource</th><th>ip</th></tr></thead><tbody></tbody></table>
  </section>

  <section id="tab-metrics">
    <h2>Live Metrics (scrape every 5s)</h2>
    <pre id="metrics-output"></pre>
  </section>
</main>

<script src="/static/admin.js"></script>
</body>
</html>
```

---

## 2. `static/admin.css`

Минимальный, calm. Белый фон, серый текст, моноширинный для технических
данных. Никаких градиентов/shadow'ов за пределами таблиц.

```css
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  margin: 0;
  padding: 0;
  color: #1a1a1a;
  background: #fff;
}
header {
  padding: 16px 24px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
header h1 { margin: 0; font-size: 18px; font-weight: 500; }
.auth input { font-family: ui-monospace, monospace; padding: 4px 8px; width: 260px; }
.tabs {
  display: flex;
  gap: 4px;
  padding: 8px 24px;
  border-bottom: 1px solid #e0e0e0;
}
.tabs button {
  padding: 8px 16px;
  background: none;
  border: none;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  font-size: 14px;
}
.tabs button.active { border-bottom-color: #1a1a1a; font-weight: 500; }
main { padding: 24px; }
main section { display: none; }
main section.active { display: block; }
h2 { margin-top: 0; font-size: 16px; font-weight: 500; }
label { display: inline-block; margin-right: 12px; font-size: 13px; }
input, button { font-size: 13px; padding: 6px 10px; border: 1px solid #d0d0d0; background: #fff; }
button { cursor: pointer; }
button:hover { background: #f5f5f5; }
pre {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  padding: 12px;
  overflow: auto;
  max-height: 500px;
}
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
th { font-weight: 500; color: #666; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
tr:hover td { background: #fafafa; }
```

---

## 3. `static/admin.js`

```javascript
(function() {
  "use strict";

  const token = () => localStorage.getItem("rag_admin_token") || "";

  function headers() {
    const t = token();
    return t ? { "Authorization": "Bearer " + t, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
  }

  async function api(method, path, body) {
    const opts = { method, headers: headers() };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(path, opts);
    const text = await resp.text();
    try { return { status: resp.status, body: JSON.parse(text) }; }
    catch { return { status: resp.status, body: text }; }
  }

  // --- Auth ---
  document.getElementById("save-token").onclick = () => {
    localStorage.setItem("rag_admin_token", document.getElementById("token").value);
    alert("Token saved.");
  };
  document.getElementById("token").value = token();

  // --- Tabs ---
  document.querySelectorAll(".tabs button").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".tabs button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll("main section").forEach(s => s.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    };
  });

  // --- Breaker ---
  document.getElementById("btn-reset").onclick = async () => {
    const out = document.getElementById("breaker-output");
    out.textContent = "...";
    const r = await api("POST", "/api/admin/circuit-breaker/reset");
    out.textContent = JSON.stringify(r.body, null, 2);
  };

  // --- Traces ---
  document.getElementById("btn-load-traces").onclick = async () => {
    const limit = document.getElementById("traces-limit").value;
    const r = await api("GET", "/api/admin/traces?limit=" + encodeURIComponent(limit));
    const tbody = document.querySelector("#traces-table tbody");
    tbody.innerHTML = "";
    (r.body.traces || []).forEach(t => {
      const row = document.createElement("tr");
      row.innerHTML =
        "<td>" + t.trace_id + "</td><td>" + (t.started_at || "") + "</td><td>" +
        (t.finished_at || "") + "</td><td><button data-tid='" + t.trace_id + "'>details</button></td>";
      tbody.appendChild(row);
    });
    tbody.querySelectorAll("button").forEach(b => {
      b.onclick = async () => {
        const detail = await api("GET", "/api/admin/traces/" + encodeURIComponent(b.dataset.tid));
        document.getElementById("trace-detail").textContent = JSON.stringify(detail.body, null, 2);
      };
    });
  };

  // --- Audit ---
  document.getElementById("btn-load-audit").onclick = async () => {
    const params = new URLSearchParams();
    params.set("limit", document.getElementById("audit-limit").value);
    const actor = document.getElementById("audit-actor").value;
    const action = document.getElementById("audit-action").value;
    if (actor) params.set("actor", actor);
    if (action) params.set("action", action);
    const r = await api("GET", "/api/admin/audit?" + params.toString());
    const tbody = document.querySelector("#audit-table tbody");
    tbody.innerHTML = "";
    (r.body.entries || []).forEach(e => {
      const row = document.createElement("tr");
      row.innerHTML =
        "<td>" + (e.ts || "") + "</td><td>" + e.actor + "</td><td>" + e.action +
        "</td><td>" + e.resource + "</td><td>" + (e.ip_address || "") + "</td>";
      tbody.appendChild(row);
    });
  };

  // --- Metrics ---
  async function refreshMetrics() {
    try {
      const r = await fetch("/api/metrics", { headers: headers() });
      const text = await r.text();
      document.getElementById("metrics-output").textContent = text;
    } catch (e) {
      document.getElementById("metrics-output").textContent = "Failed to load metrics: " + e;
    }
  }
  setInterval(() => {
    if (document.getElementById("tab-metrics").classList.contains("active")) refreshMetrics();
  }, 5000);
  refreshMetrics();
})();
```

---

## 4. `tests/test_admin_ui.py`

Минимальные тесты: страница отдаётся, JS/CSS тоже.

```python
"""Тесты отдачи admin UI статики."""
from fastapi.testclient import TestClient


def test_admin_html_served(client: TestClient) -> None:
    resp = client.get("/static/admin.html")
    assert resp.status_code == 200
    assert "RAG Support Assistant" in resp.text
    assert "tabs" in resp.text


def test_admin_js_served(client: TestClient) -> None:
    resp = client.get("/static/admin.js")
    assert resp.status_code == 200
    assert "addEventListener" in resp.text or "onclick" in resp.text
```

---

## CONSTRAINTS
- Никаких новых зависимостей. No frameworks. Vanilla JS + HTML + CSS.
- `pytest tests/ -v` — **163+ passed** (161 + 2 новых).
- `ruff check .` — 0 errors (Python-only, HTML/JS не валидируются).
- UI — calm, white background, no shadows/gradients/emojis (user preference).
- Token хранится в `localStorage` — **не** sessionStorage, чтобы
  оператор не пере-вводил его после закрытия вкладки. Минус: XSS-атака
  может его украсть. Для admin UI приемлемо (доверенная сеть).
- Никаких SPA-фреймворков, одна HTML + один JS.
- Файлы **только в `static/`** — полная изоляция от backend.

## DONE WHEN
- [ ] `static/admin.html` — 4 таба (Breaker, Traces, Audit, Metrics)
- [ ] `static/admin.js` — fetch-обёртки, localStorage для token
- [ ] `static/admin.css` — calm, minimal стили
- [ ] `/static/admin.html` отдаётся через существующий StaticFiles mount
- [ ] 2 теста в `tests/test_admin_ui.py` проходят
- [ ] `pytest tests/ -v` — 163+ passed
- [ ] `ruff check .` — 0 errors
