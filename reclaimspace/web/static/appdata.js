/** Appdata: unused folders, code migrate, quarantine, delete, archive. */

const scanStatus = document.getElementById("appdata-status");
const archiveStatus = document.getElementById("archive-status");
const candidateList = document.getElementById("candidate-list");
const inUseList = document.getElementById("in-use-list");
const archiveList = document.getElementById("archive-list");
const summaryEl = document.getElementById("appdata-summary");
const scanButton = document.getElementById("scan-appdata");
const scanLabel = document.getElementById("scan-appdata-label");

let scanState = "idle";
let scanError = "";
let scanning = false;
let busy = false;
let candidates = [];
let inUse = [];
let archive = [];
const selectedCandidateNames = new Set();
const selectedArchiveNames = new Set();
const openExplore = new Map();

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function oneLine(value) {
  return String(value ?? "").replace(/[\r\n\u2028\u2029]+/g, " ");
}

function humanSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "—";
  return formatBytes(value);
}

function evidenceText(evidence) {
  if (evidence == null || evidence === "") return "";
  if (Array.isArray(evidence)) {
    return evidence.map((item) => oneLine(item)).filter((item) => item.trim()).join(", ");
  }
  if (typeof evidence === "object") {
    return Object.entries(evidence)
      .map(([key, value]) => `${oneLine(key)}: ${oneLine(value)}`)
      .join(", ");
  }
  return oneLine(evidence);
}

function containerText(containers) {
  const list = Array.isArray(containers) ? containers : containers ? [containers] : [];
  return list
    .map((item) => {
      if (item && typeof item === "object") return oneLine(item.name || item.id || "");
      return oneLine(item);
    })
    .filter((item) => item.trim())
    .join(", ");
}

function asSize(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : 0;
}

function asCandidate(row) {
  return {
    name: String((row && row.name) || ""),
    size_bytes: asSize(row && row.size_bytes),
    is_code: Boolean(row && row.is_code),
    evidence: row ? row.evidence : "",
  };
}

function asInUse(row) {
  return {
    name: String((row && row.name) || ""),
    containers: row ? row.containers : [],
  };
}

function asArchive(row) {
  const name = String((row && row.name) || "");
  return {
    name,
    size_bytes: asSize(row && row.size_bytes),
    original_name: String((row && (row.original_name || row.name)) || ""),
  };
}

function asEntry(entry) {
  if (typeof entry === "string") return { name: entry, is_dir: false, size_bytes: null };
  const name = String((entry && entry.name) || "");
  const isDir = Boolean(
    entry && (entry.is_dir === true || entry.type === "dir" || entry.type === "directory")
  );
  const rawSize = entry ? entry.size_bytes : null;
  return {
    name,
    is_dir: isDir,
    size_bytes: rawSize == null || rawSize === "" ? null : asSize(rawSize),
  };
}

function browseEntries(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.entries)) return payload.entries;
  if (payload && Array.isArray(payload.children)) return payload.children;
  return null;
}

function archiveRows(payload) {
  const list = Array.isArray(payload)
    ? payload
    : payload && Array.isArray(payload.entries)
      ? payload.entries
      : payload && Array.isArray(payload.items)
        ? payload.items
        : null;
  if (!list) return null;
  return list.map(asArchive).filter((row) => row.name);
}

function safeSegment(part) {
  return Boolean(part) && part !== "." && part !== ".." && !/[\\/\0]/.test(part);
}

function safePath(path) {
  const parts = String(path || "").split("/");
  if (!parts.length || parts.some((part) => !safeSegment(part))) return null;
  return parts.join("/");
}

function bullet(names) {
  return names.map((name) => `• ${oneLine(name)}`).join("\n");
}

function selectedCandidateRows() {
  return candidates.filter((row) => selectedCandidateNames.has(row.name));
}

function selectedArchiveRows() {
  return archive.filter((row) => selectedArchiveNames.has(row.name));
}

