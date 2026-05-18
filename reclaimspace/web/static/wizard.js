/** First-run setup wizard */

const WIZARD_STEPS = [
  { id: "welcome", title: "Welcome" },
  { id: "paths", title: "Paths" },
  { id: "plex", title: "Plex" },
  { id: "radarr", title: "Radarr" },
  { id: "sonarr", title: "Sonarr" },
  { id: "review", title: "Review" },
  { id: "scan", title: "First scan" },
];

const wizardRoot = document.getElementById("wizard-root");
let wizardStep = 0;
const draft = {
  movies_root: "/media/movies",
  tv_root: "/media/tv",
  quarantine_root: "/quarantine",
  plex_url: "",
  plex_token: "",
  plex_movie_section: "",
  plex_tv_section: "",
  radarr_url: "",
  radarr_api_key: "",
  sonarr_url: "",
  sonarr_api_key: "",
  path_mappings: "",
  tv_path_mappings: "",
};

const stepState = {
  paths: false,
  plex: false,
  radarr: false,
  sonarr: false,
};

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
      /* text */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return null;
  const ct = response.headers.get("content-type") || "";
  if (ct.includes("application/json")) return response.json();
  return response.text();
}

function escapeHtml(v) {
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function resultHtml(result) {
  if (!result) return "";
  const cls = result.ok ? "test-ok" : "test-fail";
  return `<p class="test-result ${cls}">${escapeHtml(result.message || "")}</p>`;
}

function renderStepIndicator() {
  return `<ol class="wizard-steps" aria-label="Setup progress">
    ${WIZARD_STEPS.map(
      (step, index) =>
        `<li class="${index === wizardStep ? "active" : ""} ${index < wizardStep ? "done" : ""}">
          <span class="step-num">${index + 1}</span>
          <span class="step-label">${escapeHtml(step.title)}</span>
        </li>`
    ).join("")}
  </ol>`;
}

function renderWelcome() {
  return `<div class="wizard-panel">
    <h2>Welcome to Reclaimspace</h2>
    <p>Find duplicate movies and TV episodes in Plex, keep the file Radarr or Sonarr manages, and quarantine the rest.</p>
    <ul class="wizard-list">
      <li><strong>Never deletes</strong> — files move to a timestamped quarantine folder with a rollback manifest.</li>
      <li><strong>Dry run first</strong> — review counts before moving anything.</li>
      <li><strong>LAN recommended</strong> — this UI has no login; use Unraid on your network or a reverse proxy with authentication.</li>
    </ul>
  </div>`;
}

function renderPaths() {
  return `<div class="wizard-panel">
    <h2>Library paths</h2>
    <p class="card-subtitle">Paths inside the Docker container (defaults match the Unraid template mounts).</p>
    <label class="field wide"><span class="field-label">Movies root</span>
      <input class="input" id="w-movies-root" value="${escapeHtml(draft.movies_root)}" /></label>
    <label class="field wide"><span class="field-label">TV root</span>
      <input class="input" id="w-tv-root" value="${escapeHtml(draft.tv_root)}" /></label>
    <label class="field wide"><span class="field-label">Quarantine folder</span>
      <input class="input" id="w-quarantine-root" value="${escapeHtml(draft.quarantine_root)}" /></label>
    <button type="button" class="btn secondary" id="w-test-paths">Validate paths</button>
    <div id="w-paths-result"></div>
  </div>`;
}

function renderPlex() {
  return `<div class="wizard-panel">
    <h2>Plex</h2>
    <label class="field wide"><span class="field-label">Server URL</span>
      <input class="input" id="w-plex-url" value="${escapeHtml(draft.plex_url)}" placeholder="http://10.0.0.10:32400" /></label>
    <label class="field wide"><span class="field-label">Token</span>
      <input class="input" id="w-plex-token" type="password" value="${escapeHtml(draft.plex_token)}" /></label>
    <button type="button" class="btn secondary" id="w-test-plex">Test Plex</button>
    <div id="w-plex-result"></div>
    <div id="w-plex-libraries" class="plex-sections hidden"></div>
    <div class="wizard-row">
      <label class="field"><span class="field-label">Movie library key</span>
        <input class="input" id="w-plex-movie-section" value="${escapeHtml(draft.plex_movie_section)}" /></label>
      <label class="field"><span class="field-label">TV library key</span>
        <input class="input" id="w-plex-tv-section" value="${escapeHtml(draft.plex_tv_section)}" /></label>
    </div>
  </div>`;
}

function renderRadarr() {
  return `<div class="wizard-panel">
    <h2>Radarr (movies)</h2>
    <label class="field wide"><span class="field-label">URL</span>
      <input class="input" id="w-radarr-url" value="${escapeHtml(draft.radarr_url)}" /></label>
    <label class="field wide"><span class="field-label">API key</span>
      <input class="input" id="w-radarr-key" type="password" value="${escapeHtml(draft.radarr_api_key)}" /></label>
    <button type="button" class="btn secondary" id="w-test-radarr">Test Radarr</button>
    <div id="w-radarr-result"></div>
  </div>`;
}

function renderSonarr() {
  return `<div class="wizard-panel">
    <h2>Sonarr (TV)</h2>
    <label class="field wide"><span class="field-label">URL</span>
      <input class="input" id="w-sonarr-url" value="${escapeHtml(draft.sonarr_url)}" /></label>
    <label class="field wide"><span class="field-label">API key</span>
      <input class="input" id="w-sonarr-key" type="password" value="${escapeHtml(draft.sonarr_api_key)}" /></label>
    <button type="button" class="btn secondary" id="w-test-sonarr">Test Sonarr</button>
    <div id="w-sonarr-result"></div>
  </div>`;
}

function renderReview() {
  return `<div class="wizard-panel">
    <h2>Review</h2>
    <p class="card-subtitle">Path mappings are generated automatically for typical Unraid Docker layouts.</p>
    <div id="w-review-checklist" class="review-checklist">Loading…</div>
    <details class="settings-group" style="margin-top:1rem">
      <summary>Advanced: path mappings</summary>
      <label class="field wide"><span class="field-label">Movie mappings</span>
        <input class="input" id="w-path-mappings" value="${escapeHtml(draft.path_mappings)}" /></label>
      <label class="field wide"><span class="field-label">TV mappings</span>
        <input class="input" id="w-tv-path-mappings" value="${escapeHtml(draft.tv_path_mappings)}" /></label>
    </details>
  </div>`;
}

function renderFirstScan() {
  return `<div class="wizard-panel">
    <h2>First scan</h2>
    <p>Run a <strong>movies dry run</strong> to see how many duplicates Reclaimspace finds. Nothing is moved.</p>
    <button type="button" class="btn btn-scan dry" id="w-first-scan">Start movies dry run</button>
    <div id="w-scan-progress" class="job-progress hidden"></div>
    <p id="w-scan-result" class="toast-area"></p>
    <button type="button" class="btn primary hidden" id="w-finish-wizard">Go to dashboard</button>
  </div>`;
}

function readDraftFromInputs() {
  const g = (id) => document.getElementById(id);
  draft.movies_root = g("w-movies-root")?.value?.trim() || draft.movies_root;
  draft.tv_root = g("w-tv-root")?.value?.trim() || draft.tv_root;
  draft.quarantine_root = g("w-quarantine-root")?.value?.trim() || draft.quarantine_root;
  draft.plex_url = g("w-plex-url")?.value?.trim() || draft.plex_url;
  draft.plex_token = g("w-plex-token")?.value?.trim() || draft.plex_token;
  draft.plex_movie_section = g("w-plex-movie-section")?.value?.trim() || draft.plex_movie_section;
  draft.plex_tv_section = g("w-plex-tv-section")?.value?.trim() || draft.plex_tv_section;
  draft.radarr_url = g("w-radarr-url")?.value?.trim() || draft.radarr_url;
  draft.radarr_api_key = g("w-radarr-key")?.value?.trim() || draft.radarr_api_key;
  draft.sonarr_url = g("w-sonarr-url")?.value?.trim() || draft.sonarr_url;
  draft.sonarr_api_key = g("w-sonarr-key")?.value?.trim() || draft.sonarr_api_key;
  draft.path_mappings = g("w-path-mappings")?.value?.trim() || draft.path_mappings;
  draft.tv_path_mappings = g("w-tv-path-mappings")?.value?.trim() || draft.tv_path_mappings;
}

async function loadDraftFromSettings() {
  try {
    const settings = await api("/api/settings");
    Object.assign(draft, {
      movies_root: settings.movies_root || draft.movies_root,
      tv_root: settings.tv_root || draft.tv_root,
      quarantine_root: settings.quarantine_root || draft.quarantine_root,
      plex_url: settings.plex_url || "",
      plex_movie_section: settings.plex_movie_section || "",
      plex_tv_section: settings.plex_tv_section || "",
      radarr_url: settings.radarr_url || "",
      sonarr_url: settings.sonarr_url || "",
      path_mappings: settings.path_mappings || "",
      tv_path_mappings: settings.tv_path_mappings || "",
    });
  } catch {
    /* fresh install */
  }
}

async function generateMappings() {
  const maps = await api("/api/setup/path-mappings", {
    method: "POST",
    body: JSON.stringify({ movies_root: draft.movies_root, tv_root: draft.tv_root }),
  });
  draft.path_mappings = maps.path_mappings;
  draft.tv_path_mappings = maps.tv_path_mappings;
}

async function saveSettings(finish = false) {
  await generateMappings();
  const payload = {
    ...draft,
    tv_page_size: 500,
    onboarding_complete: finish,
    setup_wizard_pending: !finish,
    notification_webhook_url: "",
    schedule_dry_run_enabled: false,
    schedule_dry_run_interval_hours: 168,
    schedule_dry_run_media_type: "movies",
  };
  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
}

function bindStepHandlers() {
  document.getElementById("w-test-paths")?.addEventListener("click", async () => {
    readDraftFromInputs();
    const el = document.getElementById("w-paths-result");
    el.innerHTML = '<p class="test-result">Validating…</p>';
    const result = await api("/api/setup/validate-paths", {
      method: "POST",
      body: JSON.stringify({
        movies_root: draft.movies_root,
        tv_root: draft.tv_root,
        quarantine_root: draft.quarantine_root,
      }),
    });
    stepState.paths = result.ok;
    el.innerHTML = resultHtml(result);
    if (result.paths) {
      el.innerHTML += `<ul class="wizard-list">${Object.entries(result.paths)
        .map(([k, v]) => `<li>${escapeHtml(k)}: ${v.ok ? "✓" : "✗"} ${escapeHtml(v.path)}</li>`)
        .join("")}</ul>`;
    }
  });

  document.getElementById("w-test-plex")?.addEventListener("click", async () => {
    readDraftFromInputs();
    const el = document.getElementById("w-plex-result");
    el.innerHTML = '<p class="test-result">Connecting…</p>';
    const result = await api("/api/setup/test/plex", {
      method: "POST",
      body: JSON.stringify({ plex_url: draft.plex_url, plex_token: draft.plex_token }),
    });
    stepState.plex = result.ok;
    el.innerHTML = resultHtml(result);
    const lib = document.getElementById("w-plex-libraries");
    if (result.ok && result.sections?.length) {
      lib.classList.remove("hidden");
      lib.innerHTML = result.sections
        .map((s) => {
          const target = s.type === "movie" ? "plex_movie_section" : s.type === "show" ? "plex_tv_section" : "";
          const btn = target
            ? `<button type="button" class="use-key-btn" data-key="${escapeHtml(s.key)}" data-target="${target}">Use</button>`
            : "";
          return `<div class="plex-library"><div><strong>${escapeHtml(s.title)}</strong> <span>${escapeHtml(s.type)} · ${escapeHtml(s.key)}</span></div>${btn}</div>`;
        })
        .join("");
      lib.querySelectorAll(".use-key-btn").forEach((b) => {
        b.addEventListener("click", () => {
          if (b.dataset.target === "plex_movie_section") draft.plex_movie_section = b.dataset.key;
          if (b.dataset.target === "plex_tv_section") draft.plex_tv_section = b.dataset.key;
          document.getElementById("w-plex-movie-section").value = draft.plex_movie_section;
          document.getElementById("w-plex-tv-section").value = draft.plex_tv_section;
        });
      });
    }
  });

  document.getElementById("w-test-radarr")?.addEventListener("click", async () => {
    readDraftFromInputs();
    const el = document.getElementById("w-radarr-result");
    el.innerHTML = '<p class="test-result">Connecting…</p>';
    const result = await api("/api/setup/test/radarr", {
      method: "POST",
      body: JSON.stringify({
        radarr_url: draft.radarr_url,
        radarr_api_key: draft.radarr_api_key,
        movies_root: draft.movies_root,
      }),
    });
    stepState.radarr = result.ok;
    el.innerHTML = resultHtml(result);
  });

  document.getElementById("w-test-sonarr")?.addEventListener("click", async () => {
    readDraftFromInputs();
    const el = document.getElementById("w-sonarr-result");
    el.innerHTML = '<p class="test-result">Connecting…</p>';
    const result = await api("/api/setup/test/sonarr", {
      method: "POST",
      body: JSON.stringify({
        sonarr_url: draft.sonarr_url,
        sonarr_api_key: draft.sonarr_api_key,
        tv_root: draft.tv_root,
      }),
    });
    stepState.sonarr = result.ok;
    el.innerHTML = resultHtml(result);
  });

  if (wizardStep === 5) {
    refreshReview();
  }

  document.getElementById("w-first-scan")?.addEventListener("click", async () => {
    readDraftFromInputs();
    await saveSettings(true);
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ media_type: "movies", mode: "dry_run" }),
    });
    document.getElementById("w-scan-result").textContent = `Job ${job.id} started.`;
    pollWizardJob(job.id);
  });

  document.getElementById("w-finish-wizard")?.addEventListener("click", () => {
    window.location.reload();
  });
}

