/** Shared helpers for Reclaimspace pages. */

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      const parsed = JSON.parse(detail);
      detail = parsed.detail || detail;
    } catch {
      /* plain text */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}

function setToast(el, message, type = "") {
  if (!el) return;
  el.textContent = message;
  el.className = `toast-area${type ? ` ${type}` : ""}`;
}

function formatTime(epoch) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function pathBasename(path) {
  if (!path) return "";
  const parts = String(path).replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

function initHeaderNav() {
  const page = document.body.dataset.page;
  document.querySelectorAll(".nav-link[data-nav]").forEach((link) => {
    link.classList.toggle("active", link.dataset.nav === page);
  });
}

async function loadHealth() {
  const health = document.getElementById("health");
  if (!health) return;
  const text = health.querySelector(".health-text");
  try {
    const data = await api("/api/health");
    health.className = "health-pill online";
    text.textContent = `v${data.version}`;
  } catch {
    health.className = "health-pill offline";
    text.textContent = "Offline";
  }
}

async function loadSetupHealth() {
  const el = document.getElementById("setup-health");
  if (!el) return;
  try {
    const status = await api("/api/setup/status");
    const ok =
      status.checks?.plex?.ok && status.checks?.radarr?.ok && status.checks?.sonarr?.ok;
    el.textContent = ok ? "All connected" : "Setup attention";
    el.className = `setup-health ${ok ? "ok" : "warn"}`;
    el.classList.remove("hidden");
  } catch {
    el.classList.add("hidden");
  }
}

async function openSetupWizard() {
  if (!window.confirm("Re-run the setup wizard? Your saved API keys and paths are kept.")) {
    return;
  }
  await api("/api/setup/reset", { method: "POST" });
  const onDashboard = document.body.dataset.page === "dashboard";
  if (onDashboard) {
    const wizardEl = document.getElementById("wizard-root");
    const dashboardEl = document.getElementById("dashboard");
    wizardEl?.classList.remove("hidden");
    dashboardEl?.classList.add("hidden");
    if (window.initWizard) await window.initWizard();
    return;
  }
  window.location.href = "/";
}

function bindSetupWizardButtons() {
  document.getElementById("open-setup-wizard")?.addEventListener("click", openSetupWizard);
  document.getElementById("rerun-wizard")?.addEventListener("click", openSetupWizard);
}

function showBootstrapError(error) {
  console.error("Reclaimspace UI failed to start:", error);
  const banner = document.createElement("p");
  banner.className = "error-banner";
  banner.setAttribute("role", "alert");
  banner.textContent = `Failed to start: ${error.message}`;
  document.body.prepend(banner);
}
