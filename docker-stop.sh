#!/bin/sh
set -eu
CONTAINER_NAME="${CONTAINER_NAME:-reclaimspace}"
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true
echo "Removed container ${CONTAINER_NAME}."
