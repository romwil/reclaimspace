# Usage guide

This document describes the full workflow for movies and TV. For environment variables, see [CONFIGURATION.md](CONFIGURATION.md).

## How it works

```text
Plex library scan
    → find items with more than one media file on disk
    → normalize paths to host paths (PATH_MAPPINGS / TV_PATH_MAPPINGS)
    → compare against Radarr (movies) or Sonarr (TV) managed files
    → classify each duplicate group
```

### Group status

| Status | Meaning |
|--------|---------|
| `ready` | At least one Plex file is protected by the *arr app; other files are quarantine candidates |
| `protected` | Every Plex path matches some current managed file, so nothing is safe to quarantine |
| `needs_review` | Ambiguous case (e.g. no managed file match, or paths outside the configured root) |

Quarantine only acts on `ready` groups.

### Authority model

- **Plex** decides *which items have duplicates* (multiple file parts for one movie or episode).
- **Radarr / Sonarr** decide *which paths are protected*. The protected set is every current managed file in the library: Radarr’s `movieFile` on each movie (one current file per movie), or Sonarr episode files still linked by `episodeFileId`. A match means “this path is some current managed file,” not “this title was imported twice.”
- A group is `protected` when **each** of its Plex paths is in that set. Those paths can be different files — this title’s file and another title’s file, a merged Plex item, or two names that still point at distinct files. Quarantine skips the whole group.
- **Reclaimspace** only moves files Plex lists that are *not* in the protected set.

For TV, Sonarr’s protected set ignores episode-file rows that are no longer the episode’s current `episodeFileId` (stale files after upgrades or renames).

## Movies

### 1. Dry run

```bash
python3 -m reclaimspace.media_duplicates \
  --report reports/movies-dry-run.json
```

Review `reports/movies-dry-run.json`:

- `ready_count` / `candidate_count` — how much would move
- `protected_count` — groups where every path is a current managed file
- `needs_review_count` — items to inspect manually
- Per group: `plex_paths`, `protected_paths`, `candidate_paths`

### 2. Quarantine

After reviewing the dry run:

```bash
python3 -m reclaimspace.media_duplicates \
  --quarantine \
  --report reports/movies-quarantine.json
```

Files move to:

```text
$QUARANTINE_ROOT/<run-id>/movies/<relative path under MOVIES_ROOT>
```

A manifest is written to:

```text
$QUARANTINE_ROOT/<run-id>/manifest.json
```

### 3. Needs-review report

```bash
python3 -m reclaimspace.media_duplicates review-report \
  reports/movies-quarantine.json \
  --output reports/movies-needs-review.json
```

## TV

TV libraries are large; Plex is queried in pages (default 500 episodes per request). If Plex returns HTTP 500, lower `--page-size`.

### 1. Dry run

```bash
python3 -m reclaimspace.media_duplicates tv \
  --report reports/tv-dry-run.json
```

The report also includes `plex_episode_part_count` and `sonarr_episode_file_count` for sanity checks.

### 2. Quarantine

```bash
python3 -m reclaimspace.media_duplicates tv \
  --quarantine \
  --report reports/tv-quarantine.json
```

Files move under:

```text
$QUARANTINE_ROOT/<run-id>/tv/<relative path under TV_ROOT>
```

If Plex lists a path that no longer exists on disk, the run skips it and records paths in `missing_source_paths` instead of failing.

## Rollback

Each quarantine run writes `manifest.json` with `source` and `destination` for every move. To restore a file manually:

```bash
mv "<destination>" "<source>"
```

Use the paths from the manifest for the run you want to undo.

## Running on Unraid with Docker

Host Python may be outdated; use a Python 3.10+ container and mount your media paths:

```bash
docker run --rm \
  --env-file /mnt/user/appdata/reclaimspace/.env \
  -v /mnt/user/appdata/reclaimspace:/work \
  -v /mnt/user/data:/mnt/user/data \
  -w /work \
  python:3.12-alpine \
  python -m reclaimspace.media_duplicates tv --report reports/tv-dry-run.json
```

- Mount `/mnt/user/data` read-only for dry runs.
- Mount read-write when using `--quarantine`.
- Ensure `MOVIES_ROOT`, `TV_ROOT`, and `QUARANTINE_ROOT` in `.env` match paths **inside** the container (usually the same as on the host when you bind-mount `/mnt/user/data`).

## Report JSON reference

Top-level fields (movies and TV):

| Field | Description |
|-------|-------------|
| `groups` | List of duplicate groups |
| `ready_count` | Groups with status `ready` |
| `candidate_count` | Total candidate file paths |
| `protected_count` | Groups with status `protected` |
| `needs_review_count` | Groups requiring manual review |
| `quarantined_count` | Files moved (quarantine runs only) |
| `quarantine_manifest` | Path to manifest JSON, or `null` |
| `missing_source_count` | Plex paths skipped (missing on disk) |
| `missing_source_paths` | List of skipped paths |

Each group includes `rating_key`, `title`, `year`, `status`, `reason`, `plex_paths`, `protected_paths`, and `candidate_paths`.

## Development

```bash
python3 -m unittest discover -s tests
```
