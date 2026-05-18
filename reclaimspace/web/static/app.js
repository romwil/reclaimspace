const SETTINGS_GROUPS = [
  {
    id: "plex",
    title: "Plex",
    fields: [
      { key: "plex_url", label: "Server URL", wide: false },
      { key: "plex_token", label: "Token", wide: false, secret: true },
      { key: "plex_movie_section", label: "Movie library key", wide: false, hint: "Numeric key from Plex libraries" },
      { key: "plex_tv_section", label: "TV library key", wide: false, hint: "Numeric key from Plex libraries" },
    ],
  },
  {
    id: "arr",
    title: "Radarr & Sonarr",
    fields: [
      { key: "radarr_url", label: "Radarr URL", wide: false },
      { key: "radarr_api_key", label: "Radarr API key", wide: false, secret: true },
      { key: "sonarr_url", label: "Sonarr URL", wide: false },
      { key: "sonarr_api_key", label: "Sonarr API key", wide: false, secret: true },
    ],
  },
  {
    id: "paths",
    title: "Paths & mappings",
    open: true,
    fields: [
      { key: "movies_root", label: "Movies root", wide: true, hint: "Path inside container, e.g. /media/movies" },
      { key: "tv_root", label: "TV root", wide: true, hint: "Path inside container, e.g. /media/tv" },
      { key: "quarantine_root", label: "Quarantine root", wide: true },
      { key: "path_mappings", label: "Movie path mappings", wide: true, hint: "container=host;..." },
      { key: "tv_path_mappings", label: "TV path mappings", wide: true, hint: "container=host;..." },
      { key: "tv_page_size", label: "TV Plex page size", wide: false },
    ],
  },
];

const settingsForm = document.getElementById("settings-form");
const settingsStatus = document.getElementById("settings-status");
const scanStatus = document.getElementById("scan-status");
const jobsList = document.getElementById("jobs-list");
const reportsList = document.getElementById("reports-list");
const reportViewer = document.getElementById("report-viewer");
const reportSummary = document.getElementById("report-summary");
const downloadReport = document.getElementById("download-report");
const health = document.getElementById("health");

let pollTimer = null;
let activeReportName = null;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildSettingsForm() {
  settingsForm.innerHTML = SETTINGS_GROUPS.map((group) => {
    const fieldsHtml = group.fields
      .map((field) => {
        const wide = field.wide ? " wide" : "";
        const type = field.secret ? "password" : "text";
        const hint = field.hint
          ? `<span class="field-hint">${escapeHtml(field.hint)}</span>`
          : "";
        const secretToggle = field.secret
          ? `<button type="button" class="toggle-secret" data-target="${field.key}" title="Show/hide">Show</button>`
          : "";
        return `<label class="${wide.trim()}">
          ${escapeHtml(field.label)}
          ${hint}
          <div class="input-wrap">
            <input class="input" name="${field.key}" type="${type}" autocomplete="off" />
            ${secretToggle}
          </div>
        </label>`;
      })
      .join("");
    const openAttr = group.open ? " open" : "";
    return `<details class="settings-group"${openAttr}>
      <summary>${escapeHtml(group.title)}</summary>
      <div class="settings-grid">${fieldsHtml}</div>
    </details>`;
  }).join("");

  settingsForm.querySelectorAll(".toggle-secret").forEach((button) => {
    button.addEventListener("click", () => {
      const input = settingsForm.querySelector(`[name="${button.dataset.target}"]`);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.textContent = showing ? "Hide" : "Show";
    });
  });
}

