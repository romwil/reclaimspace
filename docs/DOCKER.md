# Docker and Unraid

Reclaimspace ships as a container with a web UI on port **8777**. Settings are stored in `/config/settings.json`; scan reports are written to `/config/reports/`.

**Do not commit `config/settings.json`.** It contains API tokens. The repo ships `config/settings.example.json` as a template; real settings stay in your appdata volume (see `.gitignore`).

## Security (no built-in auth)

The web UI is intended for **trusted networks** (home LAN, Unraid). Do not expose port 8777 to the internet without a reverse proxy that adds authentication (Traefik, NPM, etc.).

| Page | URL |
|------|-----|
| Dashboard | `http://<host>:8777/` |
| Configuration | `http://<host>:8777/config` |

See [ONBOARDING.md](ONBOARDING.md) and [WEB_UI.md](WEB_UI.md).

## Quick start (Unraid / no Compose)

Many Unraid installs do not include `docker compose`. Use the helper script:

```bash
cd /mnt/user/appdata/reclaimspace
cp .env.example .env   # optional: seed API keys for first boot
chmod +x docker-run.sh docker-stop.sh
mkdir -p config
./docker-run.sh
```

Stop the container:

```bash
./docker-stop.sh
```

Open `http://<host>:8777/`, complete the **setup wizard**, then run a **dry run** before **quarantine**.

The script mounts libraries at `/media/movies`, `/media/tv`, and `/quarantine` inside the container. Optional `.env` values seed Plex/*arr URLs and API keys.

## Quick start (Docker Compose)

If `docker compose` or `docker-compose` is available:

```bash
git clone https://github.com/romwil/reclaimspace.git
cd reclaimspace
cp .env.example .env
docker compose build && docker compose up -d
```

Default compose mounts:

| Container path | Purpose |
|----------------|---------|
| `/config` | `settings.json` and JSON reports |
| `/media/movies` | Movie library |
| `/media/tv` | TV library |
| `/quarantine` | Quarantine destination |

Set **Movies root**, **TV root**, and **Quarantine root** in **Configuration** to `/media/movies`, `/media/tv`, and `/quarantine` unless you use custom mounts.

## Docker Hub image

```bash
docker pull romwil/reclaimspace:latest
# or a pinned release:
docker pull romwil/reclaimspace:1.2.0
```

Publishing new tags is documented in [RELEASE.md](RELEASE.md).

## Unraid Community Applications

1. Publish the image to Docker Hub (`romwil/reclaimspace`).
2. Ensure `main` on GitHub has `ca_profile.xml` and `templates/reclaimspace.xml`.
3. Submit at [ca.unraid.net/submit](https://ca.unraid.net/submit) — see [UNRAID_CA.md](UNRAID_CA.md).

Until CA approval, install via:

- **Apps** → custom template: `https://raw.githubusercontent.com/romwil/reclaimspace/main/templates/reclaimspace.xml`
- Or clone the repo and run `./docker-run.sh`

Legacy template path: `unraid/reclaimspace.xml` (same content; prefer `templates/` for CA).

## CLI in the container

```bash
docker exec -it reclaimspace media-duplicates --help
```

The web UI uses the same core logic as the CLI.
