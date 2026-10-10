#!/bin/bash
# Deploy script for vicinitideals on VM 114.
# Install to /root/deploy-vicinitideals.sh and chmod +x.
# Usage: /root/deploy-vicinitideals.sh
set -e

STACK_DIR="/root/stacks/vicinitideals"

cd "$STACK_DIR"

echo "==> Pulling latest code..."
git pull origin main

echo "==> Building Docker images..."
docker compose build

echo "==> Running database migrations..."
docker compose run --rm api python -m alembic upgrade head

echo "==> Starting containers..."
docker compose up -d

echo "==> Pruning dangling images and stale build cache..."
# Keep disk usage stable across deploys. Only removes UNUSED images and cache;
# never touches volumes (postgres data is in a named volume).
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true

echo "==> Disk after prune:"
df -h / | tail -1

echo "==> Waiting for the api to become healthy..."
bash "$STACK_DIR/scripts/wait-for-api.sh" \
  || echo "WARNING: api never reported healthy -- the smoke below will likely fail for real"

echo "==> Running post-deploy smoke checks..."
docker compose run --rm -e POST_DEPLOY_BASE_URL=http://api:8000 api python scripts/post_deploy_smoke.py \
  || echo "WARNING: post-deploy smoke check failed — check logs above"

echo "==> Deploy complete."
