# Unraid Community Applications

This guide walks through listing **Reclaimspace** in the official Unraid **Community Applications** (CA) store.

## Prerequisites

Complete these before submitting:

| Requirement | Status |
|-------------|--------|
| Public GitHub repo `romwil/reclaimspace` | Required |
| OSI license ([MIT](../LICENSE)) | Required |
| Docker image on Docker Hub `romwil/reclaimspace` | Required for end users |
| `ca_profile.xml` in repo root | Included |
| `templates/reclaimspace.xml` with valid `TemplateURL` | Included |
| `icon.svg` in repo root | Included |

Publish the Docker image first — see [RELEASE.md](RELEASE.md). CA users install by pulling your Hub image; a template alone is not enough.

## Repository layout (CA)

```text
reclaimspace/
  ca_profile.xml              # Repository profile for CA
  icon.svg                    # Icon shown in CA
  templates/reclaimspace.xml  # Container template (canonical)
  unraid/reclaimspace.xml     # Legacy path (same template; kept for old links)
```

The canonical template URL is:

`https://raw.githubusercontent.com/romwil/reclaimspace/main/templates/reclaimspace.xml`

## Install without CA (template URL)

Users can add the template before CA approval:

1. Unraid → **Docker** → **Add Container** → **Template Repositories** (or paste template URL if your Unraid version supports it).
2. Alternatively: **Apps** → **Previous Apps** → install from custom template URL above.

Or use the in-repo script on the server:

```bash
cd /mnt/user/appdata/reclaimspace
./docker-run.sh
```

## Submit to Community Applications

Modern submissions use the Unraid CA portal (not a manual PR to `community.applications` in most cases).

### Step 1 — Sign in

Open **[https://ca.unraid.net/submit](https://ca.unraid.net/submit)** and sign in with your Unraid account.

### Step 2 — Add repository

1. Choose **Add repository** (or **New submission**).
2. Enter: `https://github.com/romwil/reclaimspace`
3. The scanner looks for:
   - `ca_profile.xml` (non-empty `<Profile>`)
   - At least one valid template under `templates/` with a `TemplateURL` pointing to the raw XML on GitHub

### Step 3 — Validate and scan

1. Run **Validate** — fix XML or profile errors.
2. Run **Scan** — resolve warnings (placeholder icon text, missing support links, etc.).

Helpful references:

- [Builder guide](https://ca.unraid.net/submit/help/builders)
- [Repository info XML](https://ca.unraid.net/submit/help/repository-info-xml)
- [Starter template repo](https://github.com/unraid/unraid-community-apps-starter)

### Step 4 — Submit for review

Submit when scan passes. Moderators may request changes (icon, overview text, category, support link).

### Step 5 — After approval

1. Users find **Reclaimspace** under **Apps** → search `reclaimspace`.
2. Install maps paths from `templates/reclaimspace.xml` defaults; users should confirm **Configuration** in the web UI (`http://[IP]:8777/config`).
3. Monitor [GitHub Issues](https://github.com/romwil/reclaimspace/issues) for support.

## Optional: support forum thread

Create a thread under [Unraid → Plugin Support](https://forums.unraid.net/forum/85-plugin-support/) and add the URL to `ca_profile.xml` as `<Forum>...</Forum>` for visibility in CA.

## Updating the CA listing

1. Merge changes to `main` (template, overview, version).
2. Push a new Docker tag to Hub (`romwil/reclaimspace:latest` and version tag).
3. Re-run **Scan** in the CA portal if you changed templates or profile metadata.

## Container paths checklist

Tell users to verify in **Configuration** (`/config`):

| Setting | Typical container value |
|---------|-------------------------|
| Movies root | `/media/movies` |
| TV root | `/media/tv` |
| Quarantine root | `/quarantine` |

Host paths are set in the Docker template volume mappings, not in these fields.

## Troubleshooting CA scan

| Issue | Fix |
|-------|-----|
| Missing `ca_profile.xml` | Add file at repo root; push to `main` |
| Empty `<Profile>` | Add description in `ca_profile.xml` |
| Invalid `TemplateURL` | Must be raw GitHub URL to the exact XML file |
| Image pull fails | Publish `romwil/reclaimspace` on Docker Hub |
| Template not found | Ensure file is under `templates/`, not only `unraid/` |