async function refreshReview() {
  readDraftFromInputs();
  await generateMappings();
  const el = document.getElementById("w-review-checklist");
  const items = [
    ["Movies root", draft.movies_root],
    ["TV root", draft.tv_root],
    ["Quarantine", draft.quarantine_root],
    ["Plex", draft.plex_url ? "Configured" : "Missing"],
    ["Radarr", draft.radarr_url ? "Configured" : "Missing"],
    ["Sonarr", draft.sonarr_url ? "Configured" : "Missing"],
    ["Movie library key", draft.plex_movie_section || "—"],
    ["TV library key", draft.plex_tv_section || "—"],
  ];
  el.innerHTML = `<ul class="wizard-list">${items
    .map(([k, v]) => `<li><strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}</li>`)
    .join("")}</ul>`;
  document.getElementById("w-path-mappings").value = draft.path_mappings;
  document.getElementById("w-tv-path-mappings").value = draft.tv_path_mappings;
}

async function pollWizardJob(jobId) {
  const bar = document.getElementById("w-scan-progress");
  bar.classList.remove("hidden");
  const timer = setInterval(async () => {
    const job = await api(`/api/jobs/${jobId}`);
    const p = job.progress || {};
    bar.innerHTML = `<div class="progress-bar"><div style="width:${p.percent || 0}%"></div></div>
      <p class="job-meta">${escapeHtml(p.phase || "")} — ${escapeHtml(p.message || job.status)}</p>`;
    if (job.status === "completed" || job.status === "failed") {
      clearInterval(timer);
      document.getElementById("w-scan-result").textContent =
        job.status === "completed"
          ? `Done. Ready: ${job.summary?.ready_count ?? 0}, candidates: ${job.summary?.candidate_count ?? 0}`
          : job.error || "Scan failed";
      document.getElementById("w-finish-wizard")?.classList.remove("hidden");
    }
  }, 2500);
}

