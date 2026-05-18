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
  if (!table.groups?.length) {
    reportGridEl.innerHTML = "<p class='hint'>No groups in this report.</p>";
    return;
  }
  reportGrid.setRows(table.groups);
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
      await loadReportGrid(name);
      reportGridEl.classList.remove("hidden");
    } else {
      cachedRawReport = await api(`/api/reports/${encodeURIComponent(name)}`);
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
  loadJobs().catch(() => {});
  loadReports().catch(() => {});
  loadManifests().catch(() => {});
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
