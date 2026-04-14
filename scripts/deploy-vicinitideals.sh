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

echo "==> Verifying health..."
sleep 5
curl -sf http://localhost:8001/health && echo "" && echo "Health check passed." || echo "WARNING: health check failed — check logs"

echo "==> Deploy complete."
