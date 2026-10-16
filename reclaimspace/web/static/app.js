/** Dashboard: scans, jobs, reports, restore. */

const scanStatus = document.getElementById("scan-status");
const jobsList = document.getElementById("jobs-list");
const reportsList = document.getElementById("reports-list");
const reportSummary = document.getElementById("report-summary");
const reportHumanSummary = document.getElementById("report-human-summary");
const reportGridEl = document.getElementById("report-grid");
const reportJsonEl = document.getElementById("report-json");
const reportEmptyEl = document.getElementById("report-empty");
const downloadReport = document.getElementById("download-report");

const reportGrid = reportGridEl ? new ReportDataGrid(reportGridEl) : null;

let pollTimer = null;
let activeReportName = null;
let activeReportTab = "grid";
let cachedRawReport = null;

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function modeLabel(mode) {
  return mode === "quarantine" ? "Quarantine" : "Dry run";
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
    const modeText = mode === "dry_run" ? "dry run" : "quarantine";
    setToast(scanStatus, `${capitalize(mediaType)} ${modeText} started · job ${job.id}`, "ok");
    await loadJobs();
    startPolling();
  } catch (error) {
    setToast(scanStatus, error.message, "error");
    setScanButtonsDisabled(false);
  }
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
    if (summary.protected_count != null) detail += ` · Protected ${summary.protected_count}`;
    if (summary.quarantined_count) detail += ` · Moved ${summary.quarantined_count}`;
    if (summary.needs_review_count) detail += ` · Review ${summary.needs_review_count}`;
  }
  const active = job.report_name === activeReportName ? " active" : "";
  const progress = job.progress || {};
  const progressHtml =
    status === "running" || status === "queued"
      ? `<div class="progress-bar"><div class="progress-fill" style="width:${progress.percent || 0}%"></div></div>
         <p class="job-meta">${escapeHtml(progress.message || progress.phase || "")}</p>`
      : "";
  return `<button type="button" class="job-item${active}" data-report="${escapeHtml(job.report_name || "")}" role="listitem">
    <div class="job-row">
      <span class="job-title">
        <span class="badge badge-${job.media_type}">${job.media_type}</span>
        <span class="badge badge-${job.mode}">${modeLabel(job.mode)}</span>
      </span>
      <span class="badge badge-${status}">${status}</span>
    </div>
    ${progressHtml}
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

function protectedGroupCount(data, groups) {
  if (data && data.protected_count != null) return Number(data.protected_count);
  const source = groups || data?.groups;
  if (!Array.isArray(source)) return 0;
  return source.filter((group) => group.status === "protected").length;
}

function renderReportSummary(data, groups) {
  const chips = [
    { label: "Ready", value: data.ready_count ?? 0, class: "highlight" },
    { label: "Candidates", value: data.candidate_count ?? 0, class: "" },
    { label: "Protected", value: protectedGroupCount(data, groups), class: "" },
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

function setReportTab(tab) {
  activeReportTab = tab;
  document.querySelectorAll("[data-report-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.reportTab === tab);
  });
  reportGridEl?.classList.toggle("hidden", tab !== "grid");
  reportJsonEl?.classList.toggle("hidden", tab !== "json");
}

async function loadReportGrid(name) {
  const table = await api(`/api/reports/${encodeURIComponent(name)}/groups?limit=10000`);
  if (reportGrid && reportGrid.reportName !== name) {
    reportGrid.filters.status = "ready";
    reportGrid.filters.search = "";
    reportGrid.reportName = name;
  }
  if (!table.groups?.length) {
    reportGridEl.innerHTML = "<p class='hint'>No groups in this report.</p>";
    return table;
  }
  reportGrid.setRows(table.groups);
  return table;
}

function showReportPane() {
  reportEmptyEl?.classList.add("hidden");
}

function hideReportData() {
  reportSummary.classList.add("hidden");
  reportHumanSummary.classList.add("hidden");
  reportGridEl?.classList.add("hidden");
  reportJsonEl?.classList.add("hidden");
  reportEmptyEl?.classList.remove("hidden");
  cachedRawReport = null;
}

async function viewReport(name) {
  activeReportName = name;
  await loadReports();
  jobsList.querySelectorAll(".job-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.report === name);
  });

  showReportPane();
  reportSummary.classList.add("hidden");
  reportHumanSummary.classList.add("hidden");
  reportGridEl.innerHTML = "<p class='hint'>Loading…</p>";
  reportJsonEl.innerHTML = "";
  setReportTab(activeReportTab);
  downloadReport.classList.add("hidden");

  try {
    const summary = await api(`/api/reports/${encodeURIComponent(name)}/summary`);
    reportSummary.innerHTML = renderReportSummary(summary);
    reportSummary.classList.remove("hidden");
    reportHumanSummary.textContent = summary.summary_line || "";
    reportHumanSummary.classList.remove("hidden");

    if (activeReportTab === "grid") {
      const table = await loadReportGrid(name);
      if (summary.protected_count == null && table?.groups) {
        reportSummary.innerHTML = renderReportSummary(summary, table.groups);
      }
      reportGridEl.classList.remove("hidden");
    } else {
      cachedRawReport = await api(`/api/reports/${encodeURIComponent(name)}`);
      if (summary.protected_count == null) {
        reportSummary.innerHTML = renderReportSummary(summary, cachedRawReport?.groups);
      }
      renderJsonPanel(reportJsonEl, cachedRawReport);
      reportJsonEl.classList.remove("hidden");
    }

    downloadReport.href = `/api/reports/${encodeURIComponent(name)}/download`;
    downloadReport.download = name;
    downloadReport.classList.remove("hidden");
  } catch (error) {
    reportGridEl.innerHTML = "";
    reportJsonEl.textContent = error.message;
    reportJsonEl.classList.remove("hidden");
  }
}

async function loadManifests() {
  const list = document.getElementById("manifest-list");
  const manifests = await api("/api/quarantine/manifests");
  if (!manifests.length) {
    list.innerHTML = "<p class='hint'>No quarantine manifests found.</p>";
    return;
  }
  list.innerHTML = manifests
    .map(
      (m) => `<div class="manifest-item">
        <div><strong>${escapeHtml(m.run_id)}</strong> · ${m.move_count} files</div>
        <div class="manifest-actions">
          <button type="button" class="btn ghost btn-sm" data-manifest="${escapeHtml(m.manifest_path)}" data-dry="1">Preview restore</button>
          <button type="button" class="btn danger btn-sm" data-manifest="${escapeHtml(m.manifest_path)}" data-dry="0">Restore</button>
        </div>
      </div>`
    )
    .join("");
  list.querySelectorAll("button[data-manifest]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const dryRun = btn.dataset.dry === "1";
      if (!dryRun && !window.confirm("Move files back from quarantine to their original paths?")) return;
      const result = await api("/api/quarantine/restore", {
        method: "POST",
        body: JSON.stringify({ manifest_path: btn.dataset.manifest, dry_run: dryRun }),
      });
      setToast(
        document.getElementById("restore-status"),
        dryRun
          ? `Preview: would restore ${result.restored_count} files.`
          : `Restored ${result.restored_count} files.`,
        "ok"
      );
    });
  });
}

const orphanStatus = document.getElementById("orphan-status");
const orphanQuarantineStatus = document.getElementById("orphan-quarantine-status");
const orphanCandidatesEl = document.getElementById("orphan-candidates");
const orphanQuarantineEl = document.getElementById("orphan-quarantine-list");

let orphanScanning = false;
let orphanBusy = false;
let orphanScanned = false;
let orphanMediaType = null;
let orphanCandidates = [];
let orphanLoose = [];
let orphanQuarantine = [];
const orphanSelected = new Set();
const orphanQuarantineSelected = new Set();

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function oneLine(value) {
  return String(value ?? "").replace(/[\r\n\u2028\u2029]+/g, " ");
}

function humanSize(bytes) {
  if (bytes == null || bytes === "") return "—";
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "—";
  return formatBytes(value);
}

function bullet(names) {
  return names.map((name) => `• ${oneLine(name)}`).join("\n");
}

function managerLabel(mediaType) {
  return mediaType === "tv" ? "Sonarr" : "Radarr";
}

function setOrphanScanLabel(text) {
  const label = document.getElementById("orphan-scan-label");
  if (label) label.textContent = text;
}

function setActionLabel(id, text) {
  const button = document.getElementById(id);
  if (button) button.textContent = text;
}

function selectedOrphanRows() {
  return orphanCandidates.filter((row) => orphanSelected.has(row.name));
}

function selectedOrphanQuarantineRows() {
  return orphanQuarantine.filter((row) => orphanQuarantineSelected.has(row.name));
}

function updateOrphanButtons() {
  const locked = orphanBusy || orphanScanning;
  const scanButton = document.getElementById("orphan-scan");
  const selectAll = document.getElementById("orphan-select-all");
  const selectNone = document.getElementById("orphan-select-none");
  const quarantine = document.getElementById("orphan-quarantine");
  if (scanButton) scanButton.disabled = locked;
  if (selectAll) selectAll.disabled = locked || orphanCandidates.length === 0;
  if (selectNone) selectNone.disabled = locked || orphanSelected.size === 0;
  if (quarantine) quarantine.disabled = locked || selectedOrphanRows().length === 0;

  const quarantineAll = document.getElementById("orphan-quarantine-select-all");
  const quarantineNone = document.getElementById("orphan-quarantine-select-none");
  const restore = document.getElementById("orphan-restore");
  const purge = document.getElementById("orphan-purge");
  const refresh = document.getElementById("refresh-orphan-quarantine");
  const selected = selectedOrphanQuarantineRows();
  if (quarantineAll) quarantineAll.disabled = orphanBusy || orphanQuarantine.length === 0;
  if (quarantineNone) quarantineNone.disabled = orphanBusy || orphanQuarantineSelected.size === 0;
  if (restore) restore.disabled = orphanBusy || selected.length === 0;
  if (purge) purge.disabled = orphanBusy || selected.length === 0;
  if (refresh) refresh.disabled = orphanBusy;
}

function renderOrphanNote() {
  const note = document.getElementById("orphan-result-note");
  if (!note) return;
  if (!orphanScanned) {
    note.textContent = "";
    return;
  }
  const library = orphanMediaType === "tv" ? "TV" : "Movies";
  note.textContent = `${library}. A folder is listed only when it is missing from both ${managerLabel(orphanMediaType)} and Plex.`;
}

function renderOrphanCandidates() {
  if (!orphanCandidatesEl) return;
  if (!orphanScanned) {
    orphanCandidatesEl.innerHTML = `<div class="empty-state"><strong>No orphan scan yet</strong><p>Choose Movies or TV, then run Orphan folders. A folder is listed only when it is missing from both the manager app and Plex.</p></div>`;
    return;
  }
  if (!orphanCandidates.length) {
    const manager = managerLabel(orphanMediaType);
    orphanCandidatesEl.innerHTML = `<div class="empty-state"><strong>No orphan folders</strong><p>Every top-level folder is in ${escapeHtml(manager)} or in Plex.</p></div>`;
    return;
  }
  orphanCandidatesEl.innerHTML = orphanCandidates
    .map((row) => {
      const checked = orphanSelected.has(row.name) ? " checked" : "";
      return `<div class="appdata-row" role="listitem">
        <label class="checkbox-label appdata-check">
          <input type="checkbox" class="orphan-check" data-name="${escapeHtml(row.name)}"${checked} />
          <span class="appdata-name">${escapeHtml(row.name)}</span>
        </label>
        <span class="appdata-size">${escapeHtml(humanSize(row.size_bytes))}</span>
      </div>`;
    })
    .join("");
}

function renderLooseFiles() {
  const wrap = document.getElementById("orphan-loose-wrap");
  const list = document.getElementById("orphan-loose");
  if (!wrap || !list) return;
  if (!orphanLoose.length) {
    wrap.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  wrap.classList.remove("hidden");
  list.innerHTML = orphanLoose
    .map(
      (name) => `<div class="appdata-row" role="listitem">
        <span class="appdata-name">${escapeHtml(name)}</span>
      </div>`
    )
    .join("");
}

function renderOrphanQuarantine() {
  if (!orphanQuarantineEl) return;
  if (!orphanQuarantine.length) {
    orphanQuarantineEl.innerHTML = `<div class="empty-state"><strong>No orphan folders in quarantine</strong><p>Quarantine from the orphan scan keeps folders here. Duplicate-file quarantine is separate and is not purged here.</p></div>`;
    return;
  }
  orphanQuarantineEl.innerHTML = orphanQuarantine
    .map((row) => {
      const checked = orphanQuarantineSelected.has(row.name) ? " checked" : "";
      return `<div class="appdata-row" role="listitem">
        <label class="checkbox-label appdata-check">
          <input type="checkbox" class="orphan-quarantine-check" data-name="${escapeHtml(row.name)}"${checked} />
          <span class="appdata-name">${escapeHtml(folderLabel(row))}</span>
        </label>
        <span class="appdata-size">${escapeHtml(humanSize(row.size_bytes))}</span>
      </div>`;
    })
    .join("");
}

function asOrphanCandidate(row) {
  if (!row || typeof row !== "object") return null;
  const name = String(row.name ?? "");
  if (!name) return null;
  const size = Number(row.size_bytes);
  return { name, size_bytes: Number.isFinite(size) && size >= 0 ? size : 0 };
}

function looseName(entry) {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object" && entry.name != null) return String(entry.name);
  return "";
}

function compareBySize(a, b) {
  const left = a.size_bytes == null ? -1 : a.size_bytes;
  const right = b.size_bytes == null ? -1 : b.size_bytes;
  if (right !== left) return right - left;
  return String(a.name).localeCompare(String(b.name));
}

function applyOrphanResult(result, mediaType) {
  const rows = result && Array.isArray(result.candidates) ? result.candidates : null;
  const loose = result && Array.isArray(result.loose_files) ? result.loose_files : null;
  if (!rows || !loose) throw new Error("Orphan scan result could not be read.");
  orphanMediaType = mediaType;
  orphanScanned = true;
  orphanCandidates = rows.map(asOrphanCandidate).filter(Boolean).sort(compareBySize);
  orphanLoose = loose.map(looseName).filter((name) => name);
  orphanSelected.clear();
  renderOrphanNote();
  renderOrphanCandidates();
  renderLooseFiles();
  updateOrphanButtons();
}

function orphanQuarantineRows(payload) {
  const list = Array.isArray(payload)
    ? payload
    : payload && Array.isArray(payload.entries)
      ? payload.entries
      : payload && Array.isArray(payload.items)
        ? payload.items
        : payload && Array.isArray(payload.folders)
          ? payload.folders
          : null;
  if (!list) return null;
  return list
    .map((row) => {
      if (typeof row === "string") return { name: row, original_name: row, size_bytes: null };
      if (!row || typeof row !== "object") return null;
      const name = String(row.name ?? "");
      if (!name) return null;
      const original = String(row.original_name ?? "");
      const raw = row.size_bytes;
      const size = Number(raw);
      return {
        name,
        original_name: original || name,
        size_bytes: raw == null || raw === "" || !Number.isFinite(size) || size < 0 ? null : size,
      };
    })
    .filter(Boolean)
    .sort(compareBySize);
}

function folderLabel(row) {
  return row.original_name || row.name;
}

function collectErrors(result) {
  const errors = [];
  const failed = new Set();
  const list = result && Array.isArray(result.errors) ? result.errors : [];
  for (const item of list) {
    if (typeof item === "string") {
      errors.push(oneLine(item));
      continue;
    }
    if (!item || typeof item !== "object") continue;
    const name = item.name != null ? String(item.name) : "";
    const message = oneLine(item.error || item.message || "failed");
    if (name) failed.add(name);
    errors.push(name ? `${oneLine(name)}: ${message}` : message);
  }
  return { errors, failed };
}

function dropOrphanCandidates(names) {
  const gone = new Set(names);
  orphanCandidates = orphanCandidates.filter((row) => !gone.has(row.name));
  for (const name of names) orphanSelected.delete(name);
  renderOrphanCandidates();
}

async function pollOrphanScan(jobId) {
  for (;;) {
    const data = await api(`/api/media/orphans/scan/${encodeURIComponent(jobId)}`);
    if (data.status === "failed") throw new Error(data.error || "Orphan scan failed.");
    if (data.status === "completed") return data.result;
    setToast(orphanStatus, "Scanning orphan folders…", "loading");
    await delay(2000);
  }
}

async function startOrphanScan() {
  if (orphanBusy || orphanScanning) return;
  const mediaType = document.getElementById("scan-media-type").value;
  orphanScanning = true;
  updateOrphanButtons();
  setOrphanScanLabel("Scanning…");
  setToast(orphanStatus, "Scanning orphan folders…", "loading");
  try {
    const payload = await api("/api/media/orphans/scan", {
      method: "POST",
      body: JSON.stringify({ media_type: mediaType }),
    });
    const jobId = payload && payload.job_id;
    if (!jobId) throw new Error("Orphan scan did not return a job id.");
    const result = await pollOrphanScan(String(jobId));
    applyOrphanResult(result, mediaType);
    const count = orphanCandidates.length;
    const loose = orphanLoose.length;
    let message = count === 1 ? "Found 1 orphan folder." : `Found ${count} orphan folders.`;
    if (loose === 1) message += " 1 loose file stays in place.";
    else if (loose) message += ` ${loose} loose files stay in place.`;
    setToast(orphanStatus, message, "ok");
  } catch (error) {
    setToast(orphanStatus, error.message || "Orphan scan failed.", "error");
  } finally {
    orphanScanning = false;
    setOrphanScanLabel("Orphan folders");
    updateOrphanButtons();
  }
}

async function loadOrphanQuarantine() {
  const payload = await api("/api/media/orphans/quarantine");
  const rows = orphanQuarantineRows(payload);
  if (!rows) throw new Error("Orphan quarantine list could not be read.");
  orphanQuarantine = rows;
  const present = new Set(orphanQuarantine.map((row) => row.name));
  for (const name of [...orphanQuarantineSelected]) {
    if (!present.has(name)) orphanQuarantineSelected.delete(name);
  }
  renderOrphanQuarantine();
  updateOrphanButtons();
}

async function refreshOrphanQuarantine() {
  setToast(orphanQuarantineStatus, "Loading orphan quarantine…", "loading");
  try {
    await loadOrphanQuarantine();
    setToast(orphanQuarantineStatus, "", "");
  } catch (error) {
    orphanQuarantine = [];
    orphanQuarantineSelected.clear();
    if (orphanQuarantineEl) {
      orphanQuarantineEl.innerHTML = `<div class="empty-state" role="alert"><strong>Orphan quarantine unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
    setToast(orphanQuarantineStatus, error.message || "Orphan quarantine list failed.", "error");
    updateOrphanButtons();
  }
}

