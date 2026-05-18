# Reclaimspace

Reclaimspace is a cleanup utility for Plex plus Arr-managed libraries. It asks Plex which media items have multiple files, asks Radarr or Sonarr which file is actively managed, and quarantines only duplicate files the relevant Arr app does not know about.

The first implementation never deletes files directly.

## Requirements

- Python 3.10 or newer
- Network access to Plex and Radarr
- Plex token and Radarr API key

## Configuration

Copy `.env.example` to a local `.env` file or export the variables in your shell:

```bash
export PLEX_URL="http://10.10.1.202:32400"
export PLEX_TOKEN="your-plex-token"
export RADARR_URL="http://10.10.1.202:7878"
export RADARR_API_KEY="your-radarr-api-key"
export SONARR_URL="http://10.10.1.202:8989"
export SONARR_API_KEY="your-sonarr-api-key"
export MOVIES_ROOT="/mnt/user/appdata/data/media/movies"
export TV_ROOT="/mnt/user/appdata/data/media/tv"
export PATH_MAPPINGS="/data/media/movies=/mnt/user/appdata/data/media/movies;/movies=/mnt/user/appdata/data/media/movies"
export TV_PATH_MAPPINGS="/data/media/tv=/mnt/user/appdata/data/media/tv;/tv=/mnt/user/appdata/data/media/tv"
export QUARANTINE_ROOT="/mnt/user/appdata/reclaimspace/quarantine"
```

If Plex has more than one movie library, set `PLEX_MOVIE_SECTION` to the library section key. If it is blank, the tool uses the first Plex library with type `movie`.

`PATH_MAPPINGS` is the explicit container-to-host translation used before comparing Plex and Radarr paths. Plex commonly reports files as `/data/media/movies/...`, while Radarr reports the same library as `/movies/...`; both prefixes must map to the same host path.

For TV, set `PLEX_TV_SECTION` to the Plex TV Shows library key and use `TV_PATH_MAPPINGS` to map Plex `/data/media/tv/...` and Sonarr `/tv/...` paths to the same host root.

## Dry Run

Dry-run mode is the default and writes a JSON report without moving files:

```bash
python3 -m reclaimspace.media_duplicates --report movie-duplicates-report.json
```

Run a TV dry run against Sonarr-managed episode files:

```bash
python3 -m reclaimspace.media_duplicates tv --report tv-duplicates-report.json
```

The report includes:

- `plex_paths`: all files Plex reports for a duplicate media item
- `protected_paths`: files Radarr/Sonarr manages and the tool will not touch
- `candidate_paths`: duplicate files eligible for quarantine
- `status`: `ready`, `protected`, or `needs_review`

## Quarantine

After reviewing the dry-run report, run with `--quarantine`:

```bash
python3 -m reclaimspace.media_duplicates --quarantine --report quarantine-report.json
```

For TV:

```bash
python3 -m reclaimspace.media_duplicates tv --quarantine --report tv-quarantine-report.json
```

Files move to:

```text
$QUARANTINE_ROOT/<run-id>/movies/<relative movie path>
```

Each run writes:

```text
$QUARANTINE_ROOT/<run-id>/manifest.json
```

The manifest records every source and destination path so files can be moved back manually if needed.

If Plex reports a duplicate path that no longer exists on disk, the TV quarantine run skips that path and records it in `missing_source_paths` in the report.

## Needs Review Report

After a dry-run or quarantine run, generate a smaller report containing only the groups that were skipped for manual review:

```bash
python3 -m reclaimspace.media_duplicates review-report \
  reports/movie-duplicates-quarantine.json \
  --output reports/movie-duplicates-needs-review.json
```

The review report keeps each skipped group's Plex paths and reason, and adds file counts to make the manual intervention list easier to scan.

## Tests

Run the unit tests with Python 3:

```bash
python3 -m unittest discover -s tests
```

