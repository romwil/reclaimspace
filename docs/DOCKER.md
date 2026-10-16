# Docker and Unraid

Reclaimspace ships as a container with a web UI on port **8777**. Settings are stored in `/config/settings.json`; scan reports are written to `/config/reports/`.

Two modes share the container. **Media** quarantines Plex duplicates and never deletes files. **Appdata** can quarantine leftover folders, and **Delete** and **Purge** permanently remove them.

**Do not commit `config/settings.json`.** It contains API tokens. The repo ships `config/settings.example.json` as a template; real settings stay in your appdata volume (see `.gitignore`).

## Security (no built-in auth)

The web UI is intended for **trusted networks** (home LAN, Unraid). Do not expose port 8777 to the internet without a reverse proxy that adds authentication (Traefik, NPM, etc.).

| Page | URL |
|------|-----|
| Media | `http://<host>:8777/` |
| Appdata | `http://<host>:8777/appdata` |
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

The script mounts libraries at `/media/movies`, `/media/tv`, and `/quarantine` inside the container. It also mounts `/mnt/cache/appdata` at `/appdata` and `/mnt/user/data/code` at `/code`. It does not mount the Docker socket. Optional `.env` values seed Plex/*arr URLs and API keys.

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
| `/quarantine` | Media quarantine destination |
| `/appdata` | Appdata share, from `/mnt/cache/appdata` |
| `/code` | Migrate destination, from `/mnt/user/data/code` |

Set **Movies root**, **TV root**, and **Quarantine root** in **Configuration** to `/media/movies`, `/media/tv`, and `/quarantine` unless you use custom mounts. Appdata root defaults to `/appdata` and the code root to `/code`.

## Appdata

Appdata reads container mounts, then works on the filesystem mounts above. Host paths `/mnt/user/appdata/<name>` and `/mnt/cache/appdata/<name>` are the same folder inside `/appdata`. Sizing, explore, migrate, quarantine, delete, and restore use those mounts. A mount of the whole share protects every folder.

### Unraid API key

On Unraid 7.2+, set the Unraid API URL and key under **Configuration → Appdata**. Create the key with only `DOCKER:READ_ANY`. That permission lists containers and their mounts, including stopped containers, which is all this scan reads.

**Test Unraid API** sends one read, `docker { containers { id } }`, and reports reachable, unauthorized, or the container count. It does not return mounts.

### Docker socket fallback

Other Docker hosts can set **Docker socket** in Configuration, or `DOCKER_SOCKET` (usually `/var/run/docker.sock`), and mount that socket. This is optional. Leave it off the default Unraid template. Mounting the socket read-only still lets the daemon accept writes from anyone who can open the socket.

```yaml
# Optional fallback. Not part of the Unraid template.
services:
  reclaimspace:
    environment:
      DOCKER_SOCKET: /var/run/docker.sock
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

If neither the Unraid API nor an explicit socket is available, the scan fails. It does not treat every folder as unused.

### Workspace migrate

**Migrate** moves a whole unused top-level folder from `/appdata/<name>` to `/code/<name>` (host `/mnt/user/data/code/<name>`). A `.git` directory is enough to mark it as code. Otherwise the folder needs at least two of `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, a `*.sln` file, or `.code-workspace`. The **Code** badge is advisory. Nothing moves until you confirm, and a container that still mounts the folder blocks the move.

**Delete** and **Purge** are permanent. **Media** never deletes files.

## Docker Hub image

```bash
docker pull romwil/reclaimspace:latest
# or a pinned release:
docker pull romwil/reclaimspace:1.4.0
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
