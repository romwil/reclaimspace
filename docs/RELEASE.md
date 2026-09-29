# Release process

Reclaimspace uses [Semantic Versioning](https://semver.org/). The version string lives in:

- `reclaimspace/_version.py`
- `pyproject.toml` (`[project].version`)

Keep these in sync before tagging.

## Cut a release

### 1. Prepare on a PR branch

Bump version in `_version.py` and `pyproject.toml`. Update `CHANGELOG.md` with the release
date and highlights. Add benefit-led notes at `docs/RELEASE_NOTES/vX.Y.Z.md` (see
`docs/RELEASE_NOTES/v1.2.0.md`). Refresh the README version badge / Hub tag mentions and
current-version pin examples in [UNRAID_CA.md](UNRAID_CA.md) / [DOCKER.md](DOCKER.md) when
shipping a new current version.

```bash
python3 -m unittest discover -s tests
```

Open a PR into `main` (branch protection — no direct pushes to `main`, including hotfixes).

### 2. After merge: tag and GitHub release

On `main` after the PR merges:

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0

gh release create v1.2.0 \
  --title "v1.2.0 — Web UI, wizard, reports, Unraid CA" \
  --notes-file docs/RELEASE_NOTES/v1.2.0.md
```

Or create the release in the GitHub UI and paste notes from `docs/RELEASE_NOTES/v1.2.0.md`.

### 3. Publish the Docker image

A version is not released until Hub has `romwil/reclaimspace:X.Y.Z` (and preferably `:latest`).

**Option A — GitHub Actions** (after configuring secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`):

Pushing tag `v*` triggers [.github/workflows/release.yml](../.github/workflows/release.yml) to build and push `romwil/reclaimspace:latest` and `romwil/reclaimspace:<version>`.

Configure secrets once:

```bash
gh secret set DOCKERHUB_USERNAME --body "romwil"
gh secret set DOCKERHUB_TOKEN --body "YOUR_DOCKER_HUB_TOKEN"
```

You can also run the workflow manually: **Actions** → **Release** → **Run workflow**.

**Option B — Manual** (`./docker-publish.sh` reads the version from `_version.py`):

```bash
docker login
./docker-publish.sh
```

Equivalent raw commands:

```bash
docker build -t romwil/reclaimspace:1.2.0 -t romwil/reclaimspace:latest .
docker push romwil/reclaimspace:1.2.0
docker push romwil/reclaimspace:latest
```

Unraid users pulling `romwil/reclaimspace` from Docker Hub need a published image before the CA listing is useful.

### 4. Community Applications (Unraid)

After the image is on Docker Hub and `main` contains `ca_profile.xml` + `templates/reclaimspace.xml`, follow [UNRAID_CA.md](UNRAID_CA.md).

## Hotfix workflow

1. Fix on a PR branch; bump patch version (e.g. `1.2.1`).
2. Update `CHANGELOG.md` and `docs/RELEASE_NOTES/v1.2.1.md`; merge PR into `main`.
3. Tag `v1.2.1`, push the tag, create the GitHub release, confirm Hub has `romwil/reclaimspace:1.2.1`.
