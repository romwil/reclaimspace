# Changelog

All notable changes to this project are documented in this file.

## [1.4.1] - 2026-10-15

### Fixed

- Configuration **Save** keeps the Unraid API URL and key, and the next Appdata scan reads those saved values. A blank container variable such as `UNRAID_API_KEY` no longer replaces a value stored in `settings.json`. The template default `UNRAID_API_URL` no longer hides a URL saved in the UI. Reload still masks the key and shows that a key is saved.

## [1.4.0] - 2026-10-15

### Added

- **Appdata** page at `/appdata` for leftover top-level folders on the appdata share. A folder is in use when any container, running or stopped, bind-mounts it. `/mnt/user/appdata/<name>` and `/mnt/cache/appdata/<name>` are the same folder. A mount of the whole share protects every folder. `_archive` is never a candidate.
- Scan sizes unused folders in the background and lists them largest first. If the Unraid API and the optional Docker socket are both unavailable, the scan stops and does not treat folders as unused.
- **Migrate** moves a selected code folder from `/appdata/<name>` to `/code/<name>` after confirmation. A `.git` directory, or at least two project markers, marks a folder as code. The move is refused when the destination exists or a container still mounts the folder.
- **Quarantine** moves unused folders to `appdata/_archive/<name>` with a manifest. **Restore** moves them back and stops when the original name is occupied. **Delete** and **Purge** permanently remove the named folders after confirmation. **Remove empty folders** skips `_archive` and anything still mounted.
- Configuration fields for the appdata root, code root, host prefixes, Unraid API URL, and a masked Unraid API key. The key should have only `DOCKER:READ_ANY`. **Test** checks that Docker can be read and does not list mounts.
- Container mounts for `/mnt/cache/appdata` → `/appdata` and `/mnt/user/data/code` → `/code` in Compose, `docker-run.sh`, and the Unraid templates. The Docker socket is not mounted.

### Changed

- The header links **Media**, **Appdata**, and **Configuration**. Media still quarantines Plex duplicates and never deletes files.

## [1.3.0] - 2026-09-29

### Added

- **Split in Plex** on a report row that lists two or more paths. The confirm prompt shows every path. The action calls Plex split only: it does not move files and does not change Radarr or Sonarr. Run a new dry run afterward; the open report does not update itself.
- **Protected** summary chip (`protected_count`) for groups where every Plex path is a current managed file. Older reports that omit the field still show the chip, counted from the groups.
- Report rows include every Plex path, protected path, and candidate path.

### Changed

- The report grid status filter opens on **Ready** (rows with something to quarantine).
- The **Candidates** column counts quarantine candidate paths only.
- Expanding a row lists every path, not a single sample keep or duplicate path.
- A protected group is described as every Plex path matching some current managed file (this title’s file and another title’s file can both be protected). Quarantine still skips the whole group.

## [1.2.0] - 2026-05-18

### Added

- First-run setup wizard with step-by-step Plex, Radarr, Sonarr, and path validation.
- Setup API: status, path validation, service connectivity tests, auto path mappings, wizard reset.
- Dashboard at `/` and **Configuration** page at `/config` with header navigation.
- Job progress phases and percent in the UI (including TV Plex paging).
- Masked secrets on `GET /api/settings`; merge on save preserves existing tokens.
- Report summary chips and **interactive data grid** (search, status filter, column sort, row expand).
- Structured **JSON** report tree viewer.
- Quarantine restore UI with dry-run preview and optional webhook notifications.
- Optional scheduled dry-run scans (in-process scheduler).
- Unraid Community Applications metadata: `ca_profile.xml`, `templates/reclaimspace.xml`, `icon.svg`.
- Docs: [WEB_UI.md](docs/WEB_UI.md), [UNRAID_CA.md](docs/UNRAID_CA.md), [RELEASE.md](docs/RELEASE.md).

### Changed

- Dashboard hidden until onboarding completes; existing configured installs auto-mark onboarded.
- Reports API group limit raised to 10,000 rows for full-grid client filtering.

### Fixed

- Setup wizard re-run (`Setup wizard` button) stays open instead of flickering back to dashboard.
- JavaScript bootstrap failure from duplicate `wizardRoot` declaration across scripts.
- `load_merged_settings` no longer overwrites `settings.json` booleans with default env values.
- `setup_wizard_pending` flag respected so legacy auto-onboarding does not skip re-run wizard.

## [1.1.0] - 2026-05-18

### Added

- Web UI (FastAPI) for settings, background scan jobs, and report viewing.
- Persistent `settings.json` under `DATA_DIR` (default `/config`), merged with container env overrides.
- Docker image, `docker-compose.yml`, and Unraid template (`unraid/reclaimspace.xml`).
- `reclaimspace-web` entry point and `python -m reclaimspace.web` server on port 8777.

## [1.0.0] - 2026-05-18

### Added

- Movies workflow: Plex duplicate detection with Radarr-managed file protection.
- TV workflow: paged Plex episode scan with Sonarr-managed episode file protection.
- Quarantine mode with timestamped run folders and JSON manifests for rollback.
- `review-report` command to extract `needs_review` groups from any report.
- Container-to-host path mapping via `PATH_MAPPINGS` and `TV_PATH_MAPPINGS`.
- Skips Plex-reported paths that no longer exist on disk during TV quarantine.
- Sonarr protection uses only episode files currently linked by `episodeFileId` (not stale `/episodefile` records).

### Notes

- The tool never deletes files; it only moves quarantine candidates.
- Default CLI command targets movies; use `tv` for television libraries.
