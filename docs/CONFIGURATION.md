# Configuration reference

Reclaimspace reads settings from environment variables. Copy [`.env.example`](../.env.example) to `.env` in the project directory (or export the variables in your shell).

## Plex

| Variable | Required | Description |
|----------|----------|-------------|
| `PLEX_URL` | Yes | Plex server base URL, e.g. `http://10.0.0.10:32400` |
| `PLEX_TOKEN` | Yes | Plex token with access to your movie and TV libraries |
| `PLEX_MOVIE_SECTION` | No | Plex library section **key** for movies. Leave blank to auto-select the first `movie` library. |
| `PLEX_TV_SECTION` | For TV | Plex library section **key** for TV shows (numeric key from `/library/sections`, not the display title). |

### Finding Plex section keys

```bash
curl -s "$PLEX_URL/library/sections?X-Plex-Token=$PLEX_TOKEN" | head
```

Or list sections with the tool’s Plex client (see README). Use the `key` attribute (e.g. `1` for Movies, `2` for TV Shows), not the library title.

## Radarr (movies)

| Variable | Required | Description |
|----------|----------|-------------|
| `RADARR_URL` | For movies | Radarr base URL, e.g. `http://10.0.0.10:7878` |
| `RADARR_API_KEY` | For movies | API key from Radarr → Settings → General → Security |

## Sonarr (TV)

| Variable | Required | Description |
|----------|----------|-------------|
| `SONARR_URL` | For TV | Sonarr base URL, e.g. `http://10.0.0.10:8989` |
| `SONARR_API_KEY` | For TV | API key from Sonarr → Settings → General → Security |

## Host paths

| Variable | Required | Description |
|----------|----------|-------------|
| `MOVIES_ROOT` | For movies | Host path to the movie library root that Plex and Radarr both refer to |
| `TV_ROOT` | For TV | Host path to the TV library root |
| `QUARANTINE_ROOT` | No | Where quarantined files are moved. Default: `./quarantine` under the project |

The process must be able to read `MOVIES_ROOT` / `TV_ROOT` and write to `QUARANTINE_ROOT`. When running in Docker, mount these host paths into the container.

## Path mappings

Plex and the *arr apps often report different path prefixes for the same file on disk.

| Variable | Required | Description |
|----------|----------|-------------|
| `PATH_MAPPINGS` | Recommended | Semicolon-separated `container=host` pairs for movies |
| `TV_PATH_MAPPINGS` | Recommended | Same format for TV |

### Format

```text
container_prefix=host_prefix;container_prefix=host_prefix
```

### Example (Unraid-style layout)

```bash
PATH_MAPPINGS=/data/media/movies=/mnt/user/data/media/movies;/movies=/mnt/user/data/media/movies
TV_PATH_MAPPINGS=/data/media/tv=/mnt/user/data/media/tv;/tv=/mnt/user/data/media/tv
```

| Source | Typical path |
|--------|----------------|
| Plex (movies) | `/data/media/movies/...` |
| Radarr | `/movies/...` |
| Plex (TV) | `/data/media/tv/...` |
| Sonarr | `/tv/...` |

Both prefixes for a library must normalize to the same path under `MOVIES_ROOT` or `TV_ROOT`.
