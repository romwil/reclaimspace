#!/bin/sh
# Build and push Reclaimspace to Docker Hub (romwil/reclaimspace).
set -eu

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

VERSION="$(python3 -c 'from reclaimspace._version import __version__; print(__version__)' 2>/dev/null || true)"
if [ -z "$VERSION" ]; then
  VERSION="${1:-latest}"
fi

IMAGE="${DOCKER_IMAGE:-romwil/reclaimspace}"

echo "Building ${IMAGE}:${VERSION} and ${IMAGE}:latest ..."
docker build -t "${IMAGE}:${VERSION}" -t "${IMAGE}:latest" .

if ! docker info 2>/dev/null | grep -q 'Username:'; then
  echo ""
  echo "Not logged in to Docker Hub. Run:"
  echo "  docker login"
  echo "Then re-run: ./docker-publish.sh"
  exit 1
fi

echo "Pushing ${IMAGE}:${VERSION} ..."
docker push "${IMAGE}:${VERSION}"
echo "Pushing ${IMAGE}:latest ..."
docker push "${IMAGE}:latest"

echo ""
echo "Published:"
echo "  ${IMAGE}:${VERSION}"
echo "  ${IMAGE}:latest"
