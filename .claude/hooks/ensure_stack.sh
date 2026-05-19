#!/usr/bin/env bash
# Idempotent local dev stack bring-up. Safe to run multiple times.
# Writes .claude/state/stack.ready when healthy.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source "$(dirname "$0")/lib.sh"

READY_FLAG="$STATE_DIR/stack.ready"

if [[ -f "$READY_FLAG" ]]; then
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        exit 0
    fi
    rm -f "$READY_FLAG"
fi

echo "[ensure_stack] Starting local dev stack..." >&2

if ! have_docker; then
    echo "[ensure_stack] Docker not available — skipping local stack." >&2
    exit 0
fi

ensure_env_file
ensure_pg_volume

# Bring up postgres + redis first, then api
docker compose up -d postgres redis >/dev/null 2>&1 || true
sleep 2
docker compose up -d api >/dev/null 2>&1 || true

if ! wait_for_health 30; then
    echo "[ensure_stack] API did not become healthy — check docker compose logs." >&2
    exit 1
fi

run_migrations || true
seed_e2e_user || true

mkdir -p "$STATE_DIR"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$READY_FLAG"
echo "[ensure_stack] Stack ready at $HEALTH_URL" >&2
