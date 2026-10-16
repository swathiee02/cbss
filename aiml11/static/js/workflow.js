document.addEventListener("DOMContentLoaded", function () {

    // Clean stale query params from URL
    if (window.location.search) {
        window.history.replaceState(null, '', window.location.pathname);
    }

    // Browser back arrow → admin portal
    history.pushState(null, '', window.location.href);
    window.addEventListener("popstate", function () {
        window.location.href = '/aiml11/admin_portal';
    });

    // Populate username
    const userDataEl = document.getElementById("user-data");
    if (userDataEl) {
        const userData = JSON.parse(userDataEl.getAttribute("data-json"));
        const usernameEl = document.getElementById("username");
        if (usernameEl) usernameEl.textContent = userData.name;
    }

    // Logout
    const logoutBtn = document.getElementById("logout");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            const logoutUrl = this.getAttribute("data-url");
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
            fetch(logoutUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
                credentials: "same-origin",
            }).then((res) => { if (res.redirected) window.location.replace(res.url); });
        });
    }

    // State
    let rows = [];
    let editIndex = -1;

    const content   = document.querySelector(".workflow-content");
    const btnAdd    = document.getElementById("btnShowForm");

    // ── Build form card ────────────────────────────────────────────────
    const formCard = document.createElement("div");
    formCard.className = "wf-form-card";
    formCard.style.display = "none";
    formCard.innerHTML = `
        <form id="workflowForm" autocomplete="off">
            <div class="wf-grid">
                <div class="wf-field">
                    <label>Operations</label>
                    <input type="text" id="wf_operation" placeholder="Enter operation">
                </div>
                <div class="wf-field">
                    <label>Requirements</label>
                    <input type="text" id="wf_requirement" placeholder="Enter requirement">
                </div>
                <div class="wf-field">
                    <label>Parameter</label>
                    <input type="text" id="wf_parameter" placeholder="Enter parameter">
                </div>
                <div class="wf-field">
                    <label>Authorization</label>
                    <input type="text" id="wf_authority" placeholder="Enter authorization">
                </div>
            </div>
            <div class="wf-form-actions">
                <button type="submit" class="wf-btn-submit" id="btnFormSubmit">Submit</button>
                <button type="button" class="wf-btn-cancel" id="btnCancel">Cancel</button>
            </div>
        </form>`;
    content.appendChild(formCard);

    // ── Build table ────────────────────────────────────────────────────
    const tableWrap = document.createElement("div");
    tableWrap.className = "wf-table-wrap";
    tableWrap.style.display = "none";
    tableWrap.innerHTML = `
        <table class="wf-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Operations</th>
                    <th>Requirements</th>
                    <th>Parameter</th>
                    <th>Authorization</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="wfTableBody"></tbody>
        </table>`;
    content.appendChild(tableWrap);

    const form          = document.getElementById("workflowForm");
    const btnCancel     = document.getElementById("btnCancel");
    const btnFormSubmit = document.getElementById("btnFormSubmit");

    // ── + Add click: show the entry card ────────────────────────────────
    btnAdd.addEventListener("click", function () {
        if (formCard.style.display === "block") {
            formCard.style.display = "none";
            form.reset();
            editIndex = -1;
            // show table again if rows exist
            if (rows.length > 0) tableWrap.style.display = "block";
        } else {
            editIndex = -1;
            form.reset();
            btnFormSubmit.textContent = "Submit";
            tableWrap.style.display = "none";   // hide table while form is open
            formCard.style.display = "block";
            document.getElementById("wf_operation").focus();
        }
    });

    // ── Cancel ─────────────────────────────────────────────────────────
    btnCancel.addEventListener("click", function () {
        formCard.style.display = "none";
        form.reset();
        editIndex = -1;
        // restore table if rows exist
        if (rows.length > 0) tableWrap.style.display = "block";
    });

    // ── Submit ─────────────────────────────────────────────────────────
    form.addEventListener("submit", function (e) {
        e.preventDefault();
        e.stopPropagation();

        const operation   = document.getElementById("wf_operation").value.trim();
        const requirement = document.getElementById("wf_requirement").value.trim();
        const parameter   = document.getElementById("wf_parameter").value.trim();
        const authority   = document.getElementById("wf_authority").value.trim();

        if (!operation || !requirement || !parameter || !authority) {
            alert("Please fill in all fields.");
            return;
        }

        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
        const isEditing = editIndex >= 0;
        const currentEntry = isEditing ? rows[editIndex] : null;
        if (isEditing && !currentEntry.id) {
            alert("This row has no Firestore document ID and cannot be edited.");
            return;
        }
        btnFormSubmit.disabled = true;
        fetch(isEditing
            ? "/aiml11/workflow/edit/" + encodeURIComponent(currentEntry.id)
            : "/aiml11/workflow/submit", {
            method: isEditing ? "PUT" : "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            credentials: "same-origin",
            body: JSON.stringify({ operation, requirement, parameter, authority }),
        }).then(async (response) => {
            const result = await readApiResponse(response);
            if (!response.ok || result.status !== "success") {
                throw new Error(result.message || "Unable to save workflow entry.");
            }
            if (isEditing) rows[editIndex] = result.entry;
            else rows.push(result.entry);
            form.reset();
            editIndex = -1;
            formCard.style.display = "none";
            btnFormSubmit.textContent = "Submit";
            renderTable();
        }).catch((error) => {
            alert(error.message || "Unable to save workflow entry.");
        }).finally(() => {
            btnFormSubmit.disabled = false;
        });
    });

    // ── Render table ───────────────────────────────────────────────────
    function renderTable() {
        const tbody = document.getElementById("wfTableBody");
        if (rows.length === 0) {
            tableWrap.style.display = "none";
            return;
        }
        tableWrap.style.display = "block";
        tbody.innerHTML = "";
        rows.forEach(function (row, i) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${i + 1}</td>
                <td>${esc(row.operation)}</td>
                <td>${esc(row.requirement)}</td>
                <td>${esc(row.parameter)}</td>
                <td>${esc(row.authority)}</td>
                <td class="action-cell">
                    <button class="btn-edit" data-i="${i}">Edit</button>
                    <button class="btn-delete" data-i="${i}">Delete</button>
                </td>`;
            tbody.appendChild(tr);
        });

        tbody.querySelectorAll(".btn-edit").forEach(function (btn) {
            btn.addEventListener("click", function () {
                const i = parseInt(this.getAttribute("data-i"));
                editIndex = i;
                document.getElementById("wf_operation").value   = rows[i].operation;
                document.getElementById("wf_requirement").value = rows[i].requirement;
                document.getElementById("wf_parameter").value   = rows[i].parameter;
                document.getElementById("wf_authority").value   = rows[i].authority;
                btnFormSubmit.textContent = "Update";
                tableWrap.style.display = "none";     // hide table while editing
                formCard.style.display = "block";
                document.getElementById("wf_operation").focus();
            });
        });

        tbody.querySelectorAll(".btn-delete").forEach(function (btn) {
            btn.addEventListener("click", function () {
                const i = parseInt(this.getAttribute("data-i"));
                if (confirm("Delete this row?")) {
                    rows.splice(i, 1);
                    renderTable();
                }
            });
        });
    }

    function esc(str) {
        return String(str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    async function readApiResponse(response) {
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            if (response.redirected) throw new Error("Your session expired. Please sign in again.");
            throw new Error("The server returned a non-JSON response. Check the Flask server log.");
        }
        return response.json();
    }

    fetch("/aiml11/workflow/entries", { credentials: "same-origin" })
        .then(async (response) => {
            const result = await readApiResponse(response);
            if (!response.ok || result.status !== "success") {
                throw new Error(result.message || "Unable to load workflow entries.");
            }
            rows = result.entries || [];
            renderTable();
        })
        .catch((error) => console.error("Workflow entries could not be loaded:", error));
});
