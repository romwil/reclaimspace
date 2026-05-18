# Reclaimspace

Reclaim disk space from duplicate media files in Plex libraries while keeping the single file Radarr or Sonarr manages.

Plex sometimes indexes more than one file per movie or episode (leftovers after upgrades, renames, or manual copies). Reclaimspace asks Plex which items have duplicates, asks your *arr app which file is authoritative, and **quarantines** everything else. Nothing is deleted—files are moved to a timestamped quarantine folder with a manifest for rollback.

## Features

- **Web UI (Docker)** — configure services, run dry-run or quarantine scans, view JSON reports
- **Movies** — Plex + Radarr, default command
- **TV** — Plex (paged episode scan) + Sonarr (current `episodeFileId` only)
- **Dry run by default** — JSON reports before any file moves
- **Path mapping** — reconcile Plex container paths with Radarr/Sonarr paths on the host
- **Needs-review extraction** — separate report for ambiguous cases

## Requirements

- Python 3.10+ (CLI) or Docker (recommended on Unraid)
- Network access to Plex and Radarr (movies) and/or Sonarr (TV)
- API tokens for each service you use
- Read access to your media roots; write access to `QUARANTINE_ROOT` when quarantining

CLI uses stdlib only. The web UI requires optional dependencies (`pip install ".[web]"`) or the published Docker image.

## Docker / Unraid (recommended)

Unraid often has Docker without the Compose plugin. Use the helper script:

```bash
cd /mnt/user/appdata/reclaimspace
chmod +x docker-run.sh docker-stop.sh
mkdir -p config
cp -n config/settings.example.json config/settings.json  # first run only
./docker-run.sh
```

This reads API keys from `.env`, builds the image, and starts the container on port **8777**. Web UI settings are saved to `config/settings.json`, which is gitignored — never commit that file.

If your server has Compose v2 (`docker compose`) or v1 (`docker-compose`), you can use `docker-compose.yml` instead.

Open **http://your-server:8777/** — save settings, run a dry run, review reports, then quarantine when ready.

See [docs/DOCKER.md](docs/DOCKER.md) for volume paths, Unraid Community Applications template (`unraid/reclaimspace.xml`), and security notes.

## Quick start

1. **Clone and configure**

   ```bash
   git clone https://github.com/romwil/reclaimspace.git
   cd reclaimspace
   cp .env.example .env
   # Edit .env with your URLs, API keys, host paths, and path mappings
   ```

2. **Find your Plex library section keys** (use numeric `key`, not the library title):

   ```bash
   # Example: Movies = 1, TV Shows = 2
   export PLEX_MOVIE_SECTION=1
   export PLEX_TV_SECTION=2
   ```

3. **Movies — dry run**

   ```bash
   python3 -m reclaimspace.media_duplicates --report reports/movies-dry-run.json
   ```

4. **Review** `ready_count`, `candidate_count`, and sample groups in the report.

5. **Movies — quarantine** (after you are satisfied)

   ```bash
   python3 -m reclaimspace.media_duplicates --quarantine --report reports/movies-quarantine.json
   ```

6. **TV — same pattern**

   ```bash
   python3 -m reclaimspace.media_duplicates tv --report reports/tv-dry-run.json
   python3 -m reclaimspace.media_duplicates tv --quarantine --report reports/tv-quarantine.json
   ```

See [docs/USAGE.md](docs/USAGE.md) for detailed workflows and [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for every environment variable.

## Commands

| Command | Description |
|---------|-------------|
| `python3 -m reclaimspace.media_duplicates` | Movies: dry run (default) |
| `python3 -m reclaimspace.media_duplicates --quarantine` | Movies: move candidates to quarantine |
| `python3 -m reclaimspace.media_duplicates tv` | TV: dry run |
| `python3 -m reclaimspace.media_duplicates tv --quarantine` | TV: quarantine |
| `python3 -m reclaimspace.media_duplicates review-report SOURCE --output OUT` | Extract `needs_review` groups |

Installed entry point (optional): `media-duplicates` (same as the module above).

## Path mappings (important)

Plex and the *arr stack often use different path prefixes for the same files. Set explicit mappings in `.env`:

```bash
PATH_MAPPINGS=/data/media/movies=/mnt/user/data/media/movies;/movies=/mnt/user/data/media/movies
TV_PATH_MAPPINGS=/data/media/tv=/mnt/user/data/media/tv;/tv=/mnt/user/data/media/tv
```

Adjust host paths to match your server. Both prefixes for a library must resolve to the same path under `MOVIES_ROOT` or `TV_ROOT`.

## Safety

- Never deletes files—only moves to `QUARANTINE_ROOT/<run-id>/`
- Does not quarantine files Radarr/Sonarr mark as managed
- Skips single-file Plex items (not duplicates)
- TV: ignores stale Sonarr `episodefile` rows not linked to an episode
- Items outside the configured media root or with no managed match → `needs_review` (no automatic move)

## Project layout

```text
reclaimspace/
  media_duplicates.py   # CLI and core logic
  config_store.py       # Persistent settings (web)
  runner.py             # Scan API for web jobs
  web/                  # FastAPI app and static UI
tests/
docs/
  CONFIGURATION.md
  USAGE.md
  DOCKER.md
Dockerfile
docker-compose.yml
unraid/reclaimspace.xml # Unraid CA template
.env.example
```

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

[MIT](LICENSE)

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
