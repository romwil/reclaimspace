# Reclaimspace

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)](https://github.com/romwil/reclaimspace/releases)

Reclaim disk space from duplicate media files in Plex libraries while keeping the single file Radarr or Sonarr manages.

Plex sometimes indexes more than one file per movie or episode (leftovers after upgrades, renames, or manual copies). Reclaimspace asks Plex which items have duplicates, asks your *arr app which file is authoritative, and **quarantines** everything else. Nothing is deleted—files are moved to a timestamped quarantine folder with a manifest for rollback.

## Features

| Area | What you get |
|------|----------------|
| **Web UI** | Setup wizard, dashboard scans, sortable/filterable reports, restore, `/config` settings |
| **Movies** | Plex + Radarr duplicate detection and quarantine |
| **TV** | Plex (paged) + Sonarr (`episodeFileId` only) |
| **Safety** | Dry run by default; needs-review queue for ambiguous items |
| **Unraid** | CA-ready template, `docker-run.sh` without Compose |

## Screenshots (web UI)

- **Dashboard** — run dry-run / quarantine, jobs, reports, restore
- **Reports** — search, filter by status, sort columns, expand rows for full paths
- **Configuration** — Plex, Radarr, Sonarr, paths, webhooks, schedule

See [docs/WEB_UI.md](docs/WEB_UI.md).

## Requirements

- **Docker** (recommended on Unraid) or Python 3.10+ for CLI-only use
- Network access to Plex and Radarr (movies) and/or Sonarr (TV)
- API tokens for each service you use
- Read access to media roots; write access to quarantine when quarantining

CLI uses stdlib only. The web UI requires optional dependencies (`pip install ".[web]"`) or the published Docker image.

## Docker / Unraid (recommended)

```bash
git clone https://github.com/romwil/reclaimspace.git
cd reclaimspace
cp .env.example .env          # optional: seed API keys for first boot
chmod +x docker-run.sh docker-stop.sh
mkdir -p config
./docker-run.sh
```

Open **http://your-server:8777/** — complete the setup wizard, run a **dry run**, review the report grid, then **quarantine** when ready.

| Resource | Link |
|----------|------|
| Docker paths & security | [docs/DOCKER.md](docs/DOCKER.md) |
| Setup wizard | [docs/ONBOARDING.md](docs/ONBOARDING.md) |
| Web UI guide | [docs/WEB_UI.md](docs/WEB_UI.md) |
| Unraid Community Applications | [docs/UNRAID_CA.md](docs/UNRAID_CA.md) |
| Release & Docker Hub publish | [docs/RELEASE.md](docs/RELEASE.md) |

**Docker Hub:** `romwil/reclaimspace` (tags `latest`, `1.2.0`)

**Do not commit** `config/settings.json` — it contains API tokens (gitignored).

### Unraid Community Applications

After the image is on Docker Hub, submit the repo via [ca.unraid.net/submit](https://ca.unraid.net/submit). This repository includes `ca_profile.xml` and `templates/reclaimspace.xml`. Full steps: [docs/UNRAID_CA.md](docs/UNRAID_CA.md).

## CLI quick start

```bash
cp .env.example .env
# Edit URLs, keys, paths, PATH_MAPPINGS

# Movies dry run
python3 -m reclaimspace.media_duplicates --report reports/movies-dry-run.json

# Movies quarantine (after review)
python3 -m reclaimspace.media_duplicates --quarantine --report reports/movies-quarantine.json

# TV
python3 -m reclaimspace.media_duplicates tv --report reports/tv-dry-run.json
```

See [docs/USAGE.md](docs/USAGE.md) and [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Path mappings

Plex and *arr often use different path prefixes. Example:

```bash
PATH_MAPPINGS=/data/media/movies=/mnt/user/data/media/movies;/movies=/mnt/user/data/media/movies
TV_PATH_MAPPINGS=/data/media/tv=/mnt/user/data/media/tv;/tv=/mnt/user/data/media/tv
```

The setup wizard can generate typical Unraid mappings automatically.

## Safety

- Never deletes files—only moves to `QUARANTINE_ROOT/<run-id>/`
- Does not quarantine Radarr/Sonarr-managed files
- Skips single-file Plex items
- Ambiguous items → `needs_review` (no automatic move)

## Project layout

```text
reclaimspace/           # Python package (CLI + web)
  media_duplicates.py
  web/                  # FastAPI + static UI
templates/              # Unraid CA container template (canonical)
unraid/                 # Legacy template path
docs/
ca_profile.xml          # Unraid CA repository profile
reclaimspace_icon.jpg   # CA / template icon
icon.svg                # Optional legacy icon
docker-run.sh
Dockerfile
```

## Tests

```bash
python3 -m unittest discover -s tests
```

## Releases

| Version | Notes |
|---------|--------|
| [v1.2.0](https://github.com/romwil/reclaimspace/releases/tag/v1.2.0) | Wizard, reports grid, config page, CA metadata |
| [v1.1.0](https://github.com/romwil/reclaimspace/releases/tag/v1.1.0) | Web UI, Docker |
| [v1.0.0](https://github.com/romwil/reclaimspace/releases/tag/v1.0.0) | CLI |

See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
