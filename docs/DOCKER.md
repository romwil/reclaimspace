# Docker and Unraid

Reclaimspace ships as a container with a web UI on port **8777**. Settings are stored in `/config/settings.json`; scan reports are written to `/config/reports/`.

**Do not commit `config/settings.json`.** It contains API tokens. The repo ships `config/settings.example.json` as a template; real settings stay in your appdata volume (see `.gitignore`).

## Quick start (Unraid / no Compose)

Many Unraid installs do not include `docker compose`. Use the helper script:

```bash
cd /mnt/user/appdata/reclaimspace
cp .env.example .env   # then edit with your tokens (optional if you configure in the UI)
chmod +x docker-run.sh docker-stop.sh
mkdir -p config
./docker-run.sh
```

Stop the container:

```bash
./docker-stop.sh
```

Open `http://<host>:8777/`, complete **Configuration**, use **Load Plex libraries** to find section keys, then run a **Dry run** before **Quarantine**.

The script mounts your libraries at `/media/movies`, `/media/tv`, and `/quarantine` inside the container and sets path mappings accordingly. Your existing host `.env` is used for Plex/*arr URLs and API keys only.

## Quick start (Docker Compose)

If `docker compose` or `docker-compose` is available:

```bash
cd reclaimspace
cp .env.example .env
docker compose build && docker compose up -d
# or: docker-compose build && docker-compose up -d
```

When using Compose with a host `.env` that sets `MOVIES_ROOT=/mnt/user/...`, override container paths in the UI to `/media/movies`, `/media/tv`, and `/quarantine`, or set those variables in a compose override file.

Default compose mounts:

| Container path | Purpose |
|----------------|---------|
| `/config` | `settings.json` and JSON reports |
| `/media/movies` | Movie library (set **Movies root** to `/media/movies` in the UI) |
| `/media/tv` | TV library |
| `/quarantine` | Quarantine destination |

Adjust `MOVIES_PATH`, `TV_PATH`, `QUARANTINE_PATH`, and `CONFIG_PATH` in your environment or `docker-compose.yml` overrides.

## Unraid Community Applications

1. Add the template URL from the repo (`unraid/reclaimspace.xml`) or install from CA when published.
2. Map **Config** to e.g. `/mnt/user/appdata/reclaimspace/config`.
3. Map library and quarantine paths to match your server.
4. Set **Movies root**, **TV root**, and **Quarantine root** in the UI to the container paths (`/media/movies`, `/media/tv`, `/quarantine`) unless you use custom mounts.
5. Optional template variables (`PLEX_URL`, tokens, etc.) seed settings; the web UI can change them and saves to `settings.json`.

## Security

The web UI has **no built-in authentication**. Run on a trusted LAN, bind to localhost and reverse-proxy with auth, or restrict with a firewall. Do not expose port 8777 directly to the internet.

## CLI in the container

```bash
docker exec -it reclaimspace media-duplicates --help
```

The web UI uses the same core logic as the CLI.