async function quarantineOrphanFolders() {
  if (orphanBusy || orphanScanning) return;
  const rows = selectedOrphanRows();
  if (!rows.length || !orphanMediaType) return;
  const names = rows.map((row) => row.name);
  if (!window.confirm(`Move these folders to quarantine?\n\n${bullet(names)}`)) return;
  orphanBusy = true;
  updateOrphanButtons();
  setActionLabel("orphan-quarantine", "Quarantining…");
  setToast(orphanStatus, "Quarantining…", "loading");
  try {
    const result = await api("/api/media/orphans/quarantine", {
      method: "POST",
      body: JSON.stringify({ media_type: orphanMediaType, names }),
    });
    const { errors, failed } = collectErrors(result);
    if (errors.length && failed.size) dropOrphanCandidates(names.filter((name) => !failed.has(name)));
    else if (!errors.length) dropOrphanCandidates(names);
    let refreshError = "";
    try {
      await loadOrphanQuarantine();
    } catch (error) {
      refreshError = error.message || "Orphan quarantine list failed to refresh.";
    }
    const count = errors.length && failed.size ? names.length - failed.size : names.length;
    const outcome = `Quarantined ${count} folder${count === 1 ? "" : "s"}.`;
    if (errors.length) setToast(orphanStatus, errors.join(" "), "error");
    else if (refreshError) setToast(orphanStatus, `${outcome} ${refreshError}`, "error");
    else setToast(orphanStatus, outcome, "ok");
  } catch (error) {
    setToast(orphanStatus, error.message || "Quarantine failed.", "error");
    try {
      await loadOrphanQuarantine();
    } catch {
      /* the quarantine error stays visible */
    }
  } finally {
    orphanBusy = false;
    setActionLabel("orphan-quarantine", "Quarantine");
    updateOrphanButtons();
  }
}

