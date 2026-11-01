#!/bin/bash
# Run read-only Copilot scout jobs from the primary checkout.
# Usage: run_readonly.sh <out-dir> <model> <brief> [<brief> ...]
#   brief = name of docs/copilot/briefs/<brief>.txt; common-readonly.txt is appended.
# Model: gpt-6-luna by default (2026-11-01 trial: ~1/6 the AI units of claude-sonnet-5.5
# for an equal-or-better scout). Use claude-sonnet-5.5 where caution beats breadth.
#
# An ALLOWLIST, not --allow-all-tools: a scout reads web pages (untrusted text), so it gets only
# read-and-fetch commands. No python, no find, no git that writes, no shell redirection; anything
# else is refused in this non-interactive mode.
OUT="$1"; MODEL="${2:-gpt-6-luna}"; shift 2
REPO=/c/Users/Steph/Repos/vicinitideals
B=$REPO/docs/copilot/briefs
ALLOW=()
for c in grep rg ls cat head tail wc sort uniq curl "git log" "git show" "git diff" "git grep" \
         Get-Content Select-String Get-ChildItem Measure-Object Invoke-RestMethod; do
  ALLOW+=(--allow-tool "shell($c)")
done
ALLOW+=(--allow-tool "url")
mkdir -p "$OUT"
for t in "$@"; do
  [[ "$t" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "bad brief name: $t"; exit 2; }
  [ -f "$B/$t.txt" ] || { echo "no brief: $B/$t.txt"; exit 2; }
done
cd "$REPO"
for t in "$@"; do
  ( copilot -p "$(cat "$B/$t.txt" "$B/common-readonly.txt")" --model "$MODEL" --reasoning-effort medium \
      "${ALLOW[@]}" --deny-tool 'write' \
      --output-format json --log-dir "$OUT/logs-$t" > "$OUT/$t.jsonl" 2>&1; echo "$t exit $?" ) &
  sleep 15
done
wait
# Parse the results from an empty directory with an isolated interpreter (no planted modules).
cd "$(mktemp -d)"
for t in "$@"; do echo "=== $t"; PYTHONIOENCODING=utf-8 python -I -c "
import json,sys
last=None; aiu=None
for l in open(sys.argv[1],encoding='utf-8'):
    try: d=json.loads(l)
    except ValueError: continue
    if d.get('type')=='assistant.message' and d.get('data',{}).get('content'): last=d['data']['content']
    if d.get('type')=='session.usage_checkpoint': aiu=d['data'].get('totalNanoAiu')
print('AI units', (aiu or 0)/1e9); print(last)" "$OUT/$t.jsonl"; done
