# Web UI

Reclaimspace serves a browser UI on port **8777** (Docker default). The CLI and web app share the same scan logic.

## Pages

| URL | Purpose |
|-----|---------|
| `/` | **Dashboard** — run scans, jobs, reports, quarantine restore |
| `/config` | **Configuration** — Plex, Radarr, Sonarr, paths, notifications, schedule |

The header shows **Dashboard**, **Configuration**, **Setup wizard**, and a version health pill.

## First visit

If onboarding is not complete, the **setup wizard** runs instead of the dashboard (seven steps: paths → Plex → Radarr → Sonarr → review → optional first dry run).

Existing installs with saved credentials are marked onboarded automatically. Use **Setup wizard** in the header to re-run setup without clearing API keys.

## Dashboard

### Run scan

Choose **Movies** or **TV**, then **Dry run** (report only) or **Quarantine** (move files). Quarantine always writes a manifest under your quarantine root.

### Recent jobs

Click a completed job to open its report. Progress bar and phase text appear while a scan runs.

### Reports

1. Select a report from the left list.
2. Use the **Data** tab for the interactive grid:
   - **Search** — title, status, paths, reason
   - **Status** filter — all, ready, needs_review, etc.
   - **Column headers** — click to sort (click again to reverse)
   - **Row click** — expand full keep/duplicate paths
3. Use the **JSON** tab for a structured tree view of the raw report.
4. **Download** saves the JSON file.

Summary chips above the grid show ready count, candidates, needs review, quarantined, and missing-on-disk totals.

### Restore from quarantine

Lists rollback manifests under your quarantine folder. **Preview restore** is a dry run; **Restore** moves files back to their original paths.

## Configuration

Open **Configuration** in the header (or `/config`).

- Settings persist to `settings.json` under your config volume (`/config` in Docker).
- Secrets are **masked** when loaded; leave token fields blank on save to keep existing values.
- **Plex libraries** loads section keys you can apply to movie/TV library fields.
- **Setup wizard** re-opens the first-run flow.

## Security

There is **no login**. Use on a trusted LAN, bind to localhost with a reverse proxy, or firewall port 8777. Do not expose the UI directly to the internet.

See [DOCKER.md](DOCKER.md) and [ONBOARDING.md](ONBOARDING.md).