async function restoreOrphanFolders() {
  if (orphanBusy) return;
  const rows = selectedOrphanQuarantineRows();
  if (!rows.length) return;
  const names = rows.map((row) => row.name);
  if (
    !window.confirm(
      `Move these folders back to the library?\n\n${bullet(rows.map(folderLabel))}\n\nIf the original name is already there, that folder stays in quarantine.`
    )
  ) {
    return;
  }
  orphanBusy = true;
  updateOrphanButtons();
  setActionLabel("orphan-restore", "Restoring…");
  setToast(orphanQuarantineStatus, "Restoring…", "loading");
  try {
    const result = await api("/api/media/orphans/restore", {
      method: "POST",
      body: JSON.stringify({ names }),
    });
    const { errors } = collectErrors(result);
    const restored = Array.isArray(result && result.restored) ? result.restored.length : names.length;
    let refreshError = "";
    try {
      await loadOrphanQuarantine();
    } catch (error) {
      refreshError = error.message || "Orphan quarantine list failed to refresh.";
    }
    const outcome = `Restored ${restored} folder${restored === 1 ? "" : "s"}.`;
    if (errors.length) setToast(orphanQuarantineStatus, errors.join(" "), "error");
    else if (refreshError) setToast(orphanQuarantineStatus, `${outcome} ${refreshError}`, "error");
    else setToast(orphanQuarantineStatus, outcome, "ok");
  } catch (error) {
    setToast(orphanQuarantineStatus, error.message || "Restore failed.", "error");
    try {
      await loadOrphanQuarantine();
    } catch {
      /* the restore error stays visible */
    }
  } finally {
    orphanBusy = false;
    setActionLabel("orphan-restore", "Restore");
    updateOrphanButtons();
  }
}

