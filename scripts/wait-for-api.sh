#!/bin/bash
# Wait until the api container's own healthcheck reads "healthy".
# Run from the compose directory, after `docker compose up -d`.
# Exit 0 = healthy; exit 1 = unhealthy or timed out (message on stderr).
# Tunables: WAIT_TIMEOUT (seconds, default 120), WAIT_INTERVAL (seconds, default 3).
set -u

timeout="${WAIT_TIMEOUT:-120}"
interval="${WAIT_INTERVAL:-3}"
waited=0
status="no container yet"

while :; do
  cid="$(docker compose ps -q api 2>/dev/null | head -n1)"
  if [ -n "$cid" ]; then
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$cid" 2>/dev/null || echo unknown)"
    case "$status" in
      healthy)
        echo "api is healthy (waited ${waited}s)"
        exit 0
        ;;
      unhealthy | no-healthcheck)
        echo "ERROR: api container reports '$status' -- not waiting any longer" >&2
        exit 1
        ;;
    esac
  fi
  if [ "$waited" -ge "$timeout" ]; then
    echo "ERROR: api not healthy after ${timeout}s (last status: ${status})" >&2
    exit 1
  fi
  echo "waiting for api to become healthy (${status}, ${waited}s)..."
  sleep "$interval"
  waited=$((waited + interval))
done
