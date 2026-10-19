#!/usr/bin/env bash
#
# FORENSIGHT AI — VPS provisioning.
#
# Run as root on a fresh Ubuntu 22.04/24.04 server:
#   curl -fsSL <repo>/deploy.sh | sudo bash
# or, from a checkout:
#   sudo bash deploy.sh
#
# Installs Docker if missing, opens the HTTP port, and starts the stack.
# Safe to re-run: existing containers are rebuilt in place and the named
# volumes (database, evidence store, model artifacts) are left untouched.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/foresight}"
FRONTEND_PORT="${FRONTEND_PORT:-80}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------
# 1. Dependencies
# --------------------------------------------------------------------------
log "Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker from the official repository"
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl git
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    # shellcheck disable=SC1091
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                         docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
else
    systemctl enable --now docker 2>/dev/null || true
fi

docker compose version >/dev/null 2>&1 || {
    echo "ERROR: the docker compose plugin is required." >&2
    exit 1
}

# --------------------------------------------------------------------------
# 2. Application directory
# --------------------------------------------------------------------------
log "Preparing $APP_DIR"
mkdir -p "$APP_DIR"
if [ -n "${REPO_URL:-}" ]; then
    if [ -d "$APP_DIR/.git" ]; then
        log "Updating checkout"
        git -C "$APP_DIR" pull --ff-only
    else
        log "Cloning $REPO_URL"
        git clone --depth 1 "$REPO_URL" "$APP_DIR"
    fi
else
    echo "Set REPO_URL, or run this script from inside a checkout." >&2
    exit 1
fi

# --------------------------------------------------------------------------
# 3. Firewall: allow the published port
# --------------------------------------------------------------------------
log "Opening port $FRONTEND_PORT"
if command -v ufw >/dev/null 2>&1; then
    ufw allow "$FRONTEND_PORT/tcp" >/dev/null 2>&1 || true
fi

# --------------------------------------------------------------------------
# 4. Build and start
# --------------------------------------------------------------------------
log "Building images and starting the stack"
cd "$APP_DIR"
# --wait blocks until the backend reports healthy and the frontend is up.
docker compose up -d --build --wait

# --------------------------------------------------------------------------
# 5. Report
# --------------------------------------------------------------------------
log "Deployment status"
docker compose ps

cat <<EOF

FORENSIGHT AI is deploying.

  Application : $APP_DIR
  Port        : $FRONTEND_PORT
  Backup      : docker run --rm -v foresight_foresight-data:/data -v \
                  "\$PWD:/out" alpine tar czf /out/foresight-backup.tgz -C /data .

Notes:
  * Set CORS_ORIGINS in $APP_DIR/.env to the public URL if the frontend is
    ever served from a different origin than the API.
  * To update: cd $APP_DIR && git pull && docker compose up -d --build
  * Logs:    docker compose logs -f backend
  * Stop:    docker compose down      (keeps data; use 'down -v' to delete)

EOF