async function purgeOrphanFolders() {
  if (orphanBusy) return;
  const rows = selectedOrphanQuarantineRows();
  if (!rows.length) return;
  const lines = rows
    .map((row) => `• ${oneLine(folderLabel(row))} (${humanSize(row.size_bytes)})`)
    .join("\n");
  if (
    !window.confirm(
      `Permanently delete these orphan folders? This cannot be undone.\n\n${lines}\n\nDuplicate-file quarantine is not deleted.`
    )
  ) {
    return;
  }
  orphanBusy = true;
  updateOrphanButtons();
  setActionLabel("orphan-purge", "Purging…");
  setToast(orphanQuarantineStatus, "Purging…", "loading");
  try {
    const result = await api("/api/media/orphans/purge", {
      method: "POST",
      body: JSON.stringify({ names: rows.map((row) => row.name) }),
    });
    const { errors } = collectErrors(result);
    let refreshError = "";
    try {
      await loadOrphanQuarantine();
    } catch (error) {
      refreshError = error.message || "Orphan quarantine list failed to refresh.";
    }
    const count = rows.length;
    const outcome = `Purged ${count} folder${count === 1 ? "" : "s"}.`;
    if (errors.length) setToast(orphanQuarantineStatus, errors.join(" "), "error");
    else if (refreshError) setToast(orphanQuarantineStatus, `${outcome} ${refreshError}`, "error");
    else setToast(orphanQuarantineStatus, outcome, "ok");
  } catch (error) {
    setToast(orphanQuarantineStatus, error.message || "Purge failed.", "error");
    try {
      await loadOrphanQuarantine();
    } catch {
      /* the purge error stays visible */
    }
  } finally {
    orphanBusy = false;
    setActionLabel("orphan-purge", "Purge");
    updateOrphanButtons();
  }
}

