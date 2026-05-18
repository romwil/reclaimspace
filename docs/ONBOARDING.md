# Onboarding wizard

On first visit, Reclaimspace shows a **setup wizard** instead of the dashboard. After you finish (or if you already had a working `settings.json`), you land on the main UI.

## Wizard steps

1. **Welcome** — how Reclaimspace works and LAN security note (no built-in login).
2. **Paths** — movies, TV, and quarantine roots inside the container (`/media/movies`, etc.).
3. **Plex** — URL, token, test connection, pick library keys for movies and TV.
4. **Radarr** — URL and API key with connectivity test.
5. **Sonarr** — URL and API key with connectivity test.
6. **Review** — confirm settings and auto-generated path mappings.
7. **First scan** — optional movies dry run, then open the dashboard.

## After onboarding

- **Dashboard** (`/`) — scans, jobs, reports, restore
- **Configuration** (`/config`) — edit settings anytime

See [WEB_UI.md](WEB_UI.md).

## Security

- Run on your LAN or behind a reverse proxy with authentication.
- API tokens are **not** returned by `GET /api/settings` (only `*_set` flags).
- Saving settings without re-entering a token keeps the stored secret.

## Re-run wizard

Click **Setup wizard** in the header (dashboard or configuration). This sets `setup_wizard_pending` so the wizard stays open even when credentials are already saved. API keys and paths in `settings.json` are kept.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/setup/status` | Onboarding flag and readiness checks |
| `POST /api/setup/reset` | Re-open wizard without clearing secrets |
| `POST /api/setup/validate-paths` | Verify library paths exist |
| `POST /api/setup/path-mappings` | Generate Unraid-style mappings |
| `POST /api/setup/test/plex` | Test Plex and list libraries |
| `POST /api/setup/test/radarr` | Test Radarr |
| `POST /api/setup/test/sonarr` | Test Sonarr |