function allSettingsFields() {
  return SETTINGS_GROUPS.flatMap((group) => group.fields);
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

function readSettingsForm() {
  const data = {};
  for (const field of allSettingsFields()) {
    const input = settingsForm.querySelector(`[name="${field.key}"]`);
    data[field.key] = field.key === "tv_page_size" ? Number(input.value) || 500 : input.value;
  }
  return data;
}

function fillSettingsForm(settings) {
  for (const field of allSettingsFields()) {
    const input = settingsForm.querySelector(`[name="${field.key}"]`);
    if (input) input.value = settings[field.key] ?? "";
  }
}

function setToast(el, message, type = "") {
  el.textContent = message;
  el.className = `toast-area${type ? ` ${type}` : ""}`;
}

async function loadHealth() {
  const dot = health.querySelector(".health-dot");
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

async function loadSettings() {
  const settings = await api("/api/settings");
  fillSettingsForm(settings);
}

async function saveSettings() {
  const btn = document.getElementById("save-settings");
  setToast(settingsStatus, "Saving…", "loading");
  btn.disabled = true;
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(readSettingsForm()),
    });
    setToast(settingsStatus, "Settings saved.", "ok");
  } catch (error) {
    setToast(settingsStatus, error.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function loadPlexSections() {
  const container = document.getElementById("plex-sections");
  container.classList.remove("hidden");
  container.className = "plex-sections loading";
  container.textContent = "Loading Plex libraries…";
  try {
    const sections = await api("/api/plex/sections");
    container.className = "plex-sections";
    if (!sections.length) {
      container.textContent = "No libraries returned from Plex.";
      return;
    }
    container.innerHTML = sections
      .map((section) => {
        const type = escapeHtml(section.type || "unknown");
        const title = escapeHtml(section.title || "Untitled");
        const key = escapeHtml(section.key);
        const target =
          section.type === "movie" ? "plex_movie_section" : section.type === "show" ? "plex_tv_section" : "";
        const useBtn = target
          ? `<button type="button" class="use-key-btn" data-key="${key}" data-target="${target}">Use key</button>`
          : "";
        return `<div class="plex-library">
          <div class="plex-library-info">
            <strong>${title}</strong>
            <span>${type} · key <code>${key}</code></span>
          </div>
          ${useBtn}
        </div>`;
      })
      .join("");

    container.querySelectorAll(".use-key-btn").forEach((button) => {
      button.addEventListener("click", () => {
        const input = settingsForm.querySelector(`[name="${button.dataset.target}"]`);
        if (input) {
          input.value = button.dataset.key;
          input.focus();
          setToast(settingsStatus, `Set ${button.dataset.target} to ${button.dataset.key}. Save to persist.`, "ok");
        }
      });
    });
  } catch (error) {
    container.className = "plex-sections";
    container.textContent = error.message;
  }
}

function setScanButtonsDisabled(disabled) {
  document.querySelectorAll(".scan-btn").forEach((btn) => {
    btn.disabled = disabled;
  });
}

async function hasActiveJob() {
  const jobs = await api("/api/jobs");
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

async function startScan(mode) {
  const mediaType = document.getElementById("scan-media-type").value;
  if (
    mode === "quarantine" &&
    !window.confirm(
      "Move duplicate files to quarantine?\n\nThis changes files on disk. A manifest is written for rollback."
    )
  ) {
    return;
  }
  setToast(scanStatus, "Starting scan…", "loading");
  setScanButtonsDisabled(true);
  try {
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ media_type: mediaType, mode }),
    });
    const modeLabel = mode === "dry_run" ? "dry run" : "quarantine";
    setToast(scanStatus, `${capitalize(mediaType)} ${modeLabel} started · job ${job.id}`, "ok");
    await loadJobs();
    startPolling();
  } catch (error) {
    setToast(scanStatus, error.message, "error");
    setScanButtonsDisabled(false);
  }
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
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
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function modeLabel(mode) {
  return mode === "quarantine" ? "Quarantine" : "Dry run";
}

function renderJobItem(job) {
  const summary = job.summary || {};
  const status = job.status || "unknown";
  let detail;
  if (job.error) {
    detail = escapeHtml(job.error);
  } else if (status === "running" || status === "queued") {
    detail = status === "running" ? "Scan in progress…" : "Waiting to start…";
  } else {
    detail = `Ready ${summary.ready_count ?? 0} · Candidates ${summary.candidate_count ?? 0}`;
    if (summary.quarantined_count) {
      detail += ` · Moved ${summary.quarantined_count}`;
    }
    if (summary.needs_review_count) {
      detail += ` · Review ${summary.needs_review_count}`;
    }
  }
  const active = job.report_name === activeReportName ? " active" : "";
  return `<button type="button" class="job-item${active}" data-report="${escapeHtml(job.report_name || "")}" role="listitem">
    <div class="job-row">
      <span class="job-title">
        <span class="badge badge-${job.media_type}">${job.media_type}</span>
        <span class="badge badge-${job.mode}">${modeLabel(job.mode)}</span>
      </span>
      <span class="badge badge-${status}">${status}</span>
    </div>
    <div class="job-meta">${formatTime(job.created_at)} — ${detail}</div>
  </button>`;
}