function updateButtons() {
  const selected = selectedCandidateRows();
  const code = selected.filter((row) => row.is_code);
  const locked = busy || scanning;
  const migrate = document.getElementById("migrate-selected");
  const quarantine = document.getElementById("quarantine-selected");
  const remove = document.getElementById("delete-selected");
  const empty = document.getElementById("remove-empty");
  const selectAll = document.getElementById("select-all-candidates");
  const selectNone = document.getElementById("select-none-candidates");
  if (migrate) migrate.disabled = locked || code.length === 0;
  if (quarantine) quarantine.disabled = locked || selected.length === 0;
  if (remove) remove.disabled = locked || selected.length === 0;
  if (empty) empty.disabled = locked;
  if (selectAll) selectAll.disabled = scanState !== "ready" || candidates.length === 0;
  if (selectNone) selectNone.disabled = selectedCandidateNames.size === 0;

  const archiveSelected = selectedArchiveRows();
  const archiveAll = document.getElementById("select-all-archive");
  const archiveNone = document.getElementById("select-none-archive");
  const restore = document.getElementById("restore-selected");
  const purge = document.getElementById("purge-selected");
  if (archiveAll) archiveAll.disabled = archive.length === 0 || busy;
  if (archiveNone) archiveNone.disabled = selectedArchiveNames.size === 0;
  if (restore) restore.disabled = busy || archiveSelected.length === 0;
  if (purge) purge.disabled = busy || archiveSelected.length === 0;
}

function renderSummary() {
  if (!summaryEl) return;
  if (scanState !== "ready") {
    summaryEl.classList.add("hidden");
    summaryEl.innerHTML = "";
    return;
  }
  const total = candidates.reduce((sum, row) => sum + row.size_bytes, 0);
  const code = candidates.filter((row) => row.is_code).length;
  summaryEl.classList.remove("hidden");
  summaryEl.innerHTML = `
    <div class="stat-chip highlight"><strong>${candidates.length}</strong><span>Unused</span></div>
    <div class="stat-chip"><strong>${escapeHtml(humanSize(total))}</strong><span>Unused size</span></div>
    <div class="stat-chip"><strong>${code}</strong><span>Code</span></div>
    <div class="stat-chip"><strong>${inUse.length}</strong><span>In use</span></div>`;
}

function renderBrowseList(rootName, session) {
  if (!session.entries.length) return `<p class="job-meta">Empty folder.</p>`;
  const items = session.entries
    .map((entry) => {
      const size =
        entry.is_dir || entry.size_bytes == null ? "" : escapeHtml(humanSize(entry.size_bytes));
      if (entry.is_dir && safeSegment(entry.name)) {
        return `<li>
          <button type="button" class="appdata-entry" data-browse-root="${escapeHtml(rootName)}" data-browse-dir="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}/</button>
          <span class="appdata-size">${size}</span>
        </li>`;
      }
      return `<li>
        <span class="appdata-file">${escapeHtml(entry.name)}</span>
        <span class="appdata-size">${size}</span>
      </li>`;
    })
    .join("");
  return `<ul class="appdata-browse">${items}</ul>`;
}

function renderExplore(row, session) {
  const evidence = row.is_code ? evidenceText(row.evidence) : "";
  const evidenceHtml = row.is_code
    ? `<p class="appdata-evidence"><span class="field-label">Evidence</span> ${escapeHtml(evidence || "—")}</p>`
    : "";
  let body = `<p class="job-meta">Loading…</p>`;
  if (!session.loading && session.error) {
    body = `<p class="appdata-browse-error">${escapeHtml(session.error)}</p>`;
  } else if (!session.loading) {
    body = renderBrowseList(row.name, session);
  }
  const up =
    session.path !== row.name
      ? `<button type="button" class="btn ghost btn-sm browse-up" data-browse-up="${escapeHtml(row.name)}">Up</button>`
      : "";
  return `<div class="appdata-detail">
    ${evidenceHtml}
    <div class="appdata-browse-bar">${up}<code>${escapeHtml(session.path)}</code></div>
    ${body}
  </div>`;
}

