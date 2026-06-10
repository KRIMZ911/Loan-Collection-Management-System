/* ═══════════════════════════════════════
   Collection Management System — JS
   ═══════════════════════════════════════ */

let currentCaseId = null;

// ── Modal ──
function openActionModal(caseId, borrowerName) {
    currentCaseId = caseId;
    document.getElementById("modalBorrower").textContent = borrowerName || "Сонгосон хэрэг";
    document.getElementById("actionModal").classList.add("show");
}

function closeModal() {
    document.getElementById("actionModal").classList.remove("show");
    currentCaseId = null;
}

// Close modal on overlay click
document.addEventListener("DOMContentLoaded", function() {
    const overlay = document.getElementById("actionModal");
    if (overlay) {
        overlay.addEventListener("click", function(e) {
            if (e.target === this) closeModal();
        });
    }
    // Set first nav item active
    const firstNav = document.querySelector(".nav-item");
    if (firstNav) firstNav.classList.add("active");

    /* Make table rows clickable — skip if click was on a button */
    var rows = document.querySelectorAll("tr[data-case-id]");
    for (var i = 0; i < rows.length; i++) {
        rows[i].addEventListener("click", function(e) {
            if (e.target.closest("button") || e.target.closest(".quick-actions")) return;
            var id = this.getAttribute("data-case-id");
            if (id) goToCase(id);
        });
    }
});

// ── Submit Action ──
function submitAction() {
    if (!currentCaseId) return;

    const data = {
        action_type: document.getElementById("actionType").value,
        outcome: document.getElementById("actionOutcome").value,
        notes: document.getElementById("actionNote").value,
    };

    fetch(`/api/cases/${currentCaseId}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    })
    .then(res => res.json())
    .then(result => {
        closeModal();
        showToast(result.message || "Амжилттай бүртгэгдлээ!");
        // Clear form
        document.getElementById("actionNote").value = "";
    })
    .catch(err => {
        showToast("Алдаа гарлаа. Дахин оролдоно уу.");
        console.error(err);
    });
}

/* Quick Action — one-click, no modal */
function quickAction(caseId, actionType, outcome) {
    fetch("/api/cases/" + caseId + "/quick-action", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action_type: actionType, outcome: outcome})
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        showToast(res.message || "Амжилттай!");
        var row = document.querySelector('tr[data-case-id="' + caseId + '"]');
        if (row) {
            row.classList.add("row-flash");
            setTimeout(function() { row.classList.remove("row-flash"); }, 800);
        }
    })
    .catch(function() { showToast("Алдаа гарлаа"); });
}

/* Navigate to case detail page */
function goToCase(caseId) {
    window.location.href = "/case/" + caseId;
}

// ── Toast ──
function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = "✅ " + message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2500);
}

// ── Table Filter ──
function filterTable(input) {
    const val = input.value.toLowerCase();
    const table = input.closest(".card-panel").querySelector("table");
    if (!table) return;
    table.querySelectorAll("tbody tr").forEach(tr => {
        tr.style.display = tr.textContent.toLowerCase().includes(val) ? "" : "none";
    });
}

// ── Sidebar Nav ──
function setActiveNav(el) {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    el.classList.add("active");
}

// ── Format number ──
function formatMNT(num) {
    return new Intl.NumberFormat("mn-MN").format(num) + "₮";
}
