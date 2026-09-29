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
   - **Status** filter — opens on **Ready** (rows with something to quarantine). Switch to All statuses, Protected, or Needs review.
   - **Column headers** — click to sort (click again to reverse). **Candidates** counts quarantine candidate paths only.
   - **Row click** — expand every Plex path, every protected path, and every candidate path. When a group has two or more Plex paths, **Split in Plex** separates them into individual library items, the same as Split in the Plex client. Confirm first; the prompt lists the full paths. Split does not move or delete files and does not change Radarr or Sonarr. It separates every file on that Plex item, including an intentional two-part movie. Afterward, run a new dry run — the open report does not update itself.
3. Use the **JSON** tab for a structured tree view of the raw report.
4. **Download** saves the JSON file.

Summary chips above the grid show ready, candidates, protected, needs review, quarantined, and missing-on-disk totals. Protected is the number of groups with nothing safe to quarantine. Older reports that omit `protected_count` still show that chip; the count is taken from the groups.

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
