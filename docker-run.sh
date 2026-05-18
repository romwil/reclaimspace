#!/bin/sh
# Build and run Reclaimspace without Docker Compose (Unraid-friendly).
set -eu

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/config}"
SETTINGS_EXAMPLE="${SETTINGS_EXAMPLE:-$ROOT_DIR/config/settings.example.json}"
MOVIES_PATH="${MOVIES_PATH:-/mnt/user/data/media/movies}"
TV_PATH="${TV_PATH:-/mnt/user/data/media/tv}"
QUARANTINE_PATH="${QUARANTINE_PATH:-/mnt/user/data/quarantine}"
HOST_PORT="${HOST_PORT:-8777}"
IMAGE="${IMAGE:-reclaimspace:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-reclaimspace}"

# Container paths (must match volume mounts below).
CONTAINER_MOVIES_ROOT="/media/movies"
CONTAINER_TV_ROOT="/media/tv"
CONTAINER_QUARANTINE_ROOT="/quarantine"
CONTAINER_PATH_MAPPINGS="/data/media/movies=${CONTAINER_MOVIES_ROOT};/movies=${CONTAINER_MOVIES_ROOT}"
CONTAINER_TV_PATH_MAPPINGS="/data/media/tv=${CONTAINER_TV_ROOT};/tv=${CONTAINER_TV_ROOT}"

mkdir -p "$CONFIG_PATH"

# Seed settings from repo template (works when CONFIG_PATH is outside the clone).
if [ ! -f "$CONFIG_PATH/settings.example.json" ] && [ -f "$SETTINGS_EXAMPLE" ]; then
  cp "$SETTINGS_EXAMPLE" "$CONFIG_PATH/settings.example.json"
fi

if [ ! -f "$CONFIG_PATH/settings.json" ]; then
  if [ -f "$CONFIG_PATH/settings.example.json" ]; then
    cp "$CONFIG_PATH/settings.example.json" "$CONFIG_PATH/settings.json"
    echo "Created ${CONFIG_PATH}/settings.json from settings.example.json (edit in the web UI)."
  elif [ -f "$SETTINGS_EXAMPLE" ]; then
    cp "$SETTINGS_EXAMPLE" "$CONFIG_PATH/settings.json"
    echo "Created ${CONFIG_PATH}/settings.json from ${SETTINGS_EXAMPLE} (edit in the web UI)."
  fi
fi

# Load only service URLs/keys from .env (do not source the file — PATH_MAPPINGS contains ';').
read_env() {
  _key="$1"
  if [ ! -f .env ]; then
    return 0
  fi
  _line=$(grep -E "^[[:space:]]*${_key}=" .env | tail -n 1 || true)
  if [ -z "$_line" ]; then
    return 0
  fi
  _val=${_line#*=}
  # Trim optional surrounding quotes.
  case "$_val" in
    \"*\") _val=${_val#\"}; _val=${_val%\"} ;;
    \'*\') _val=${_val#\'}; _val=${_val%\'} ;;
  esac
  export "$_key=$_val"
}

for _env_key in \
  PLEX_URL PLEX_TOKEN PLEX_MOVIE_SECTION PLEX_TV_SECTION \
  RADARR_URL RADARR_API_KEY SONARR_URL SONARR_API_KEY
do
  read_env "$_env_key"
done

echo "Building image ${IMAGE}..."
docker build -t "$IMAGE" .

echo "Stopping existing container (if any)..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting ${CONTAINER_NAME} on port ${HOST_PORT}..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "${HOST_PORT}:8777" \
  -e DATA_DIR=/config \
  -e PORT=8777 \
  -e PLEX_URL="${PLEX_URL:-}" \
  -e PLEX_TOKEN="${PLEX_TOKEN:-}" \
  -e PLEX_MOVIE_SECTION="${PLEX_MOVIE_SECTION:-}" \
  -e PLEX_TV_SECTION="${PLEX_TV_SECTION:-}" \
  -e RADARR_URL="${RADARR_URL:-}" \
  -e RADARR_API_KEY="${RADARR_API_KEY:-}" \
  -e SONARR_URL="${SONARR_URL:-}" \
  -e SONARR_API_KEY="${SONARR_API_KEY:-}" \
  -e MOVIES_ROOT="${CONTAINER_MOVIES_ROOT}" \
  -e TV_ROOT="${CONTAINER_TV_ROOT}" \
  -e QUARANTINE_ROOT="${CONTAINER_QUARANTINE_ROOT}" \
  -e PATH_MAPPINGS="${CONTAINER_PATH_MAPPINGS}" \
  -e TV_PATH_MAPPINGS="${CONTAINER_TV_PATH_MAPPINGS}" \
  -v "${CONFIG_PATH}:/config" \
  -v "${MOVIES_PATH}:${CONTAINER_MOVIES_ROOT}" \
  -v "${TV_PATH}:${CONTAINER_TV_ROOT}" \
  -v "${QUARANTINE_PATH}:${CONTAINER_QUARANTINE_ROOT}" \
  "$IMAGE"

echo ""
echo "Reclaimspace is running."
echo "  Web UI:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):${HOST_PORT}/"
echo "  Logs:    docker logs -f ${CONTAINER_NAME}"
echo "  Stop:    docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}"