function renderCandidate(row) {
  const open = openExplore.get(row.name);
  const checked = selectedCandidateNames.has(row.name) ? " checked" : "";
  const badge = row.is_code ? `<span class="badge badge-code">Code</span>` : "";
  return `<div class="appdata-item" role="listitem">
    <div class="appdata-row${open ? " open" : ""}">
      <label class="checkbox-label appdata-check">
        <input type="checkbox" class="candidate-check" data-name="${escapeHtml(row.name)}"${checked} />
        <span class="appdata-name">${escapeHtml(row.name)}</span>
      </label>
      <span class="appdata-size">${escapeHtml(humanSize(row.size_bytes))}</span>
      ${badge}
      <button type="button" class="btn ghost btn-sm explore-btn" data-explore="${escapeHtml(row.name)}" aria-expanded="${open ? "true" : "false"}">${open ? "Hide" : "Explore"}</button>
    </div>
    ${open ? renderExplore(row, open) : ""}
  </div>`;
}

function renderCandidates() {
  if (!candidateList) return;
  if (scanState === "scanning") {
    candidateList.innerHTML = `<div class="empty-state"><strong>Scanning…</strong><p>Folders are not listed until the scan finishes.</p></div>`;
    return;
  }
  if (scanState === "failed") {
    candidateList.innerHTML = `<div class="empty-state" role="alert"><strong>Scan failed</strong><p>${escapeHtml(scanError)}</p></div>`;
    return;
  }
  if (scanState !== "ready") {
    candidateList.innerHTML = `<div class="empty-state"><strong>No scan yet</strong><p>Scan appdata before treating any folder as unused.</p></div>`;
    return;
  }
  if (!candidates.length) {
    candidateList.innerHTML = `<div class="empty-state"><strong>No unused folders</strong><p>Every top-level folder is mounted, archived, or the share is empty.</p></div>`;
    return;
  }
  candidateList.innerHTML = candidates.map(renderCandidate).join("");
}

function renderInUseRow(row) {
  const containers = containerText(row.containers);
  return `<div class="appdata-row is-in-use" role="listitem">
    <span class="appdata-name">${escapeHtml(row.name)}</span>
    <span class="appdata-containers">${containers ? escapeHtml(containers) : "Mounted"}</span>
  </div>`;
}

function renderInUse() {
  if (!inUseList) return;
  if (scanState === "failed") {
    inUseList.innerHTML = `<div class="empty-state"><strong>Not listed</strong><p>Container mounts stay hidden until a scan can read them.</p></div>`;
    return;
  }
  if (scanState === "scanning") {
    inUseList.innerHTML = `<div class="empty-state"><strong>Scanning…</strong><p>In-use folders appear when the scan finishes.</p></div>`;
    return;
  }
  if (scanState !== "ready") {
    inUseList.innerHTML = `<div class="empty-state"><strong>No scan yet</strong><p>In-use folders appear after a scan reads container mounts.</p></div>`;
    return;
  }
  if (!inUse.length) {
    inUseList.innerHTML = `<div class="empty-state"><strong>None in use</strong><p>No container bind-mounts a top-level appdata folder.</p></div>`;
    return;
  }
  inUseList.innerHTML = inUse.map(renderInUseRow).join("");
}

function renderArchive() {
  if (!archiveList) return;
  if (!archive.length) {
    archiveList.innerHTML = `<div class="empty-state"><strong>Nothing in _archive</strong><p>Quarantine moves folders here.</p></div>`;
    return;
  }
  archiveList.innerHTML = archive
    .map((row) => {
      const checked = selectedArchiveNames.has(row.name) ? " checked" : "";
      const from =
        row.original_name && row.original_name !== row.name
          ? ` <span class="text-muted">from ${escapeHtml(row.original_name)}</span>`
          : "";
      return `<div class="appdata-row" role="listitem">
        <label class="checkbox-label appdata-check">
          <input type="checkbox" class="archive-check" data-name="${escapeHtml(row.name)}"${checked} />
          <span class="appdata-name">${escapeHtml(row.name)}${from}</span>
        </label>
        <span class="appdata-size">${escapeHtml(humanSize(row.size_bytes))}</span>
      </div>`;
    })
    .join("");
}

