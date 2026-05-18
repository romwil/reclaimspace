# Changelog

All notable changes to this project are documented in this file.

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
