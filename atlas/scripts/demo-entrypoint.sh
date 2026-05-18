#!/usr/bin/env bash
#
# Public-demo container entrypoint for Atlas.
#
# Restores Atlas to a pristine state on every container boot, then execs the
# normal FastAPI server. Pair with a daily restart (systemd timer, host
# cron + `docker compose restart`, or any other scheduler) and you get
# paperless-ngx-style demo semantics: judges can edit anything, state resets
# at the scheduled cadence.
#
# Reset strategy: re-seed /data from the image's bundled /data-seed snapshot.
# /data-seed is baked into the image by the Dockerfile, so it survives
# container restarts and accurately reflects the most recent deploy. The data
# volume itself can be ephemeral — we don't rely on disk persistence.
#
# Required env on the deployment:
#   ATLAS_DEMO_MODE=true         enables the demo_block dependency in routes
#   ATLAS_AUTH_ENABLED=          (unset / false) — public no-auth demo
#   ATLAS_CORS_ORIGINS=          set to the demo URL when frontend is separate
#
# Optional:
#   ATLAS_DEMO_RESEED=skip       set to skip the re-seed (useful for debugging
#                                container restarts without losing in-flight
#                                experimentation)

set -euo pipefail

DATA_DIR="${ATLAS_DATA_DIR:-/data}"
SEED_DIR="${ATLAS_SEED_DIR:-/data-seed}"

echo "[demo-entrypoint] $(date -u +%FT%TZ) starting"

if [[ "${ATLAS_DEMO_RESEED:-}" == "skip" ]]; then
  echo "[demo-entrypoint] ATLAS_DEMO_RESEED=skip — leaving /data alone"
elif [[ -d "$SEED_DIR" ]]; then
  echo "[demo-entrypoint] re-seeding $DATA_DIR from $SEED_DIR"
  # rm -rf the contents but keep the mount point itself, then copy seed back.
  # `find ... -mindepth 1 -delete` is safer than `rm -rf $DATA_DIR/*` because
  # it handles hidden files and doesn't choke on an empty dir.
  find "$DATA_DIR" -mindepth 1 -delete 2>/dev/null || true
  cp -a "$SEED_DIR"/. "$DATA_DIR"/
  echo "[demo-entrypoint] reseed complete ($(du -sh "$DATA_DIR" | cut -f1) restored)"
else
  echo "[demo-entrypoint] WARN: $SEED_DIR not found — running with whatever's in $DATA_DIR"
fi

# Helpful banner in the logs so a tail-on-restart confirms what mode we're in.
echo "[demo-entrypoint] ATLAS_DEMO_MODE=${ATLAS_DEMO_MODE:-<unset>}"
echo "[demo-entrypoint] ATLAS_AUTH_ENABLED=${ATLAS_AUTH_ENABLED:-<unset>}"
echo "[demo-entrypoint] ATLAS_RATE_LIMIT_ENABLED=${ATLAS_RATE_LIMIT_ENABLED:-<unset>}"

# Hand off to uvicorn. Single worker is correct for the demo — no Redis,
# no cross-worker state.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --app-dir /app/atlas/backend
