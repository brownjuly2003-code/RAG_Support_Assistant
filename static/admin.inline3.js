  (function () {
    var draftButton = document.getElementById("btn-load-kb-drafts");
    var draftList = document.getElementById("kb-drafts-list");
    var draftOutput = document.getElementById("kb-drafts-output");
    var staleButton = document.getElementById("btn-load-stale-docs");
    var staleBody = document.querySelector("#stale-docs-table tbody");
    var staleOutput = document.getElementById("stale-docs-output");

    function headers() {
      // Auth rides on the httpOnly cookie (see admin.js / cookie bridge).
      return { "Content-Type": "application/json" };
    }

    async function loadDrafts() {
      var status = document.getElementById("kb-drafts-status").value;
      var response = await fetch("/api/admin/kb-drafts?status=" + encodeURIComponent(status), {
        method: "GET",
        headers: headers()
      });
      var data = await response.json().catch(function () { return {}; });
      draftList.innerHTML = "";
      if (!response.ok || !Array.isArray(data.drafts)) {
        draftOutput.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
        return;
      }
      data.drafts.forEach(function (draft) {
        var article = document.createElement("article");
        var title = document.createElement("h3");
        var textarea = document.createElement("textarea");
        var actions = document.createElement("div");
        var saveButton = document.createElement("button");
        var publishButton = document.createElement("button");
        var rejectButton = document.createElement("button");

        article.style.marginBottom = "16px";
        article.style.padding = "16px";
        article.style.border = "1px solid #ccc";
        title.textContent = draft.topic + " [" + draft.status + "]";
        textarea.value = draft.draft_content || "";
        textarea.style.width = "100%";
        textarea.style.minHeight = "180px";
        actions.className = "controls";

        saveButton.textContent = "Save";
        saveButton.onclick = async function () {
          await fetch("/api/admin/kb-drafts/" + encodeURIComponent(draft.id), {
            method: "PATCH",
            headers: headers(),
            body: JSON.stringify({ draft_content: textarea.value })
          });
          loadDrafts();
        };

        publishButton.textContent = "Publish";
        publishButton.onclick = async function () {
          await fetch("/api/admin/kb-drafts/" + encodeURIComponent(draft.id) + "/publish", {
            method: "POST",
            headers: headers()
          });
          loadDrafts();
        };

        rejectButton.textContent = "Reject";
        rejectButton.onclick = async function () {
          await fetch("/api/admin/kb-drafts/" + encodeURIComponent(draft.id) + "/reject", {
            method: "POST",
            headers: headers()
          });
          loadDrafts();
        };

        actions.appendChild(saveButton);
        actions.appendChild(publishButton);
        actions.appendChild(rejectButton);
        article.appendChild(title);
        article.appendChild(textarea);
        article.appendChild(actions);
        draftList.appendChild(article);
      });
      draftOutput.textContent = JSON.stringify({ status: response.status, count: data.drafts.length }, null, 2);
    }

    async function loadStaleDocs() {
      var days = document.getElementById("stale-docs-days").value;
      var top = document.getElementById("stale-docs-top").value;
      var response = await fetch("/api/admin/stale-docs?days=" + encodeURIComponent(days) + "&top_cited=" + encodeURIComponent(top), {
        method: "GET",
        headers: headers()
      });
      var data = await response.json().catch(function () { return {}; });
      staleBody.innerHTML = "";
      if (!response.ok || !Array.isArray(data.documents)) {
        staleOutput.textContent = JSON.stringify({ status: response.status, body: data }, null, 2);
        return;
      }
      data.documents.forEach(function (doc) {
        var row = document.createElement("tr");
        var titleCell = document.createElement("td");
        var updatedCell = document.createElement("td");
        var citationsCell = document.createElement("td");
        var actionCell = document.createElement("td");
        var reviewButton = document.createElement("button");

        titleCell.textContent = doc.title || doc.doc_id || "";
        updatedCell.textContent = doc.last_updated || "";
        citationsCell.textContent = String(doc.citation_count || 0);
        reviewButton.textContent = "Mark reviewed";
        reviewButton.onclick = async function () {
          await fetch("/api/admin/stale-docs/" + encodeURIComponent(doc.doc_id) + "/review", {
            method: "POST",
            headers: headers()
          });
          loadStaleDocs();
        };
        actionCell.appendChild(reviewButton);
        row.appendChild(titleCell);
        row.appendChild(updatedCell);
        row.appendChild(citationsCell);
        row.appendChild(actionCell);
        staleBody.appendChild(row);
      });
      staleOutput.textContent = JSON.stringify({ status: response.status, count: data.documents.length }, null, 2);
    }

    if (draftButton) {
      draftButton.addEventListener("click", loadDrafts);
    }
    if (staleButton) {
      staleButton.addEventListener("click", loadStaleDocs);
    }
  })();