function failScan(message) {
  const text = String(message || "Scan failed.");
  scanState = "failed";
  scanError = /not listed as unused/i.test(text) ? text : `${text} Folders are not listed as unused.`;
  candidates = [];
  inUse = [];
  selectedCandidateNames.clear();
  openExplore.clear();
  renderSummary();
  renderCandidates();
  renderInUse();
  setToast(scanStatus, scanError, "error");
  updateButtons();
}

function applyScanResult(result, options) {
  if (!result || !Array.isArray(result.candidates) || !Array.isArray(result.in_use)) {
    throw new Error("Scan finished without a folder list.");
  }
  const quiet = Boolean(options && options.quiet);
  scanState = "ready";
  scanError = "";
  candidates = result.candidates.map(asCandidate).filter((row) => row.name);
  candidates.sort((a, b) => b.size_bytes - a.size_bytes || a.name.localeCompare(b.name));
  inUse = result.in_use.map(asInUse).filter((row) => row.name);
  selectedCandidateNames.clear();
  openExplore.clear();
  renderSummary();
  renderCandidates();
  renderInUse();
  if (!quiet) {
    setToast(scanStatus, `Scan complete. ${candidates.length} unused, ${inUse.length} in use.`, "ok");
  }
  updateButtons();
}

function isFailedStatus(data) {
  const status = String((data && data.status) || "").toLowerCase();
  if (status === "failed" || status === "error") return true;
  if (data && data.error) {
    if (status === "queued" || status === "running") return false;
    return true;
  }
  return false;
}

function isDoneStatus(data) {
  const status = String((data && data.status) || "").toLowerCase();
  return status === "completed" || status === "complete" || status === "succeeded" || status === "success";
}

async function pollScan(jobId) {
  for (;;) {
    const data = await api(`/api/appdata/scan/${encodeURIComponent(jobId)}`);
    if (isFailedStatus(data)) {
      throw new Error(String((data && data.error) || "Scan failed."));
    }
    if (isDoneStatus(data)) {
      applyScanResult(data && data.result);
      return;
    }
    const progress = data && data.progress;
    const message = progress && (progress.message || progress.phase);
    setToast(scanStatus, message ? String(message) : "Scanning appdata…", "loading");
    await delay(2000);
  }
}

async function startScan() {
  if (scanning || busy) return;
  scanning = true;
  scanState = "scanning";
  scanError = "";
  candidates = [];
  inUse = [];
  selectedCandidateNames.clear();
  openExplore.clear();
  renderSummary();
  renderCandidates();
  renderInUse();
  updateButtons();
  if (scanButton) scanButton.disabled = true;
  if (scanLabel) scanLabel.textContent = "Scanning…";
  setToast(scanStatus, "Scanning appdata…", "loading");
  try {
    const payload = await api("/api/appdata/scan", { method: "POST", body: "{}" });
    const jobId = payload && (payload.job_id || payload.id);
    if (!jobId) throw new Error("Scan did not return a job id.");
    await pollScan(String(jobId));
  } catch (error) {
    failScan(error.message || "Scan failed.");
  } finally {
    scanning = false;
    if (scanButton) scanButton.disabled = false;
    if (scanLabel) scanLabel.textContent = "Scan";
    updateButtons();
  }
}

async function loadBrowse(rootName, path) {
  const session = openExplore.get(rootName);
  const safe = safePath(path);
  if (!session || session.path !== path) return;
  if (!safe || safe.split("/")[0] !== rootName) {
    session.loading = false;
    session.error = "That path stays closed.";
    session.entries = [];
    renderCandidates();
    return;
  }
  try {
    const payload = await api(`/api/appdata/browse?path=${encodeURIComponent(safe)}`);
    const current = openExplore.get(rootName);
    if (!current || current.path !== path) return;
    const entries = browseEntries(payload);
    current.loading = false;
    if (!entries) {
      current.error = "Could not read this folder.";
      current.entries = [];
    } else {
      current.error = "";
      current.entries = entries.map(asEntry).filter((entry) => entry.name);
    }
  } catch (error) {
    const current = openExplore.get(rootName);
    if (!current || current.path !== path) return;
    current.loading = false;
    current.error = error.message || "Could not read this folder.";
    current.entries = [];
  }
  renderCandidates();
}