async function loadJobs() {
  const jobs = await api("/api/jobs");
  const active = jobs.some((j) => j.status === "queued" || j.status === "running");
  setScanButtonsDisabled(active);

  if (!jobs.length) {
    jobsList.innerHTML = `<div class="empty-state"><strong>No jobs yet</strong><p>Run a dry run to generate your first report.</p></div>`;
    return;
  }

  jobsList.innerHTML = jobs.map(renderJobItem).join("");

  jobsList.querySelectorAll(".job-item").forEach((item) => {
    item.addEventListener("click", () => {
      const reportName = item.dataset.report;
      if (reportName) viewReport(reportName);
    });
  });
}

function renderReportSummary(data) {
  const chips = [
    { label: "Ready", value: data.ready_count ?? 0, class: "highlight" },
    { label: "Candidates", value: data.candidate_count ?? 0, class: "" },
    { label: "Needs review", value: data.needs_review_count ?? 0, class: data.needs_review_count ? "warn" : "" },
  ];
  if (data.quarantined_count != null && data.quarantined_count > 0) {
    chips.push({ label: "Quarantined", value: data.quarantined_count, class: "success" });
  }
  if (data.missing_source_count != null && data.missing_source_count > 0) {
    chips.push({ label: "Missing on disk", value: data.missing_source_count, class: "warn" });
  }
  return chips
    .map(
      (chip) =>
        `<div class="stat-chip ${chip.class}"><strong>${chip.value}</strong><span>${escapeHtml(chip.label)}</span></div>`
    )
    .join("");
}

async function loadReports() {
  const reports = await api("/api/reports");
  if (!reports.length) {
    reportsList.innerHTML = `<div class="empty-state"><strong>No reports yet</strong><p>Reports appear here after a scan completes.</p></div>`;
    return;
  }

  reportsList.innerHTML = reports
    .map((report) => {
      const active = report.name === activeReportName ? " active" : "";
      return `<button type="button" class="report-item${active}" data-name="${escapeHtml(report.name)}" role="listitem">
        <div class="report-name">${escapeHtml(report.name)}</div>
        <div class="job-meta">${formatBytes(report.size_bytes)} · ${formatTime(report.modified_at)}</div>
      </button>`;
    })
    .join("");

  reportsList.querySelectorAll(".report-item").forEach((item) => {
    item.addEventListener("click", () => viewReport(item.dataset.name));
  });
}

async function viewReport(name) {
  activeReportName = name;
  await loadReports();
  jobsList.querySelectorAll(".job-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.report === name);
  });

  reportSummary.classList.add("hidden");
  reportViewer.textContent = "Loading report…";
  downloadReport.classList.add("hidden");

  try {
    const data = await api(`/api/reports/${encodeURIComponent(name)}`);
    reportSummary.innerHTML = renderReportSummary(data);
    reportSummary.classList.remove("hidden");
    reportViewer.textContent = JSON.stringify(data, null, 2);
    downloadReport.href = `/api/reports/${encodeURIComponent(name)}/download`;
    downloadReport.download = name;
    downloadReport.classList.remove("hidden");
  } catch (error) {
    reportViewer.textContent = error.message;
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = window.setInterval(async () => {
    await loadJobs();
    const jobs = await api("/api/jobs");
    const active = jobs.some((job) => job.status === "queued" || job.status === "running");
    if (!active) {
      window.clearInterval(pollTimer);
      pollTimer = null;
      await loadReports();
      const latest = jobs.find((j) => j.status === "completed" && j.report_name);
      if (latest?.report_name) {
        viewReport(latest.report_name);
        setToast(scanStatus, "Scan complete — report opened.", "ok");
      }
    }
  }, 2500);
}

document.getElementById("save-settings").addEventListener("click", saveSettings);
document.getElementById("load-plex-sections").addEventListener("click", loadPlexSections);
document.getElementById("refresh-jobs").addEventListener("click", loadJobs);
document.getElementById("refresh-reports").addEventListener("click", loadReports);
document.querySelectorAll(".scan-btn").forEach((button) => {
  button.addEventListener("click", () => startScan(button.dataset.mode));
});

buildSettingsForm();
loadHealth();
loadSettings().catch((e) => setToast(settingsStatus, e.message, "error"));
loadJobs().catch(() => {});
loadReports().catch(() => {});
hasActiveJob().then((active) => {
  if (active) startPolling();
});
