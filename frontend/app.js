const API_BASE = "";

let currentRole = null;
let currentHeaders = {};

const ROLES = {
    "ENG_STANDARD": {
        name: "Standard Engineer",
        headers: {
            "X-User-ID": "11111111-1111-1111-1111-111111111111",
            "X-Functional-Role": "ENGINEER",
            "X-Allowed-Namespaces": "eng.core,eng.api",
            "X-Sensitivity-Ceiling": "2"
        },
        views: ["view-upload", "view-search"]
    },
    "STEWARD_CORE": {
        name: "Data Steward",
        headers: {
            "X-User-ID": "22222222-2222-2222-2222-222222222222",
            "X-Functional-Role": "STEWARD",
            "X-Allowed-Namespaces": "eng.core,eng.api,eng.infra",
            "X-Sensitivity-Ceiling": "3"
        },
        views: ["view-upload", "view-search", "view-steward"]
    },
    "ADMIN_EXEC": {
        name: "Security Admin",
        headers: {
            "X-User-ID": "33333333-3333-3333-3333-333333333333",
            "X-Functional-Role": "ADMIN",
            "X-Allowed-Namespaces": "eng.core,eng.api,eng.infra,hr.secret",
            "X-Sensitivity-Ceiling": "4"
        },
        views: ["view-upload", "view-search", "view-steward", "view-ledger"]
    }
};

// UI Elements
const landingState = document.getElementById("landing-state");
const workspaceState = document.getElementById("workspace-state");
const roleButtons = document.querySelectorAll(".role-btn");
const logoutBtn = document.getElementById("logoutBtn");
const currentRoleDisplay = document.getElementById("currentRoleDisplay");
const navButtons = document.querySelectorAll(".nav-btn");
const viewPanes = document.querySelectorAll(".view-pane");

// Setup Event Listeners
document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();

    // Role Selection
    roleButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const roleKey = btn.getAttribute("data-role");
            loginAs(roleKey);
        });
    });

    // Logout
    logoutBtn.addEventListener("click", () => {
        logout();
    });

    // Navigation
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            switchView(targetId);
            
            // Trigger specific loads
            if(targetId === "view-steward") loadPendingQueue();
        });
    });

    // Forms & Actions
    document.getElementById("ingestionForm").addEventListener("submit", handleUpload);
    document.getElementById("searchBtn").addEventListener("click", handleSearch);
    document.getElementById("verifyLedgerBtn").addEventListener("click", handleVerifyLedger);
});

// Authentication Flow Simulation
function loginAs(roleKey) {
    currentRole = ROLES[roleKey];
    currentHeaders = currentRole.headers;
    
    currentRoleDisplay.textContent = currentRole.name;
    
    // Configure Sidebar Visibility
    navButtons.forEach(btn => {
        const target = btn.getAttribute("data-target");
        if (currentRole.views.includes(target)) {
            btn.classList.remove("hidden-nav");
        } else {
            btn.classList.add("hidden-nav");
        }
    });

    // Transition State
    landingState.classList.remove("active-state");
    landingState.classList.add("hidden-state");
    workspaceState.classList.remove("hidden-state");
    workspaceState.classList.add("active-state");

    // Default view
    if (roleKey === "ADMIN_EXEC") {
        switchView("view-ledger");
        updateLastVerificationUI();
    } else {
        switchView("view-upload");
    }
    showToast(`Logged in securely as ${currentRole.name}`, "success");
}

function updateLastVerificationUI() {
    const lastTime = localStorage.getItem("lastVerificationTime");
    if (lastTime) {
        document.getElementById("lastVerifyText").textContent = lastTime;
    }
}

function logout() {
    currentRole = null;
    currentHeaders = {};
    
    workspaceState.classList.remove("active-state");
    workspaceState.classList.add("hidden-state");
    landingState.classList.remove("hidden-state");
    landingState.classList.add("active-state");
}

function switchView(targetId) {
    viewPanes.forEach(pane => pane.classList.remove("active"));
    navButtons.forEach(btn => btn.classList.remove("active"));
    
    document.getElementById(targetId).classList.add("active");
    const navBtn = document.querySelector(`[data-target="${targetId}"]`);
    if(navBtn) navBtn.classList.add("active");
}

// API Interactions
async function handleUpload(e) {
    e.preventDefault();
    
    const payload = {
        title: document.getElementById("docTitle").value,
        body: document.getElementById("docBody").value,
        namespace: document.getElementById("docNamespace").value,
        sensitivity_level: parseInt(document.getElementById("docSensitivity").value)
    };

    try {
        const res = await fetch(`${API_BASE}/api/v1/ingestion/items`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...currentHeaders
            },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showToast("Document ingested and sent to quarantine.", "success");
            document.getElementById("ingestionForm").reset();
        } else {
            const err = await res.json();
            const errMsg = err.message || (typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || 'Upload failed'));
            showToast(`Error: ${errMsg}`, "error");
        }
    } catch (err) {
        showToast("Network Error: Is the backend running?", "error");
    }
}

async function handleSearch() {
    const query = document.getElementById("searchInput").value;
    if (!query) return;

    try {
        const res = await fetch(`${API_BASE}/api/v1/retrieval/search`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...currentHeaders
            },
            body: JSON.stringify({ query: query, top_k: 10 })
        });

        const data = await res.json();
        renderSearchResults(Array.isArray(data) ? data : (data.items || []));
    } catch (err) {
        showToast("Search failed", "error");
    }
}