function toggleExplore(rootName) {
  if (openExplore.has(rootName)) {
    openExplore.delete(rootName);
    renderCandidates();
    return;
  }
  if (!safeSegment(rootName)) {
    openExplore.set(rootName, {
      path: rootName,
      loading: false,
      error: "That folder name cannot be opened.",
      entries: [],
    });
    renderCandidates();
    return;
  }
  openExplore.set(rootName, { path: rootName, loading: true, error: "", entries: [] });
  renderCandidates();
  loadBrowse(rootName, rootName);
}

function openChild(rootName, childName) {
  const session = openExplore.get(rootName);
  if (!session || session.loading) return;
  const next = safePath(`${session.path}/${childName}`);
  if (!next || next.split("/")[0] !== rootName) {
    session.error = "That path stays closed.";
    renderCandidates();
    return;
  }
  session.path = next;
  session.loading = true;
  session.error = "";
  session.entries = [];
  renderCandidates();
  loadBrowse(rootName, next);
}

function browseUp(rootName) {
  const session = openExplore.get(rootName);
  if (!session || session.loading) return;
  const parts = session.path.split("/");
  if (parts.length <= 1) return;
  parts.pop();
  const next = parts.join("/");
  if (next.split("/")[0] !== rootName) return;
  session.path = next;
  session.loading = true;
  session.error = "";
  session.entries = [];
  renderCandidates();
  loadBrowse(rootName, next);
}

function collectErrors(result) {
  const errors = [];
  const failed = new Set();
  if (!result || typeof result !== "object") return { errors, failed };
  if (Array.isArray(result.results)) {
    for (const row of result.results) {
      if (!row || row.ok !== false) continue;
      const name = row.name ? String(row.name) : "";
      if (name) failed.add(name);
      errors.push(name && row.error ? `${name}: ${row.error}` : String(row.error || name || "Action failed."));
    }
  }
  if (Array.isArray(result.errors)) {
    for (const item of result.errors) {
      if (item && typeof item === "object") {
        const name = item.name ? String(item.name) : "";
        if (name) failed.add(name);
        errors.push(name && item.error ? `${name}: ${item.error}` : String(item.error || name || "Action failed."));
      } else if (item) {
        errors.push(String(item));
      }
    }
  }
  if (result.error) errors.push(String(result.error));
  return { errors, failed };
}

function namesFrom(result, keys) {
  if (Array.isArray(result)) {
    return result
      .map((item) => (typeof item === "string" ? item : item && item.name))
      .filter(Boolean)
      .map(String);
  }
  if (!result || typeof result !== "object") return null;
  for (const key of keys) {
    if (!Array.isArray(result[key])) continue;
    return result[key]
      .map((item) => (typeof item === "string" ? item : item && item.name))
      .filter(Boolean)
      .map(String);
  }
  return null;
}

function dropCandidates(names) {
  const gone = new Set(names);
  candidates = candidates.filter((row) => !gone.has(row.name));
  for (const name of names) {
    selectedCandidateNames.delete(name);
    openExplore.delete(name);
  }
  renderSummary();
  renderCandidates();
}

async function postNames(path, names) {
  return api(path, { method: "POST", body: JSON.stringify({ names }) });
}

async function runCandidateAction(path, names, verb, refreshArchive) {
  busy = true;
  updateButtons();
  setToast(scanStatus, `${verb}…`, "loading");
  try {
    const result = await postNames(path, names);
    const { errors, failed } = collectErrors(result);
    const succeeded = names.filter((name) => !failed.has(name));
    if (!errors.length) dropCandidates(names);
    else if (failed.size) dropCandidates(succeeded);
    if (refreshArchive) {
      try {
        await loadArchive();
      } catch (error) {
        errors.push(error.message);
      }
    }
    if (errors.length) {
      const prefix = succeeded.length ? `${verb} ${succeeded.length}. ` : "";
      setToast(scanStatus, `${prefix}${errors.join(" ")}`, "error");
    } else {
      const count = succeeded.length;
      setToast(scanStatus, `${verb} ${count} folder${count === 1 ? "" : "s"}.`, "ok");
    }
  } catch (error) {
    setToast(scanStatus, error.message, "error");
  } finally {
    busy = false;
    updateButtons();
  }
}

