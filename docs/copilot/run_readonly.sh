#!/bin/bash
# Run read-only Copilot scout jobs in a throwaway checkout of main.
# Usage: run_readonly.sh <out-dir> <model> <brief> [<brief> ...]
#   brief = name of docs/copilot/briefs/<brief>.txt; common-readonly.txt is appended.
# Model: gpt-6-luna by default (2026-11-01 trial: ~1/6 the AI units of claude-sonnet-5.5
# for an equal-or-better scout). Use claude-sonnet-5.5 where caution beats breadth.
#
# An ALLOWLIST, not --allow-all-tools: a scout reads web pages (untrusted text), so it gets only
# read commands and the built-in fetch tool. Anything else is refused in this non-interactive mode.
OUT="$1"; MODEL="${2:-gpt-6-luna}"; shift 2
REPO=/c/Users/Steph/Repos/vicinitideals
B=$REPO/docs/copilot/briefs
ALLOW=()
# Only commands with no run-a-program or write-a-file flag (no rg --pre, git --output, sort -o,
# curl -o); web pages come through Copilot's own fetch tool, limited to public-data hosts.
for c in grep ls cat head tail wc Get-Content Select-String Get-ChildItem Measure-Object; do
  ALLOW+=(--allow-tool "shell($c)")
done
for u in 'https://*.gov' 'https://*.or.us' 'https://*.arcgis.com' 'https://arcgis.com'          'https://*.portlandmaps.com' 'https://www.portlandmaps.com' 'https://*.oregonmetro.gov'          'https://*.municode.com' 'https://*.codepublishing.com' 'https://*.amlegal.com'          'https://*.ecode360.com' 'https://*.noaa.gov' 'https://*.usgs.gov' 'https://*.census.gov' 'https://*.fed.us' 'https://*.edu'; do
  ALLOW+=(--allow-url "$u")
done
mkdir -p "$OUT"
for t in "$@"; do
  [[ "$t" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "bad brief name: $t"; exit 2; }
  [ -f "$B/$t.txt" ] || { echo "no brief: $B/$t.txt"; exit 2; }
done
# Run in a throwaway checkout of main: no .env or other untracked files, nothing of the working copy.
# Copilot's own path rule keeps file reads inside this directory (no --allow-all-paths, no --add-dir),
# and the repository is public, so a page that talks the scout into sending a file sends nothing secret.
# The host list stays wildcard on .gov / .or.us / ArcGIS on purpose: a scout's job is to find city GIS
# hosts nobody has listed yet.
WT=$(mktemp -d)/scout; git -C "$REPO" worktree add -q --detach "$WT" main || exit 2
trap 'git -C "$REPO" worktree remove --force "$WT"' EXIT
cd "$WT"
for t in "$@"; do
  ( copilot -p "$(cat "$B/$t.txt" "$B/common-readonly.txt")" --model "$MODEL" --reasoning-effort medium \
      "${ALLOW[@]}" --deny-tool 'write' \
      --output-format json --log-dir "$OUT/logs-$t" > "$OUT/$t.jsonl" 2>&1; echo "$t exit $?" ) &
  sleep 15
done
wait
# Parse the results from an empty directory with an isolated interpreter (no planted modules).
cd "$(mktemp -d)"
for t in "$@"; do echo "=== $t"; python -I -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')  # -I ignores PYTHONIOENCODING
last=None; aiu=None
for l in open(sys.argv[1],encoding='utf-8'):
    try: d=json.loads(l)
    except ValueError: continue
    if d.get('type')=='assistant.message' and d.get('data',{}).get('content'): last=d['data']['content']
    if d.get('type')=='session.usage_checkpoint': aiu=d['data'].get('totalNanoAiu')
print('AI units', (aiu or 0)/1e9); print(last)" "$OUT/$t.jsonl"; done
