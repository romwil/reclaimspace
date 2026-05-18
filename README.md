# Reclaimspace

Reclaim disk space from duplicate media files in Plex libraries while keeping the single file Radarr or Sonarr manages.

Plex sometimes indexes more than one file per movie or episode (leftovers after upgrades, renames, or manual copies). Reclaimspace asks Plex which items have duplicates, asks your *arr app which file is authoritative, and **quarantines** everything else. Nothing is deleted—files are moved to a timestamped quarantine folder with a manifest for rollback.

## Features

- **Movies** — Plex + Radarr, default command
- **TV** — Plex (paged episode scan) + Sonarr (current `episodeFileId` only)
- **Dry run by default** — JSON reports before any file moves
- **Path mapping** — reconcile Plex container paths with Radarr/Sonarr paths on the host
- **Needs-review extraction** — separate report for ambiguous cases

## Requirements

- Python 3.10+
- Network access to Plex and Radarr (movies) and/or Sonarr (TV)
- API tokens for each service you use
- Read access to your media roots; write access to `QUARANTINE_ROOT` when quarantining

No third-party Python dependencies (stdlib only).

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
tests/
docs/
  CONFIGURATION.md
  USAGE.md
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