async function pollMigrate(jobId) {
  for (;;) {
    const data = await api(`/api/appdata/migrate/${encodeURIComponent(jobId)}`);
    if (!isFailedStatus(data) && !isDoneStatus(data)) {
      const progress = data && data.progress;
      const current = progress && (progress.current || progress.folder);
      const total = progress && progress.total;
      const index = progress && progress.index;
      let message = "Moving…";
      if (current) {
        message = total ? `Moving ${current} (${index} of ${total})…` : `Moving ${current}…`;
      } else if (progress && progress.message) {
        message = String(progress.message);
      }
      setToast(scanStatus, message, "loading");
      await delay(1000);
      continue;
    }
    if (isFailedStatus(data)) {
      const result = data && data.result;
      const collected = collectErrors(result || {});
      const message = collected.errors.length
        ? collected.errors.join(" ")
        : String((data && data.error) || "Migrate failed.");
      const error = new Error(message);
      error.result = result;
      throw error;
    }
    return data && data.result;
  }
}

async function refreshScanInPlace() {
  const payload = await api("/api/appdata/scan", { method: "POST", body: "{}" });
  const jobId = payload && (payload.job_id || payload.id);
  if (!jobId) throw new Error("Scan did not return a job id.");
  for (;;) {
    const data = await api(`/api/appdata/scan/${encodeURIComponent(jobId)}`);
    if (isFailedStatus(data)) throw new Error(String((data && data.error) || "Scan failed."));
    if (isDoneStatus(data)) {
      applyScanResult(data && data.result, { quiet: true });
      return;
    }
    await delay(1000);
  }
}

async function migrateSelected() {
  if (busy || scanning) return;
  const selected = selectedCandidateRows();
  const code = selected.filter((row) => row.is_code);
  if (!code.length) return;
  const blocks = code
    .map((row) => {
      const name = oneLine(row.name);
      const evidence = evidenceText(row.evidence) || "—";
      return [
        name,
        `  source: /appdata/${name}`,
        `  destination: /code/${name}`,
        `  size: ${humanSize(row.size_bytes)}`,
        `  evidence: ${oneLine(evidence)}`,
      ].join("\n");
    })
    .join("\n\n");
  const others = selected.filter((row) => !row.is_code).map((row) => `• ${oneLine(row.name)}`);
  let message = `Move these code folders?\n\n${blocks}`;
  if (others.length) {
    message += `\n\nThese selected folders are not code and will stay:\n${others.join("\n")}`;
  }
  if (!window.confirm(message)) return;
  const names = code.map((row) => row.name);
  busy = true;
  updateButtons();
  setToast(scanStatus, "Moving…", "loading");
  try {
    const payload = await api("/api/appdata/migrate", {
      method: "POST",
      body: JSON.stringify({ names }),
    });
    const jobId = payload && (payload.job_id || payload.id);
    if (!jobId) throw new Error("Migrate did not return a job id.");
    const result = await pollMigrate(String(jobId));
    const { errors, failed } = collectErrors(result);
    const moved = (namesFrom(result, ["migrated"]) || []).filter((name) => !failed.has(name));
    if (moved.length) dropCandidates(moved);
    const notes = [];
    try {
      await loadArchive();
    } catch (error) {
      notes.push(error.message);
    }
    try {
      await refreshScanInPlace();
    } catch (error) {
      notes.push(error.message);
    }
    const movedLabel = moved.length ? moved.join(", ") : names.join(", ");
    if (errors.length) {
      const prefix = moved.length ? `Moved ${moved.join(", ")}. ` : "";
      setToast(scanStatus, `${prefix}${errors.join(" ")}`, "error");
    } else if (notes.length) {
      setToast(scanStatus, `Moved ${movedLabel}. ${notes.join(" ")}`, "error");
    } else {
      setToast(scanStatus, `Moved ${movedLabel}.`, "ok");
    }
  } catch (error) {
    const result = error && error.result;
    if (result) {
      const moved = namesFrom(result, ["migrated"]) || [];
      if (moved.length) dropCandidates(moved);
      try {
        await loadArchive();
      } catch {
        /* the migrate error stays visible */
      }
      try {
        await refreshScanInPlace();
      } catch {
        /* the migrate error stays visible */
      }
    }
    setToast(scanStatus, error.message || "Migrate failed.", "error");
  } finally {
    busy = false;
    updateButtons();
  }
}

