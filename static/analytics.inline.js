  (function () {
    // Graceful migration: drop any legacy bearer token from localStorage. This
    // read-only dashboard now authenticates via the httpOnly cookie established
    // on the admin page (same-origin requests send it automatically; the cookie
    // bridge copies it into the Authorization header server-side).
    try {
      localStorage.removeItem("rag_admin_token");
    } catch (_) {
      /* localStorage may be unavailable; nothing to migrate. */
    }

    async function loadJson(path) {
      var response = await fetch(path);
      return response.json();
    }

    function barChart(id, labels, values, label, horizontal) {
      return new Chart(document.getElementById(id), {
        type: "bar",
        data: {
          labels: labels,
          datasets: [{
            label: label,
            data: values,
            backgroundColor: ["#b5651d", "#d69f56", "#7d4e24", "#3f6f5a", "#8a7d5b"]
          }]
        },
        options: {
          indexAxis: horizontal ? "y" : "x",
          responsive: true,
          maintainAspectRatio: false
        }
      });
    }

    function lineChart(id, labels, values, label) {
      return new Chart(document.getElementById(id), {
        type: "line",
        data: {
          labels: labels,
          datasets: [{
            label: label,
            data: values,
            borderColor: "#3f6f5a",
            backgroundColor: "rgba(63, 111, 90, 0.18)",
            fill: true,
            tension: 0.3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false
        }
      });
    }

    Promise.all([
      loadJson("/api/analytics/top-topics?days=7"),
      loadJson("/api/analytics/resolution-rate?days=7"),
      loadJson("/api/analytics/cost-summary?days=7"),
      loadJson("/api/analytics/trends?days=30&metric=quality")
    ]).then(function (results) {
      var topics = results[0].topics || [];
      var resolution = results[1].topics || [];
      var cost = results[2];
      var trend = results[3].points || [];
      var costSummary = cost.summary || {};
      var costLabel = document.getElementById("cost-label");
      var costBreakdown = document.getElementById("cost-breakdown");

      barChart("topics-chart", topics.map(function (item) { return item.category; }), topics.map(function (item) { return item.count; }), "Questions", false);
      barChart("resolution-chart", resolution.map(function (item) { return item.category; }), resolution.map(function (item) { return Math.round((item.resolution_rate || 0) * 100); }), "Resolution %", true);
      barChart("cost-chart", (cost.per_category || []).map(function (item) { return item.category; }), (cost.per_category || []).map(function (item) { return item.cost_usd; }), "Cost USD", false);
      lineChart("trend-chart", trend.map(function (item) { return item.date; }), trend.map(function (item) { return item.value; }), "Quality");
      if (costSummary.free_tier) {
        costLabel.textContent = "Free tier";
        costLabel.title = costSummary.tooltip || "";
      } else {
        costLabel.textContent = costSummary.label || "";
        costLabel.title = "";
      }
      costBreakdown.textContent = (cost.per_model || []).map(function (item) {
        return item.model_name + " " + "$" + (item.cost_usd || 0).toFixed(2);
      }).join(" · ");
    });
  })();
