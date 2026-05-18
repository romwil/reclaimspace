/** Configuration form (used on /config). */

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
  {
    id: "automation",
    title: "Notifications & schedule",
    fields: [
      { key: "notification_webhook_url", label: "Webhook URL (Discord/ntfy)", wide: true, hint: "Optional POST on scan complete" },
      { key: "schedule_dry_run_enabled", label: "Scheduled dry runs", wide: false, checkbox: true },
      { key: "schedule_dry_run_interval_hours", label: "Interval (hours)", wide: false },
      { key: "schedule_dry_run_media_type", label: "Scheduled library (movies/tv)", wide: false },
    ],
  },
];

function allSettingsFields() {
  return SETTINGS_GROUPS.flatMap((group) => group.fields);
}

function buildSettingsForm() {
  const settingsForm = document.getElementById("settings-form");
  if (!settingsForm) return;

  settingsForm.innerHTML = SETTINGS_GROUPS.map((group) => {
    const fieldsHtml = group.fields
      .map((field) => {
        const wide = field.wide ? " wide" : "";
        if (field.checkbox) {
          return `<label class="${wide.trim()} checkbox-label">
            <input type="checkbox" name="${field.key}" />
            ${escapeHtml(field.label)}
          </label>`;
        }
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

function readSettingsForm() {
  const settingsForm = document.getElementById("settings-form");
  const data = {};
  for (const field of allSettingsFields()) {
    const input = settingsForm?.querySelector(`[name="${field.key}"]`);
    if (!input) continue;
    if (field.checkbox) {
      data[field.key] = input.checked;
    } else if (field.key === "tv_page_size" || field.key === "schedule_dry_run_interval_hours") {
      data[field.key] = Number(input.value) || 0;
    } else {
      data[field.key] = input.value;
    }
  }
  return data;
}

function fillSettingsForm(settings) {
  const settingsForm = document.getElementById("settings-form");
  for (const field of allSettingsFields()) {
    const input = settingsForm?.querySelector(`[name="${field.key}"]`);
    if (!input) continue;
    if (field.checkbox) {
      input.checked = Boolean(settings[field.key]);
    } else {
      input.value = settings[field.key] ?? "";
    }
  }
}

async function loadSettings() {
  const settings = await api("/api/settings");
  fillSettingsForm(settings);
}

async function saveSettings() {
  const btn = document.getElementById("save-settings");
  const settingsStatus = document.getElementById("settings-status");
  setToast(settingsStatus, "Saving…", "loading");
  btn.disabled = true;
  try {
    const payload = readSettingsForm();
    payload.onboarding_complete = true;
    payload.setup_wizard_pending = false;
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
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
  const settingsStatus = document.getElementById("settings-status");
  const settingsForm = document.getElementById("settings-form");
  if (!container) return;

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
        const input = settingsForm?.querySelector(`[name="${button.dataset.target}"]`);
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

function initSettingsPage() {
  buildSettingsForm();
  document.getElementById("save-settings")?.addEventListener("click", saveSettings);
  document.getElementById("load-plex-sections")?.addEventListener("click", loadPlexSections);
  loadSettings().catch((e) => {
    setToast(document.getElementById("settings-status"), e.message, "error");
  });
}