async function quarantineSelected() {
  if (busy || scanning) return;
  const names = selectedCandidateRows().map((row) => row.name);
  if (!names.length) return;
  if (!window.confirm(`Move these folders to _archive?\n\n${bullet(names)}`)) return;
  await runCandidateAction("/api/appdata/quarantine", names, "Quarantined", true);
}

async function deleteSelected() {
  if (busy || scanning) return;
  const names = selectedCandidateRows().map((row) => row.name);
  if (!names.length) return;
  if (!window.confirm(`Permanently delete these folders? This cannot be undone.\n\n${bullet(names)}`)) return;
  await runCandidateAction("/api/appdata/delete", names, "Deleted", false);
}

async function removeEmpty() {
  if (busy || scanning) return;
  if (
    !window.confirm(
      "Remove empty top-level appdata folders?\n\nOnly directories with nothing inside are removed. _archive and any folder a container still mounts are skipped."
    )
  ) {
    return;
  }
  busy = true;
  updateButtons();
  setToast(scanStatus, "Removing empty folders…", "loading");
  try {
    const result = await api("/api/appdata/empty", { method: "POST", body: "{}" });
    const { errors, failed } = collectErrors(result);
    const removed = namesFrom(result, ["removed", "names", "deleted", "emptied"]);
    if (removed) dropCandidates(removed.filter((name) => !failed.has(name)));
    if (errors.length) setToast(scanStatus, errors.join(" "), "error");
    else if (removed) {
      setToast(
        scanStatus,
        `Removed ${removed.length} empty folder${removed.length === 1 ? "" : "s"}.`,
        "ok"
      );
    } else {
      setToast(scanStatus, "Removed empty folders.", "ok");
    }
  } catch (error) {
    setToast(scanStatus, error.message, "error");
  } finally {
    busy = false;
    updateButtons();
  }
}

async function loadArchive() {
  const payload = await api("/api/appdata/archive");
  const rows = archiveRows(payload);
  if (!rows) throw new Error("Archive list could not be read.");
  archive = rows;
  const present = new Set(archive.map((row) => row.name));
  for (const name of [...selectedArchiveNames]) {
    if (!present.has(name)) selectedArchiveNames.delete(name);
  }
  renderArchive();
  updateButtons();
}

