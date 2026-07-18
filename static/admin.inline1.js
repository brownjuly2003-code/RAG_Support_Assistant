  (function () {
    var button = document.getElementById("btn-load-providers");
    var tableBody = document.querySelector("#providers-table tbody");
    var output = document.getElementById("providers-output");

    function headers() {
      // Auth rides on the httpOnly cookie (see admin.js / cookie bridge).
      return { "Content-Type": "application/json" };
    }

    async function loadProviders() {
      var response = await fetch("/api/admin/providers", {
        method: "GET",
        headers: headers()
      });
      var data = await response.json().catch(function () { return {}; });
      tableBody.innerHTML = "";

      if (!response.ok || !data || !Array.isArray(data.providers)) {
        output.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
        return;
      }

      data.providers.forEach(function (provider) {
        var row = document.createElement("tr");
        var providerCell = document.createElement("td");
        var kindCell = document.createElement("td");
        var activeCell = document.createElement("td");
        var configuredCell = document.createElement("td");
        var requestsCell = document.createElement("td");
        var tokensCell = document.createElement("td");
        var successCell = document.createElement("td");

        providerCell.textContent = provider.label || provider.id || "";
        kindCell.textContent = provider.kind || "";
        activeCell.textContent = data.active_profile || "";
        configuredCell.textContent = provider.configured ? "yes" : "no";
        requestsCell.textContent = String((provider.usage_1m || {}).requests || 0);
        tokensCell.textContent = String((provider.usage_1m || {}).tokens || 0);
        successCell.textContent = provider.last_success_at || "";

        row.appendChild(providerCell);
        row.appendChild(kindCell);
        row.appendChild(activeCell);
        row.appendChild(configuredCell);
        row.appendChild(requestsCell);
        row.appendChild(tokensCell);
        row.appendChild(successCell);
        tableBody.appendChild(row);
      });

      output.textContent = JSON.stringify({
        status: response.status,
        active_profile: data.active_profile,
        default_profile: data.default_profile,
        providers: data.providers.length
      }, null, 2);
    }

    if (button) {
      button.addEventListener("click", loadProviders);
    }
  })();