function canGoNext() {
  if (wizardStep === 0) return true;
  if (wizardStep === 1) return stepState.paths;
  if (wizardStep === 2) return stepState.plex && draft.plex_movie_section;
  if (wizardStep === 3) return stepState.radarr;
  if (wizardStep === 4) return stepState.sonarr;
  if (wizardStep === 5) return true;
  return true;
}

function renderWizard() {
  const panels = [
    renderWelcome,
    renderPaths,
    renderPlex,
    renderRadarr,
    renderSonarr,
    renderReview,
    renderFirstScan,
  ];
  wizardRoot.innerHTML = `
    <div class="wizard-shell">
      ${renderStepIndicator()}
      <div class="wizard-body">${panels[wizardStep]()}</div>
      <div class="wizard-nav">
        <button type="button" class="btn ghost" id="w-back" ${wizardStep === 0 ? "disabled" : ""}>Back</button>
        <button type="button" class="btn primary" id="w-next" ${wizardStep >= panels.length - 1 ? "disabled" : ""}>
          ${wizardStep === panels.length - 2 ? "Save & continue" : "Next"}
        </button>
      </div>
    </div>`;
  bindStepHandlers();

  document.getElementById("w-back")?.addEventListener("click", () => {
    readDraftFromInputs();
    wizardStep -= 1;
    renderWizard();
  });

  document.getElementById("w-next")?.addEventListener("click", async () => {
    readDraftFromInputs();
    if (wizardStep === 5) {
      await saveSettings(false);
    }
    if (!canGoNext()) {
      alert("Complete the test on this step before continuing.");
      return;
    }
    wizardStep += 1;
    renderWizard();
  });
}

async function initWizard() {
  await loadDraftFromSettings();
  renderWizard();
}

window.initWizard = initWizard;