async function refreshArchive() {
  setToast(archiveStatus, "Loading archive…", "loading");
  try {
    await loadArchive();
    setToast(archiveStatus, "", "");
  } catch (error) {
    archive = [];
    selectedArchiveNames.clear();
    if (archiveList) {
      archiveList.innerHTML = `<div class="empty-state" role="alert"><strong>Archive unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
    setToast(archiveStatus, error.message, "error");
    updateButtons();
  }
}

async function runArchiveAction(path, names, verb) {
  busy = true;
  updateButtons();
  setToast(archiveStatus, `${verb}…`, "loading");
  try {
    const result = await postNames(path, names);
    const { errors } = collectErrors(result);
    let refreshError = "";
    try {
      await loadArchive();
    } catch (error) {
      refreshError = error.message || "Archive list failed to refresh.";
    }
    const count = names.length;
    const outcome = `${verb} ${count} folder${count === 1 ? "" : "s"}.`;
    if (errors.length) setToast(archiveStatus, errors.join(" "), "error");
    else if (refreshError) setToast(archiveStatus, `${outcome} ${refreshError}`, "error");
    else setToast(archiveStatus, outcome, "ok");
  } catch (error) {
    setToast(archiveStatus, error.message, "error");
  } finally {
    busy = false;
    updateButtons();
  }
}

async function restoreSelected() {
  if (busy) return;
  const names = selectedArchiveRows().map((row) => row.name);
  if (!names.length) return;
  if (
    !window.confirm(
      `Restore these folders to the appdata root?\n\n${bullet(names)}\n\nIf a folder with that name already exists, that restore stops.`
    )
  ) {
    return;
  }
  await runArchiveAction("/api/appdata/restore", names, "Restored");
}

async function purgeSelected() {
  if (busy) return;
  const rows = selectedArchiveRows();
  if (!rows.length) return;
  const lines = rows.map((row) => `• ${oneLine(row.name)} (${humanSize(row.size_bytes)})`).join("\n");
  if (
    !window.confirm(`Permanently delete these archived folders? This cannot be undone.\n\n${lines}`)
  ) {
    return;
  }
  await runArchiveAction(
    "/api/appdata/purge",
    rows.map((row) => row.name),
    "Purged"
  );
}

function selectAllCandidates() {
  selectedCandidateNames.clear();
  for (const row of candidates) selectedCandidateNames.add(row.name);
  renderCandidates();
  updateButtons();
}

function selectNoneCandidates() {
  selectedCandidateNames.clear();
  renderCandidates();
  updateButtons();
}

function selectAllArchive() {
  selectedArchiveNames.clear();
  for (const row of archive) selectedArchiveNames.add(row.name);
  renderArchive();
  updateButtons();
}

function selectNoneArchive() {
  selectedArchiveNames.clear();
  renderArchive();
  updateButtons();
}

function bindAppdata() {
  scanButton?.addEventListener("click", () => {
    startScan();
  });
  document.getElementById("select-all-candidates")?.addEventListener("click", selectAllCandidates);
  document.getElementById("select-none-candidates")?.addEventListener("click", selectNoneCandidates);
  document.getElementById("migrate-selected")?.addEventListener("click", () => {
    migrateSelected();
  });
  document.getElementById("quarantine-selected")?.addEventListener("click", () => {
    quarantineSelected();
  });
  document.getElementById("delete-selected")?.addEventListener("click", () => {
    deleteSelected();
  });
  document.getElementById("remove-empty")?.addEventListener("click", () => {
    removeEmpty();
  });
  document.getElementById("select-all-archive")?.addEventListener("click", selectAllArchive);
  document.getElementById("select-none-archive")?.addEventListener("click", selectNoneArchive);
  document.getElementById("restore-selected")?.addEventListener("click", () => {
    restoreSelected();
  });
  document.getElementById("purge-selected")?.addEventListener("click", () => {
    purgeSelected();
  });
  document.getElementById("refresh-archive")?.addEventListener("click", () => {
    refreshArchive();
  });

  candidateList?.addEventListener("change", (event) => {
    const box = event.target.closest(".candidate-check");
    if (!box) return;
    if (box.checked) selectedCandidateNames.add(box.dataset.name);
    else selectedCandidateNames.delete(box.dataset.name);
    updateButtons();
  });
  candidateList?.addEventListener("click", (event) => {
    const explore = event.target.closest("[data-explore]");
    if (explore) {
      toggleExplore(explore.dataset.explore);
      return;
    }
    const dir = event.target.closest("[data-browse-dir]");
    if (dir) {
      openChild(dir.dataset.browseRoot, dir.dataset.browseDir);
      return;
    }
    const up = event.target.closest("[data-browse-up]");
    if (up) browseUp(up.dataset.browseUp);
  });
  archiveList?.addEventListener("change", (event) => {
    const box = event.target.closest(".archive-check");
    if (!box) return;
    if (box.checked) selectedArchiveNames.add(box.dataset.name);
    else selectedArchiveNames.delete(box.dataset.name);
    updateButtons();
  });
}

function bootstrapAppdata() {
  initHeaderNav();
  bindSetupWizardButtons();
  loadHealth();
  loadSetupHealth();
  bindAppdata();
  renderSummary();
  renderCandidates();
  renderInUse();
  updateButtons();
  refreshArchive();
}

bootstrapAppdata();
