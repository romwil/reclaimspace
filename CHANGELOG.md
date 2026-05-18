# Changelog

All notable changes to this project are documented in this file.

## [1.1.0] - 2026-05-18

### Added

- Web UI (FastAPI) for settings, background scan jobs, and report viewing.
- Persistent `settings.json` under `DATA_DIR` (default `/config`), merged with container env overrides.
- Docker image, `docker-compose.yml`, and Unraid Community Applications template (`unraid/reclaimspace.xml`).
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
