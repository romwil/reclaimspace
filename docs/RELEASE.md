# Release process

Reclaimspace uses [Semantic Versioning](https://semver.org/). The version string lives in:

- `reclaimspace/_version.py`
- `pyproject.toml` (`[project].version`)

Keep these in sync before tagging.

## Cut a release

### 1. Prepare the tree

```bash
cd reclaimspace
python3 -m unittest discover -s tests
```

Update `CHANGELOG.md` with the release date and highlights.

### 2. Commit and tag

```bash
git add -A
git commit -m "Release v1.2.0"
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin main
git push origin v1.2.0
```

### 3. Publish the Docker image

**Option A — GitHub Actions** (after configuring secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`):

Pushing tag `v*` triggers [.github/workflows/release.yml](../.github/workflows/release.yml) to build and push `romwil/reclaimspace:latest` and `romwil/reclaimspace:<version>`.

Configure secrets once:

```bash
gh secret set DOCKERHUB_USERNAME --body "romwil"
gh secret set DOCKERHUB_TOKEN --body "YOUR_DOCKER_HUB_TOKEN"
```

You can also run the workflow manually: **Actions** → **Release** → **Run workflow**.

**Option B — Manual:**

```bash
docker build -t romwil/reclaimspace:1.2.0 -t romwil/reclaimspace:latest .
docker push romwil/reclaimspace:1.2.0
docker push romwil/reclaimspace:latest
```

Unraid users pulling `romwil/reclaimspace` from Docker Hub need a published image before the CA listing is useful.

### 4. Create the GitHub release

```bash
gh release create v1.2.0 \
  --title "v1.2.0 — Web UI, wizard, reports, Unraid CA" \
  --notes-file docs/RELEASE_NOTES/v1.2.0.md
```

Or create the release in the GitHub UI and paste notes from `docs/RELEASE_NOTES/v1.2.0.md`.

### 5. Community Applications (Unraid)

After the image is on Docker Hub and `main` contains `ca_profile.xml` + `templates/reclaimspace.xml`, follow [UNRAID_CA.md](UNRAID_CA.md).

## Hotfix workflow

1. Fix on `main`, bump patch version (e.g. `1.2.1`).
2. Update `CHANGELOG.md`, tag `v1.2.1`, push, publish image, GitHub release.
