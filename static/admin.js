(function () {
  "use strict";

  var legacyStorageKey = "rag_admin_token";
  var tokenInput = document.getElementById("token");
  var tokenStatus = document.getElementById("token-status");
  var tracesTableBody = document.querySelector("#traces-table tbody");
  var auditTableBody = document.querySelector("#audit-table tbody");

  // Graceful migration: purge any bearer token left in localStorage by an
  // earlier build. Auth now rides on an httpOnly cookie (set via /api/auth/session)
  // that JavaScript cannot read, so the XSS-theft surface is gone.
  try {
    localStorage.removeItem(legacyStorageKey);
  } catch (_) {
    /* localStorage may be unavailable; nothing to migrate. */
  }

  function buildHeaders() {
    // No Authorization header: requests authenticate via the httpOnly cookie,
    // copied into the Authorization header server-side by the cookie bridge.
    return { "Content-Type": "application/json" };
  }

  async function establishSession(token) {
    var response = await fetch("/api/auth/session", {
      method: "POST",
      headers: token ? { Authorization: "Bearer " + token } : {}
    });
    return response.ok;
  }

  async function api(method, path, body) {
    var options = {
      method: method,
      headers: buildHeaders()
    };

    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }

    var response = await fetch(path, options);
    var text = await response.text();
    var parsed = text;

    try {
      parsed = JSON.parse(text);
    } catch (_) {
      parsed = text;
    }

    return {
      ok: response.ok,
      status: response.status,
      body: parsed
    };
  }

  document.getElementById("save-token").addEventListener("click", async function () {
    var token = tokenInput.value.trim();
    if (!token) {
      tokenStatus.textContent = "Enter a bearer token first.";
      return;
    }
    tokenStatus.textContent = "Establishing session...";
    var ok = await establishSession(token);
    if (ok) {
      tokenInput.value = "";
      tokenStatus.textContent = "Session cookie set (httpOnly). Token is no longer stored in the browser.";
    } else {
      tokenStatus.textContent = "Authorization failed. Check the token and try again.";
    }
  });

  document.querySelectorAll(".tabs button").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll(".tabs button").forEach(function (item) {
        item.classList.remove("active");
      });
      document.querySelectorAll("main section").forEach(function (section) {
        section.classList.remove("active");
      });
      button.classList.add("active");
      document.getElementById("tab-" + button.dataset.tab).classList.add("active");
      if (button.dataset.tab === "metrics") {
        refreshMetrics();
      }
    });
  });

  document.getElementById("btn-reset").addEventListener("click", async function () {
    var output = document.getElementById("breaker-output");
    var result;

    output.textContent = "Loading...";
    result = await api("POST", "/api/admin/circuit-breaker/reset");
    output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
  });

  document.getElementById("btn-load-traces").addEventListener("click", async function () {
    var limit = document.getElementById("traces-limit").value;
    var output = document.getElementById("traces-output");
    var detail = document.getElementById("trace-detail");
    var result = await api("GET", "/api/admin/traces?limit=" + encodeURIComponent(limit));

    tracesTableBody.innerHTML = "";
    detail.textContent = "";

    if (!result.ok || !result.body || !Array.isArray(result.body.traces)) {
      output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
      return;
    }

    output.textContent = JSON.stringify({ status: result.status, count: result.body.traces.length }, null, 2);

    result.body.traces.forEach(function (trace) {
      var row = document.createElement("tr");
      var traceIdCell = document.createElement("td");
      var startedCell = document.createElement("td");
      var finishedCell = document.createElement("td");
      var actionCell = document.createElement("td");
      var detailsButton = document.createElement("button");

      traceIdCell.textContent = trace.trace_id || "";
      startedCell.textContent = trace.started_at || "";
      finishedCell.textContent = trace.finished_at || "";

      detailsButton.type = "button";
      detailsButton.textContent = "Details";
      detailsButton.addEventListener("click", async function () {
        var detailResult = await api("GET", "/api/admin/traces/" + encodeURIComponent(trace.trace_id || ""));
        detail.textContent = JSON.stringify({ status: detailResult.status, body: detailResult.body }, null, 2);
      });

      actionCell.appendChild(detailsButton);
      row.appendChild(traceIdCell);
      row.appendChild(startedCell);
      row.appendChild(finishedCell);
      row.appendChild(actionCell);
      tracesTableBody.appendChild(row);
    });
  });

  document.getElementById("btn-purge-traces").addEventListener("click", async function () {
    var days = document.getElementById("traces-purge-days").value;
    var output = document.getElementById("traces-output");
    var result = await api("DELETE", "/api/admin/traces?older_than_days=" + encodeURIComponent(days));

    output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
    if (result.ok) {
      document.getElementById("btn-load-traces").click();
    }
  });

  document.getElementById("btn-load-audit").addEventListener("click", async function () {
    var params = new URLSearchParams();
    var actor = document.getElementById("audit-actor").value;
    var action = document.getElementById("audit-action").value;
    var limit = document.getElementById("audit-limit").value;
    var output = document.getElementById("audit-output");
    var result;

    params.set("limit", limit);
    if (actor) {
      params.set("actor", actor);
    }
    if (action) {
      params.set("action", action);
    }

    result = await api("GET", "/api/admin/audit?" + params.toString());
    auditTableBody.innerHTML = "";

    if (!result.ok || !result.body || !Array.isArray(result.body.entries)) {
      output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
      return;
    }

    output.textContent = JSON.stringify({ status: result.status, count: result.body.entries.length }, null, 2);

    result.body.entries.forEach(function (entry) {
      var row = document.createElement("tr");
      var tsCell = document.createElement("td");
      var actorCell = document.createElement("td");
      var actionCell = document.createElement("td");
      var resourceCell = document.createElement("td");
      var ipCell = document.createElement("td");

      tsCell.textContent = entry.ts || "";
      actorCell.textContent = entry.actor || "";
      actionCell.textContent = entry.action || "";
      resourceCell.textContent = entry.resource || "";
      ipCell.textContent = entry.ip_address || "";

      row.appendChild(tsCell);
      row.appendChild(actorCell);
      row.appendChild(actionCell);
      row.appendChild(resourceCell);
      row.appendChild(ipCell);
      auditTableBody.appendChild(row);
    });
  });

  document.getElementById("btn-purge-audit").addEventListener("click", async function () {
    var days = document.getElementById("audit-purge-days").value;
    var output = document.getElementById("audit-output");
    var result = await api("DELETE", "/api/admin/audit-log?older_than_days=" + encodeURIComponent(days));

    output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
    if (result.ok) {
      document.getElementById("btn-load-audit").click();
    }
  });

  async function refreshMetrics() {
    var output = document.getElementById("metrics-output");
    var result = await api("GET", "/api/metrics");

    output.textContent = JSON.stringify({ status: result.status, body: result.body }, null, 2);
  }

  setInterval(function () {
    if (document.getElementById("tab-metrics").classList.contains("active")) {
      refreshMetrics();
    }
  }, 5000);

  refreshMetrics();
})();
