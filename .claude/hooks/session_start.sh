#!/usr/bin/env bash
# Runs at session start: fast sync prep, then ensure_stack in background.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)" 2>/dev/null || exit 0
source "$(dirname "$0")/lib.sh"

# Fast sync steps (no docker needed)
ensure_env_file

# Ensure override file exists for live source mounts
if ! [[ -f docker-compose.override.yml ]]; then
    cat > docker-compose.override.yml <<'YAML'
services:
  api:
    volumes:
      - ./app:/app/app
      - ./alembic:/app/alembic
YAML
fi

# Launch stack bring-up in background (non-blocking)
if have_docker; then
    bash "$(dirname "$0")/ensure_stack.sh" &>/dev/null &
fi

exit 0
