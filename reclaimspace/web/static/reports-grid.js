/** Sortable, filterable report data grid. */

const REPORT_GRID_COLUMNS = [
  { key: "title", label: "Title", type: "string", get: (r) => r.title || "" },
  { key: "year", label: "Year", type: "number", get: (r) => (r.year == null ? -1 : Number(r.year)) },
  { key: "status", label: "Status", type: "string", get: (r) => r.status || "" },
  { key: "reason", label: "Reason", type: "string", get: (r) => r.reason || "" },
  {
    key: "candidate_count",
    label: "Files",
    type: "number",
    get: (r) => Number(r.candidate_count) || 0,
  },
  {
    key: "reclaimable_bytes",
    label: "Reclaim",
    type: "number",
    get: (r) => Number(r.reclaimable_bytes) || 0,
    format: (r) => r.reclaimable_human || formatBytes(r.reclaimable_bytes || 0),
  },
  {
    key: "protected_path",
    label: "Keep",
    type: "string",
    get: (r) => r.protected_path || "",
    format: (r) => pathBasename(r.protected_path) || "—",
    title: (r) => r.protected_path || "",
  },
  {
    key: "sample_candidate",
    label: "Duplicate",
    type: "string",
    get: (r) => r.sample_candidate || "",
    format: (r) => pathBasename(r.sample_candidate) || "—",
    title: (r) => r.sample_candidate || "",
  },
];

class ReportDataGrid {
  constructor(container) {
    this.container = container;
    this.rows = [];
    this.filtered = [];
    this.sort = { key: "title", dir: "asc" };
    this.filters = { search: "", status: "all" };
    this.expandedId = null;
  }

  setRows(rows) {
    this.rows = rows.map((row, index) => ({
      ...row,
      _rowId: `${row.rating_key || row.title || "row"}-${index}`,
    }));
    this.expandedId = null;
    this.applyFilters();
    this.render();
  }

  applyFilters() {
    let rows = [...this.rows];
    if (this.filters.status !== "all") {
      rows = rows.filter((r) => r.status === this.filters.status);
    }
    const q = this.filters.search.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => {
        const haystack = [
          r.title,
          r.year,
          r.status,
          r.reason,
          r.protected_path,
          r.sample_candidate,
          r.rating_key,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }

    const col = REPORT_GRID_COLUMNS.find((c) => c.key === this.sort.key) || REPORT_GRID_COLUMNS[0];
    const dir = this.sort.dir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      const av = col.get(a);
      const bv = col.get(b);
      if (col.type === "number") {
        return (av - bv) * dir;
      }
      return String(av).localeCompare(String(bv), undefined, { sensitivity: "base" }) * dir;
    });
    this.filtered = rows;
  }

  toggleSort(key) {
    if (this.sort.key === key) {
      this.sort.dir = this.sort.dir === "asc" ? "desc" : "asc";
    } else {
      this.sort.key = key;
      this.sort.dir = "asc";
    }
    this.applyFilters();
    this.render();
  }

  render() {
    const statuses = [...new Set(this.rows.map((r) => r.status).filter(Boolean))].sort();
    const statusOptions = [
      `<option value="all"${this.filters.status === "all" ? " selected" : ""}>All statuses</option>`,
      ...statuses.map(
        (s) =>
          `<option value="${escapeHtml(s)}"${this.filters.status === s ? " selected" : ""}>${escapeHtml(s)}</option>`
      ),
    ].join("");

    const headerCells = REPORT_GRID_COLUMNS.map((col) => {
      const active = this.sort.key === col.key;
      const arrow = active ? (this.sort.dir === "asc" ? " ▲" : " ▼") : "";
      return `<th scope="col" class="sortable${active ? " sorted" : ""}" data-sort="${col.key}">${escapeHtml(col.label)}${arrow}</th>`;
    }).join("");

    const bodyRows = this.filtered.length
      ? this.filtered
          .map((row) => {
            const expanded = this.expandedId === row._rowId;
            const cells = REPORT_GRID_COLUMNS.map((col) => {
              const display = col.format ? col.format(row) : escapeHtml(String(col.get(row) ?? ""));
              const title = col.title ? col.title(row) : col.get(row);
              const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
              if (col.key === "status") {
                return `<td><span class="badge badge-${escapeHtml(row.status)}">${escapeHtml(row.status)}</span></td>`;
              }
              if (col.key === "title") {
                const year = row.year ? ` <span class="text-muted">(${row.year})</span>` : "";
                return `<td class="col-title">${escapeHtml(row.title || "")}${year}</td>`;
              }
              return `<td class="col-${col.key}"${titleAttr}>${display}</td>`;
            }).join("");
            const detail = expanded
              ? `<tr class="grid-detail-row"><td colspan="${REPORT_GRID_COLUMNS.length}">
                  <div class="grid-detail">
                    <p><strong>Keep:</strong> <code>${escapeHtml(row.protected_path || "—")}</code></p>
                    <p><strong>Duplicate:</strong> <code>${escapeHtml(row.sample_candidate || "—")}</code></p>
                    ${row.reason ? `<p><strong>Reason:</strong> ${escapeHtml(row.reason)}</p>` : ""}
                    ${row.rating_key ? `<p><strong>Plex key:</strong> ${escapeHtml(row.rating_key)}</p>` : ""}
                  </div>
                </td></tr>`
              : "";
            return `<tr class="grid-row${expanded ? " expanded" : ""}" data-row-id="${escapeHtml(row._rowId)}">${cells}</tr>${detail}`;
          })
          .join("")
      : `<tr><td colspan="${REPORT_GRID_COLUMNS.length}" class="grid-empty">No rows match your filters.</td></tr>`;

    this.container.innerHTML = `
      <div class="grid-toolbar">
        <label class="grid-search">
          <span class="sr-only">Search report</span>
          <input type="search" class="input" id="grid-search-input" placeholder="Search title, path, status…" value="${escapeHtml(this.filters.search)}" />
        </label>
        <label class="grid-status-filter">
          <span class="field-label">Status</span>
          <select class="input" id="grid-status-select">${statusOptions}</select>
        </label>
        <span class="grid-count">${this.filtered.length} / ${this.rows.length} groups</span>
      </div>
      <div class="grid-table-wrap">
        <table class="data-table report-grid-table">
          <thead><tr>${headerCells}</tr></thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>`;

    this.container.querySelector("#grid-search-input")?.addEventListener("input", (e) => {
      this.filters.search = e.target.value;
      this.applyFilters();
      this.render();
      const input = this.container.querySelector("#grid-search-input");
      if (input) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
    });

    this.container.querySelector("#grid-status-select")?.addEventListener("change", (e) => {
      this.filters.status = e.target.value;
      this.applyFilters();
      this.render();
    });

    this.container.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => this.toggleSort(th.dataset.sort));
    });

    this.container.querySelectorAll("tr.grid-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = tr.dataset.rowId;
        this.expandedId = this.expandedId === id ? null : id;
        this.render();
      });
    });
  }
}

