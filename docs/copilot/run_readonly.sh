#!/bin/bash
# Run read-only Copilot scout jobs from the primary checkout.
# Usage: run_readonly.sh <out-dir> <model> <brief> [<brief> ...]
#   brief = name of docs/copilot/briefs/<brief>.txt; common-readonly.txt is appended.
# Model: gpt-6-luna by default (2026-11-01 trial: ~1/6 the AI units of claude-sonnet-5.5
# for an equal-or-better scout). Use claude-sonnet-5.5 where caution beats breadth.
OUT="$1"; MODEL="${2:-gpt-6-luna}"; shift 2
B=/c/Users/Steph/Repos/vicinitideals/docs/copilot/briefs
mkdir -p "$OUT"; cd /c/Users/Steph/Repos/vicinitideals
for t in "$@"; do
  ( copilot -p "$(cat "$B/$t.txt" "$B/common-readonly.txt")" --model "$MODEL" --reasoning-effort medium \
      --allow-all-tools --deny-tool 'write' --deny-tool 'shell(git commit)' --deny-tool 'shell(git push)' \
      --deny-tool 'shell(git checkout)' --deny-tool 'shell(git reset)' --deny-tool 'shell(git stash)' \
      --output-format json --log-dir "$OUT/logs-$t" > "$OUT/$t.jsonl" 2>&1; echo "$t exit $?" ) &
  sleep 15
done
wait
for t in "$@"; do echo "=== $t"; PYTHONIOENCODING=utf-8 python -c "
import json,sys
last=None; aiu=None
for l in open(sys.argv[1],encoding='utf-8'):
    try: d=json.loads(l)
    except: continue
    if d.get('type')=='assistant.message' and d.get('data',{}).get('content'): last=d['data']['content']
    if d.get('type')=='session.usage_checkpoint': aiu=d['data'].get('totalNanoAiu')
print('AI units', (aiu or 0)/1e9); print(last)" "$OUT/$t.jsonl"; done
