# Web UI

Reclaimspace serves a browser UI on port **8777** (Docker default). The CLI and web app share the same media scan logic.

The UI has two modes. **Media** quarantines Plex duplicates and never deletes files. **Appdata** lists leftover folders on the appdata share and can quarantine, migrate, or permanently delete them.

## Pages

| URL | Purpose |
|-----|---------|
| `/` | **Media** — run scans, jobs, reports, quarantine restore |
| `/appdata` | **Appdata** — unused appdata folders, migrate, quarantine, delete |
| `/config` | **Configuration** — Plex, Radarr, Sonarr, paths, notifications, schedule, Appdata |

The header shows **Media**, **Appdata**, **Configuration**, **Setup wizard**, and a version health pill.

## First visit

If onboarding is not complete, the **setup wizard** runs instead of the Media page (seven steps: paths → Plex → Radarr → Sonarr → review → optional first dry run).

Existing installs with saved credentials are marked onboarded automatically. Use **Setup wizard** in the header to re-run setup without clearing API keys.

## Media

Media is the duplicate workflow: Movies and TV scans, jobs, the report grid, Plex Split, and media quarantine restore. It moves files into quarantine. It never deletes them.

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

Lists rollback manifests under your media quarantine folder. **Preview restore** is a dry run; **Restore** moves files back to their original paths. Appdata `_archive` restore is on the Appdata page.

## Appdata

Open **Appdata** in the header (or `/appdata`). A top-level folder is **in use** when any container, running or stopped, bind-mounts that folder or anything inside it. Unraid may record the same share as `/mnt/user/appdata/<name>` or `/mnt/cache/appdata/<name>`; both match the folder name. A mount of the whole share covers every folder. `_archive` is never a candidate.

### Scan

**Scan** starts a background job and sizes each unused folder. Large trees, such as Plex appdata, can take a while. Results list unused folders largest first.

If the Unraid API and the optional Docker socket are both unavailable, the scan stops with an error. Folders are not shown as unused.

**In use** lists each mounted folder and the container names that mount it. Those rows have no checkbox.

### Unused folders

Each candidate has a checkbox, the folder name, and the total size. **Select all** and **Select none** apply only to this list.

- **Code** — badge for a folder that looks like a project. A `.git` directory is enough. Otherwise the folder needs at least two of `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, a `*.sln` file, or `.code-workspace`. Matched evidence is in the row expander. The badge is advisory: nothing moves until you confirm, and a container mount always wins.
- **Explore** — one directory level inside that folder. Open a subdirectory to list the next level. Paths stay under the appdata root.
- **Migrate** — selected **Code** rows only. Moves `/appdata/<name>` to `/code/<name>`. The confirmation lists source, destination, size, and evidence. The move is refused when the destination already exists or a container mounts the folder. Migrate does not write an Appdata quarantine entry, and this page cannot restore it.
- **Quarantine** — moves the selected folders to `appdata/_archive/<name>`. If that name is already there, a timestamp is appended. Restore for these folders is the archive panel on this page.
- **Delete** — permanently deletes the selected folders after a confirmation that names each one.
- **Remove empty folders** — separate from the checkboxes. Removes top-level directories that contain nothing, skipping `_archive` and any folder a container still mounts.

### Archive

Lists `_archive` entries. **Select all** and **Select none** apply to this list. **Restore** and **Purge** are separate buttons.

- **Restore** moves a folder back to the appdata root. If that name is already occupied, restore stops for that folder and says so.
- **Purge** permanently deletes the selected archive folders and their manifests. The confirmation lists each folder and its size.

**Delete** and **Purge** are permanent. Media scans never delete files.

## Configuration

Open **Configuration** in the header (or `/config`).

- Settings persist to `settings.json` under your config volume (`/config` in Docker).
- Secrets are **masked** when loaded; leave token fields blank on save to keep existing values.
- **Plex libraries** loads section keys you can apply to movie/TV library fields.
- **Appdata** — **Appdata root**, **Code root**, **Host prefixes**, **Unraid API URL**, a masked **Unraid API key**, and an optional **Docker socket**. Create the key in Unraid with only `DOCKER:READ_ANY`. Leave the key blank on save to keep the stored value. **Test Unraid API** checks that Docker can be read and does not list mounts. Leave **Docker socket** empty unless you set `DOCKER_SOCKET`. Without the Unraid API or that socket, Appdata scan fails closed.
- **Setup wizard** re-opens the first-run flow. The wizard stays on Media; the Unraid key lives on Configuration.

## Security

There is **no login**. Use on a trusted LAN, bind to localhost with a reverse proxy, or firewall port 8777. Do not expose the UI directly to the internet.

See [DOCKER.md](DOCKER.md) and [ONBOARDING.md](ONBOARDING.md).
