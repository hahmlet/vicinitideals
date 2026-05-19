#!/usr/bin/env bash
# Shared helpers for .claude hooks. Source with: source "$(dirname "$0")/lib.sh"

STATE_DIR=".claude/state"
MARKER="$STATE_DIR/fixloop.json"
API_IMAGE="vicinitideals-api"
HEALTH_URL="http://localhost:8001/health"

# ── Marker helpers ────────────────────────────────────────────────────────────

marker_get() {
    local key="$1"
    if [[ -f "$MARKER" ]]; then
        python3 -c "import json,sys; d=json.load(open('$MARKER')); print(d.get('$key',''))" 2>/dev/null
    fi
}

marker_set() {
    # Usage: marker_set key1 val1 key2 val2 ...
    mkdir -p "$STATE_DIR"
    local tmp
    tmp=$(python3 -c "
import json, sys
try:
    d = json.load(open('$MARKER'))
except Exception:
    d = {}
args = sys.argv[1:]
for i in range(0, len(args), 2):
    k, v = args[i], args[i+1]
    if v in ('true','false'): d[k] = v == 'true'
    elif v.lstrip('-').isdigit(): d[k] = int(v)
    else: d[k] = v
print(json.dumps(d, indent=2))
" "$@") && echo "$tmp" > "$MARKER"
}

# ── Docker helpers ─────────────────────────────────────────────────────────────

have_docker() {
    docker info >/dev/null 2>&1
}

wait_for_health() {
    local retries="${1:-30}"
    local i=0
    while [[ $i -lt $retries ]]; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        ((i++))
    done
    return 1
}

ensure_env_file() {
    if [[ ! -f .env ]]; then
        if [[ -f .env.example ]]; then
            cp .env.example .env
            echo "[lib.sh] Created .env from .env.example — fill in secrets before running." >&2
        fi
    fi
}

ensure_pg_volume() {
    if ! docker volume inspect re-modeling-postgres-data >/dev/null 2>&1; then
        docker volume create re-modeling-postgres-data >/dev/null
    fi
}

run_migrations() {
    docker compose exec -T api python -m alembic upgrade head
}

seed_e2e_user() {
    docker compose exec -T api python -m app.scripts.seed_e2e_user 2>/dev/null || true
}

api_reload() {
    # With source mount active, just restart; otherwise rebuild
    docker compose restart api 2>/dev/null || docker compose up -d --build api
}

compose_up() {
    docker compose up -d --no-build postgres redis api 2>/dev/null
}
