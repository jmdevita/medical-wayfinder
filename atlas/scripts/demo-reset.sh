#!/usr/bin/env bash
#
# Host-side cron job. Restarts the demo Atlas container; the container's
# entrypoint then re-seeds /data from /data-seed before uvicorn comes back up.
# That gives you paperless-ngx-style demo semantics with no per-app reset
# logic — restart == reset.
#
# Wire to host cron:
#
#   crontab -e
#   # daily at 06:00 UTC
#   0 6 * * * /opt/atlas/atlas/scripts/demo-reset.sh >> /var/log/atlas-demo-reset.log 2>&1
#
# Or systemd timer (preferred on modern hosts — see DEPLOY-DEMO.md).
#
# This script is idempotent and safe to run multiple times.

set -euo pipefail

# Path to the directory containing docker-compose.demo.yml. Override via env
# if you've laid the repo out somewhere other than /opt/atlas.
ATLAS_DIR="${ATLAS_DIR:-/opt/atlas/atlas}"
COMPOSE_FILE="${ATLAS_DIR}/docker-compose.demo.yml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found at $COMPOSE_FILE" >&2
  echo "Set ATLAS_DIR to the directory containing docker-compose.demo.yml" >&2
  exit 1
fi

cd "$ATLAS_DIR"

echo "[demo-reset] $(date -u +%FT%TZ) restarting atlas container"
docker compose -f docker-compose.demo.yml restart atlas

# Optional: prune leftover anonymous volumes that piled up from previous
# restarts. The demo compose doesn't declare volumes, so this is a belt-and-
# suspenders cleanup against docker accidentally retaining state.
echo "[demo-reset] pruning dangling volumes"
docker volume prune -f --filter "label!=keep" >/dev/null

# Wait until the container reports healthy. We poll for up to 60s; uvicorn
# usually comes up in <5s after the reseed.
echo "[demo-reset] waiting for healthcheck"
for i in $(seq 1 30); do
  status=$(docker inspect --format '{{.State.Health.Status}}' atlas-demo 2>/dev/null || echo "missing")
  if [[ "$status" == "healthy" ]]; then
    echo "[demo-reset] healthy after $((i*2))s"
    exit 0
  fi
  sleep 2
done

echo "[demo-reset] WARN: container did not reach healthy state in 60s" >&2
echo "[demo-reset] current status: $(docker inspect --format '{{.State.Status}} / health={{.State.Health.Status}}' atlas-demo 2>&1 || echo missing)" >&2
exit 1
