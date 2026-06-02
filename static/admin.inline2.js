  (function () {
    var storageKey = "rag_admin_token";
    var button = document.getElementById("btn-load-kb-gaps");
    var output = document.getElementById("kb-gaps-output");
    var tableBody = document.querySelector("#kb-gaps-table tbody");

    function buildHeaders() {
      var token = (localStorage.getItem(storageKey) || "").trim();
      var headers = { "Content-Type": "application/json" };
      if (token) {
        headers.Authorization = "Bearer " + token;
      }
      return headers;
    }

    async function loadKbGaps() {
      var response = await fetch("/api/admin/kb-gaps", {
        method: "GET",
        headers: buildHeaders()
      });
      var data = await response.json().catch(function () { return {}; });

      tableBody.innerHTML = "";
      if (!response.ok || !data || !Array.isArray(data.gaps)) {
        output.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
        return;
      }

      data.gaps.forEach(function (gap) {
        var row = document.createElement("tr");
        var topicCell = document.createElement("td");
        var countCell = document.createElement("td");
        var examplesCell = document.createElement("td");

        topicCell.textContent = gap.topic_summary || "";
        countCell.textContent = String(gap.question_count || 0);
        examplesCell.textContent = Array.isArray(gap.sample_questions)
          ? gap.sample_questions.join(" | ")
          : "";

        row.appendChild(topicCell);
        row.appendChild(countCell);
        row.appendChild(examplesCell);
        tableBody.appendChild(row);
      });

      output.textContent = JSON.stringify({ status: response.status, count: data.gaps.length }, null, 2);
    }

    if (button) {
      button.addEventListener("click", loadKbGaps);
    }
  })();
