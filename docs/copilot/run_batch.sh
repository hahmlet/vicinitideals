#!/bin/bash
N="$1"; cd /c/Users/Steph/Repos/vicinitideals-worktrees
for t in nul-note-posts e2e-waits test-hygiene flags-cache-geometry; do
  ( cd $t && copilot -p "$(cat "$N/$t.txt" "$N/common.txt")" --model auto --allow-all-tools --deny-tool 'shell(git push)' --add-dir /c/Users/Steph/Repos/vicinitideals/.venv --add-dir /c/Users/Steph/Repos/vicinitideals/data --output-format json --log-level debug --log-dir "$N/logs-$t" > "$N/$t.jsonl" 2>&1; echo "$t exit $?" ) &
  sleep 20
done
wait
for t in nul-note-posts e2e-waits test-hygiene flags-cache-geometry; do echo "=== $t"; git -C $t log --oneline origin/main..HEAD; PYTHONIOENCODING=utf-8 python -c "
import json,sys
last=None
for l in open(sys.argv[1],encoding='utf-8'):
    try: d=json.loads(l)
    except: continue
    if d.get('type')=='assistant.message' and d.get('data',{}).get('content'): last=d['data']['content']
print(last)" "$N/$t.jsonl"; done