function renderSearchResults(items) {
    const container = document.getElementById("searchResults");
    container.innerHTML = "";
    
    if (items.length === 0) {
        container.innerHTML = "<p>No active documents found within your clearance.</p>";
        return;
    }

    items.forEach(item => {
        const div = document.createElement("div");
        div.className = "result-card";
        div.innerHTML = `
            <div class="result-title">${item.title}</div>
            <div class="result-meta">
                <span class="meta-pill active">Score: ${(item.score).toFixed(2)}</span>
                <span class="meta-pill">NS: ${item.namespace || item.domain_namespace}</span>
                <span class="meta-pill">Sens: L${item.sensitivity_level}</span>
            </div>
            <div class="result-body">${item.body.substring(0, 150)}...</div>
        `;
        container.appendChild(div);
    });
}

async function loadPendingQueue() {
    try {
        const res = await fetch(`${API_BASE}/api/v1/governance/pending`, {
            headers: { ...currentHeaders }
        });
        
        if (!res.ok) {
            if (res.status === 403) {
                showToast("Unauthorized: You lack Steward clearance.", "error");
                document.getElementById("stewardQueueList").innerHTML = "<p>Unauthorized Access Blocked.</p>";
                return;
            }
            throw new Error("Failed to load");
        }

        const items = await res.json();
        renderPendingQueue(items);
    } catch (err) {
        showToast("Failed to load queue", "error");
    }
}

function renderPendingQueue(items) {
    const container = document.getElementById("stewardQueueList");
    container.innerHTML = "";
    
    if (items.length === 0) {
        container.innerHTML = "<p>Queue is empty. You're all caught up!</p>";
        return;
    }

    items.forEach(item => {
        const div = document.createElement("div");
        div.className = "queue-item";
        div.innerHTML = `
            <div class="result-title">${item.title}</div>
            <div class="result-meta">
                <span class="meta-pill pending">PENDING</span>
                <span class="meta-pill">NS: ${item.namespace || item.domain_namespace}</span>
                <span class="meta-pill">Sens: L${item.sensitivity_level}</span>
            </div>
            <div class="result-body" style="margin-bottom: 1rem;">${item.body}</div>
            <div class="queue-actions">
                <input type="text" id="justification-${item.item_id}" placeholder="Mandatory Adjudication Justification..." class="search-input">
                <div style="display: flex; gap: 1rem; margin-top: 0.5rem;">
                    <button class="btn btn-primary" onclick="adjudicate('${item.item_id}', 'approve')">Approve</button>
                    <button class="btn btn-danger" onclick="adjudicate('${item.item_id}', 'reject')">Reject</button>
                </div>
            </div>
        `;
        container.appendChild(div);
    });
}

window.adjudicate = async function(itemId, action) {
    const justification = document.getElementById(`justification-${itemId}`).value;
    if (!justification) {
        showToast("Justification is required for audit logs.", "error");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/v1/governance/adjudicate/${itemId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...currentHeaders
            },
            body: JSON.stringify({ action, justification })
        });

        if (res.ok) {
            showToast(`Item successfully ${action}d.`, "success");
            loadPendingQueue(); // reload
        } else {
            const err = await res.json();
            const errMsg = err.message || (typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || 'Adjudication failed'));
            showToast(`Error: ${errMsg}`, "error");
        }
    } catch (err) {
        showToast("Adjudication failed", "error");
    }
};

async function handleVerifyLedger() {
    const btn = document.getElementById("verifyLedgerBtn");
    const shield = document.querySelector(".glowing-shield");
    const resPanel = document.getElementById("ledgerResultPanel");
    
    // Set Loading State
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon"><i data-lucide="loader" class="lucide-spin"></i></span><span class="btn-text">Running cryptographic verification...</span>`;
    lucide.createIcons();
    shield.classList.add("scanning-pulse");
    resPanel.classList.add("hidden");
    resPanel.classList.remove("compromised");
    
    try {
        const res = await fetch(`${API_BASE}/api/v1/audit/verify`, {
            headers: { ...currentHeaders }
        });
        
        if (!res.ok) {
            if (res.status === 403) {
                showToast("Unauthorized: Admin clearance required.", "error");
                throw new Error("Unauthorized");
            }
            throw new Error("Verification failed");
        }

        const data = await res.json();
        
        // Update Result Panel
        const now = new Date();
        const timeString = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        document.getElementById("resRecordsVerified").textContent = data.verified_records || 0;
        document.getElementById("resTimestamp").textContent = timeString;
        document.getElementById("resMessage").textContent = data.message;
        
        if (data.compromised) {
            document.getElementById("resLedgerStatus").textContent = "Compromised";
            document.getElementById("resLedgerStatus").style.color = "#ef4444";
            resPanel.classList.add("compromised");
        } else {
            document.getElementById("resLedgerStatus").textContent = "Healthy";
            document.getElementById("resLedgerStatus").style.color = "#10b981";
            
            // Save to local storage for convenience
            const cacheStr = `Today at ${timeString} (Local)`;
            localStorage.setItem("lastVerificationTime", cacheStr);
            updateLastVerificationUI();
        }
        
        resPanel.classList.remove("hidden");
    } catch (err) {
        if (err.message !== "Unauthorized") {
            showToast("Failed to verify ledger", "error");
        }
    } finally {
        // Reset Button State
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon"><i data-lucide="shield"></i></span><span class="btn-text">Run Integrity Verification</span>`;
        shield.classList.remove("scanning-pulse");
        lucide.createIcons();
    }
}

// Toast Utility
function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
