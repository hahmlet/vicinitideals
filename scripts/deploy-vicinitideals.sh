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

echo "==> Running post-deploy smoke checks..."
sleep 5
docker compose run --rm -e POST_DEPLOY_BASE_URL=http://127.0.0.1:8000 api python scripts/post_deploy_smoke.py \
  || echo "WARNING: post-deploy smoke check failed — check logs above"

echo "==> Deploy complete."
