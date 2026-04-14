#!/usr/bin/env bash
# Run the Fairview Zone Painter on VM 114.
# Usage: bash tools/zone_painter/run.sh
#
# Prerequisites (run once):
#   pip install fastapi uvicorn asyncpg python-dotenv
#
# The tool reads DATABASE_URL from re-modeling/.env automatically.
# Access at http://192.168.1.114:8765 from anywhere on the LAN.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"

echo "Starting Fairview Zone Painter on port 8765..."
python -m uvicorn tools.zone_painter.main:app --host 0.0.0.0 --port 8765 --reload
