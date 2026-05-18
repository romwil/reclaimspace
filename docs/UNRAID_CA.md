# Unraid Community Applications

This guide walks through listing **Reclaimspace** in the official Unraid **Community Applications** (CA) store.

## Prerequisites checklist

| Requirement | Status |
|-------------|--------|
| Public GitHub repo `romwil/reclaimspace` | Required |
| OSI license ([MIT](../LICENSE)) | Required |
| Docker image on Docker Hub `romwil/reclaimspace:latest` and `romwil/reclaimspace:1.2.0` | Required |
| `ca_profile.xml` in repo root (non-empty `<Profile>`) | Included |
| `templates/reclaimspace.xml` with valid `TemplateURL`, `<Description>`, `:latest` image | Included |
| Icon `reclaimspace_icon.jpg` at repo root | Included |

Publish images with `./docker-publish.sh` after `docker login` — see [RELEASE.md](RELEASE.md).

## Repository layout (CA)

```text
reclaimspace/
  ca_profile.xml                 # Repository profile for CA
  reclaimspace_icon.jpg          # Icon shown in CA and templates
  icon.svg                       # Optional legacy icon (not used by CA)
  templates/reclaimspace.xml     # Container template (canonical)
  unraid/reclaimspace.xml        # Legacy path (kept in sync)
```

Canonical template URL:

`https://raw.githubusercontent.com/romwil/reclaimspace/main/templates/reclaimspace.xml`

## Submit to Community Applications

1. Open **[https://ca.unraid.net/submit/new](https://ca.unraid.net/submit/new)** and sign in.
2. **Add repository:** `https://github.com/romwil/reclaimspace`
3. **Validate** → **Scan** → fix any warnings.
4. **Submit** for moderator review.

References: [Builder guide](https://ca.unraid.net/submit/help/builders) · [Repository XML](https://ca.unraid.net/submit/help/repository-xml) · [Repository info XML](https://ca.unraid.net/submit/help/repository-info-xml)

## Support links

- **GitHub Issues** (primary): https://github.com/romwil/reclaimspace/issues — listed in `ca_profile.xml` as `<Forum>` and in template `<Support>`.
- **Unraid forum thread (optional):** If you create a dedicated thread under [Plugin Support](https://forums.unraid.net/forum/85-plugin-support/), replace the `<Forum>` URL in `ca_profile.xml` with that thread link.

## GitHub Actions — Docker Hub auto-publish

Add repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `DOCKERHUB_USERNAME` | Your Docker Hub username (`romwil`) |
| `DOCKERHUB_TOKEN` | Docker Hub access token ([create here](https://hub.docker.com/settings/security)) |

Then either:

- Push a version tag: `git tag v1.2.1 && git push origin v1.2.1` (runs [.github/workflows/release.yml](../.github/workflows/release.yml)), or
- **Actions** → **Release** → **Run workflow** and enter the version (e.g. `1.2.0`).

One-time setup from the CLI:

```bash
gh secret set DOCKERHUB_USERNAME --body "romwil"
gh secret set DOCKERHUB_TOKEN --body "YOUR_DOCKER_HUB_TOKEN"
```

## After approval

1. Users install from **Apps** → search `reclaimspace`.
2. Open Web UI → **Configuration** — confirm `/media/movies`, `/media/tv`, `/quarantine`.
3. Run a dry run before quarantine.

## Troubleshooting CA scan

| Issue | Fix |
|-------|-----|
| Image pull fails | Push `romwil/reclaimspace:latest` and `romwil/reclaimspace:1.2.0` |
| Missing `<Description>` | Use `templates/reclaimspace.xml` on `main` |
| Invalid `TemplateURL` | Must be raw GitHub URL to `templates/reclaimspace.xml` |
| Empty `<Profile>` | Edit `ca_profile.xml` |