function selectAllOrphans() {
  orphanSelected.clear();
  for (const row of orphanCandidates) orphanSelected.add(row.name);
  renderOrphanCandidates();
  updateOrphanButtons();
}

function selectNoneOrphans() {
  orphanSelected.clear();
  renderOrphanCandidates();
  updateOrphanButtons();
}

function selectAllOrphanQuarantine() {
  orphanQuarantineSelected.clear();
  for (const row of orphanQuarantine) orphanQuarantineSelected.add(row.name);
  renderOrphanQuarantine();
  updateOrphanButtons();
}

function selectNoneOrphanQuarantine() {
  orphanQuarantineSelected.clear();
  renderOrphanQuarantine();
  updateOrphanButtons();
}

async function bootstrap() {
  const wizardEl = document.getElementById("wizard-root");
  const dashboardEl = document.getElementById("dashboard");
  if (!wizardEl || !dashboardEl) {
    throw new Error("Page layout is missing required elements.");
  }

  initHeaderNav();
  bindSetupWizardButtons();

  const status = await api("/api/setup/status");
  if (!status.onboarding_complete) {
    wizardEl.classList.remove("hidden");
    dashboardEl.classList.add("hidden");
    if (window.initWizard) await window.initWizard();
    return;
  }

  wizardEl.classList.add("hidden");
  dashboardEl.classList.remove("hidden");
  loadHealth();
  loadSetupHealth();
  renderOrphanCandidates();
  updateOrphanButtons();
  loadJobs().catch(() => {});
  loadReports().catch(() => {});
  loadManifests().catch(() => {});
  loadOrphanQuarantine().catch((error) => {
    if (orphanQuarantineEl) {
      orphanQuarantineEl.innerHTML = `<div class="empty-state" role="alert"><strong>Orphan quarantine unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
    setToast(orphanQuarantineStatus, error.message || "Orphan quarantine list failed.", "error");
    updateOrphanButtons();
  });
  hasActiveJob().then((active) => {
    if (active) startPolling();
  });
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

document.getElementById("refresh-jobs")?.addEventListener("click", loadJobs);
document.getElementById("refresh-reports")?.addEventListener("click", loadReports);
document.getElementById("refresh-manifests")?.addEventListener("click", loadManifests);
document.querySelectorAll(".scan-btn").forEach((button) => {
  button.addEventListener("click", () => startScan(button.dataset.mode));
});
document.getElementById("orphan-scan")?.addEventListener("click", () => {
  startOrphanScan();
});
document.getElementById("orphan-select-all")?.addEventListener("click", selectAllOrphans);
document.getElementById("orphan-select-none")?.addEventListener("click", selectNoneOrphans);
document.getElementById("orphan-quarantine")?.addEventListener("click", () => {
  quarantineOrphanFolders();
});
document.getElementById("orphan-quarantine-select-all")?.addEventListener("click", selectAllOrphanQuarantine);
document.getElementById("orphan-quarantine-select-none")?.addEventListener("click", selectNoneOrphanQuarantine);
document.getElementById("orphan-restore")?.addEventListener("click", () => {
  restoreOrphanFolders();
});
document.getElementById("orphan-purge")?.addEventListener("click", () => {
  purgeOrphanFolders();
});
document.getElementById("refresh-orphan-quarantine")?.addEventListener("click", () => {
  refreshOrphanQuarantine();
});
orphanCandidatesEl?.addEventListener("change", (event) => {
  const box = event.target.closest(".orphan-check");
  if (!box) return;
  if (box.checked) orphanSelected.add(box.dataset.name);
  else orphanSelected.delete(box.dataset.name);
  updateOrphanButtons();
});
orphanQuarantineEl?.addEventListener("change", (event) => {
  const box = event.target.closest(".orphan-quarantine-check");
  if (!box) return;
  if (box.checked) orphanQuarantineSelected.add(box.dataset.name);
  else orphanQuarantineSelected.delete(box.dataset.name);
  updateOrphanButtons();
});
document.querySelectorAll("[data-report-tab]").forEach((tab) => {
  tab.addEventListener("click", async () => {
    setReportTab(tab.dataset.reportTab);
    if (activeReportName) {
      if (tab.dataset.reportTab === "json" && cachedRawReport) {
        renderJsonPanel(reportJsonEl, cachedRawReport);
        reportJsonEl.classList.remove("hidden");
        reportGridEl.classList.add("hidden");
      } else if (tab.dataset.reportTab === "grid") {
        await loadReportGrid(activeReportName);
        reportGridEl.classList.remove("hidden");
        reportJsonEl.classList.add("hidden");
      } else if (tab.dataset.reportTab === "json") {
        await viewReport(activeReportName);
      }
    }
  });
});

bootstrap().catch((error) => {
  showBootstrapError(error);
  document.getElementById("dashboard")?.classList.remove("hidden");
});