function renderJsonTree(value, depth = 0) {
  const indent = "  ".repeat(depth);
  if (value === null) {
    return `<span class="json-null">null</span>`;
  }
  if (typeof value === "boolean") {
    return `<span class="json-bool">${value}</span>`;
  }
  if (typeof value === "number") {
    return `<span class="json-num">${value}</span>`;
  }
  if (typeof value === "string") {
    const short = value.length > 120 ? `${escapeHtml(value.slice(0, 120))}…` : escapeHtml(value);
    return `<span class="json-str">"${short}"</span>`;
  }
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="json-bracket">[]</span>';
    const items = value
      .slice(0, 50)
      .map((item, i) => `${indent}  <span class="json-key">${i}</span>: ${renderJsonTree(item, depth + 1)}`)
      .join(",<br>");
    const more = value.length > 50 ? `<br>${indent}  <span class="json-muted">… ${value.length - 50} more</span>` : "";
    return `<span class="json-bracket">[</span><br>${items}${more}<br>${indent}<span class="json-bracket">]</span>`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return '<span class="json-bracket">{}</span>';
    const lines = entries
      .slice(0, 40)
      .map(
        ([k, v]) =>
          `${indent}  <span class="json-key">"${escapeHtml(k)}"</span>: ${renderJsonTree(v, depth + 1)}`
      )
      .join(",<br>");
    const more =
      entries.length > 40
        ? `<br>${indent}  <span class="json-muted">… ${entries.length - 40} more keys</span>`
        : "";
    return `<span class="json-bracket">{</span><br>${lines}${more}<br>${indent}<span class="json-bracket">}</span>`;
  }
  return escapeHtml(String(value));
}

function renderJsonPanel(container, data) {
  const topKeys = ["media_type", "scan_mode", "ready_count", "candidate_count", "needs_review_count", "groups"];
  const summary = topKeys
    .filter((k) => k in data)
    .map((k) => {
      const v = data[k];
      const display = k === "groups" && Array.isArray(v) ? `${v.length} items` : escapeHtml(String(v));
      return `<div class="json-summary-chip"><span>${escapeHtml(k)}</span><strong>${display}</strong></div>`;
    })
    .join("");

  container.innerHTML = `
    <div class="json-summary">${summary}</div>
    <div class="json-tree" tabindex="0">${renderJsonTree(data)}</div>`;
}

window.ReportDataGrid = ReportDataGrid;
window.renderJsonPanel = renderJsonPanel;
