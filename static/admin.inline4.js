  (function () {
    var storageKey = "rag_admin_token";
    var button = document.getElementById("btn-load-review-queue");
    var statusInput = document.getElementById("review-queue-status");
    var reasonInput = document.getElementById("review-queue-reason");
    var limitInput = document.getElementById("review-queue-limit");
    var tableBody = document.querySelector("#review-queue-table tbody");
    var output = document.getElementById("review-queue-output");
    var statsOutput = document.getElementById("review-queue-stats");

    function headers() {
      var token = (localStorage.getItem(storageKey) || "").trim();
      var result = { "Content-Type": "application/json" };
      if (token) {
        result.Authorization = "Bearer " + token;
      }
      return result;
    }

    async function loadStats() {
      var response = await fetch("/api/admin/review-queue/stats", {
        method: "GET",
        headers: headers()
      });
      var data = await response.json().catch(function () { return {}; });
      statsOutput.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
    }

    async function loadQueue() {
      var params = new URLSearchParams();
      var status = statusInput.value;
      var reason = reasonInput.value;
      var limit = limitInput.value;
      var response;
      var data;

      params.set("status", status || "pending");
      params.set("reason", reason || "*");
      params.set("limit", limit || "50");
      params.set("offset", "0");

      response = await fetch("/api/admin/review-queue?" + params.toString(), {
        method: "GET",
        headers: headers()
      });
      data = await response.json().catch(function () { return {}; });
      tableBody.innerHTML = "";

      if (!response.ok || !data || !Array.isArray(data.items)) {
        output.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
        return;
      }

      data.items.forEach(function (item) {
        var row = document.createElement("tr");
        var traceCell = document.createElement("td");
        var reasonCell = document.createElement("td");
        var qualityCell = document.createElement("td");
        var durationCell = document.createElement("td");
        var createdCell = document.createElement("td");
        var actionCell = document.createElement("td");
        var traceLink = document.createElement("a");
        var confirmGood = document.createElement("button");
        var confirmBad = document.createElement("button");
        var dismiss = document.createElement("button");

        traceLink.href = "#";
        traceLink.textContent = item.trace_id || "";
        traceLink.onclick = async function (event) {
          var traceResponse;
          var traceData;
          event.preventDefault();
          traceResponse = await fetch("/api/admin/traces/" + encodeURIComponent(item.trace_id || ""), {
            method: "GET",
            headers: headers()
          });
          traceData = await traceResponse.json().catch(function () { return {}; });
          output.textContent = JSON.stringify({ status: traceResponse.status, body: traceData }, null, 2);
        };
        traceCell.appendChild(traceLink);

        reasonCell.textContent = item.reason || "";
        qualityCell.textContent = item.quality == null ? "" : String(item.quality);
        durationCell.textContent = item.duration_ms == null ? "" : String(item.duration_ms);
        createdCell.textContent = item.created_at || "";

        confirmGood.type = "button";
        confirmGood.textContent = "Confirm good";
        confirmGood.onclick = async function () {
          var notes = window.prompt("Reviewer notes", item.reviewer_notes || "") || "";
          await fetch("/api/admin/review-queue/" + encodeURIComponent(String(item.id)), {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ status: "confirmed_good", reviewer_notes: notes })
          });
          loadStats();
          loadQueue();
        };

        confirmBad.type = "button";
        confirmBad.textContent = "Confirm bad";
        confirmBad.onclick = async function () {
          var notes = window.prompt("Reviewer notes", item.reviewer_notes || "") || "";
          await fetch("/api/admin/review-queue/" + encodeURIComponent(String(item.id)), {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ status: "confirmed_bad", reviewer_notes: notes })
          });
          loadStats();
          loadQueue();
        };

        dismiss.type = "button";
        dismiss.textContent = "Dismiss";
        dismiss.onclick = async function () {
          var notes = window.prompt("Dismiss reason", item.reviewer_notes || "") || "";
          await fetch("/api/admin/review-queue/" + encodeURIComponent(String(item.id)), {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ status: "dismissed", reviewer_notes: notes })
          });
          loadStats();
          loadQueue();
        };

        actionCell.appendChild(confirmGood);
        actionCell.appendChild(confirmBad);
        actionCell.appendChild(dismiss);

        row.appendChild(traceCell);
        row.appendChild(reasonCell);
        row.appendChild(qualityCell);
        row.appendChild(durationCell);
        row.appendChild(createdCell);
        row.appendChild(actionCell);
        tableBody.appendChild(row);
      });

      output.textContent = JSON.stringify({ status: response.status, count: data.items.length }, null, 2);
    }

    if (button) {
      button.addEventListener("click", function () {
        loadStats();
        loadQueue();
      });
    }
  })();
