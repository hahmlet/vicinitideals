# Feature Plan: Pro Forma Import — File Result Caching

## Problem

Every time a user uploads a pro forma file, a Celery task spins up, sends the sheet data to Ollama twice (revenue + OpEx), and waits 15–60 seconds for a response. If the user:
- Uploads the same file a second time (to try again after a mistake)
- Refreshes and re-uploads the same file (before state persistence is implemented)
- Uploads the same file to a different deal

...they pay the full LLM cost again with no benefit.

Additionally, LLM outputs are **non-deterministic** — re-running the same file may produce slightly different category mappings or confidence scores each time, which is confusing if the user expected the same result.

A content-hash cache would: skip the LLM call for previously-seen files, return consistent results, and give the user explicit control to bust the cache when they actually want a fresh parse.

---

## How It Works

### Cache Key

SHA-256 hash of the raw file bytes. Two uploads of the same `.xlsx` produce identical hashes regardless of filename.

```
proforma:filehash:{sha256hex}:result   → JSON parse result (same schema as proforma:{task_id}:result)
proforma:filehash:{sha256hex}:parsed_at → ISO timestamp string
```

TTL: **7 days** (vs. 24h for task-keyed results — cached results are worth keeping longer).

### Upload Flow (modified)

```
User uploads file
  ↓
POST /proforma-preflight (existing — reads sheet names, stores bytes in Redis)
  + compute SHA-256 hash of bytes
  + check Redis: proforma:filehash:{hash}:result
  ↓
┌─ Cache HIT ──────────────────────────────────────────────────────────────────┐
│ Return preflight fragment with "Cached result available" notice              │
│ Two buttons: [Use Cached Result] [Re-analyze (slower)]                       │
│ [Use Cached Result] → skips Celery, jumps directly to review template        │
│ [Re-analyze] → proceeds to normal sheet picker → Celery task flow            │
└──────────────────────────────────────────────────────────────────────────────┘
┌─ Cache MISS ─────────────────────────────────────────────────────────────────┐
│ Normal flow: sheet picker → upload-proforma → Celery task → progress polling │
│ On task complete: write result to BOTH task key AND hash key in Redis        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Cache Bust (Purge)

On the preflight fragment (when cache hit detected), show a "Purge cache & re-analyze" option. This:
1. Calls `DELETE /ui/models/{model_id}/proforma-cache/{hash}` (or a POST with `_method=DELETE`)
2. Route deletes `proforma:filehash:{hash}:result` and `proforma:filehash:{hash}:parsed_at` from Redis
3. Returns the normal sheet picker (no cache, will trigger fresh Celery parse)

This is the "I know I modified the file but it has the same content" escape hatch.

---

## UI Changes

### Preflight page — cache hit state

```
┌─────────────────────────────────────────────────────────────────────┐
│  ✓ We've seen this file before                                       │
│  Parsed 2 days ago — 19 expense lines, 3 unit types found           │
│                                                                      │
│  [Use Cached Result →]   [Re-analyze (15–60s)]                      │
│                                                                      │
│  ↳ Purge cached result and re-analyze from scratch                  │
└─────────────────────────────────────────────────────────────────────┘
```

"Purge cached result" is a small text link below the buttons, not a primary action — avoids accidental cache busts.

### Upload page — no UI change

The upload page doesn't know about cache state until after file selection. Cache check happens in `proforma-preflight` POST handler. No changes to `proforma_upload_step.html`.

---

## Implementation

### Step 1 — Hash computation in preflight route

In `proforma_preflight` (`ui.py`, POST handler):

```python
import hashlib

file_hash = hashlib.sha256(content).hexdigest()
cache_key = f"proforma:filehash:{file_hash}:result"
cached_result = r.get(cache_key)

if cached_result:
    parsed_at = r.get(f"proforma:filehash:{file_hash}:parsed_at") or "unknown"
    result = json.loads(cached_result)
    return templates.TemplateResponse(
        request,
        "partials/proforma_preflight_cached.html",   # new template
        {
            "model_id": model_id,
            "task_id": task_id,         # still stored so user can proceed to review
            "file_hash": file_hash,
            "parsed_at": parsed_at,
            "unit_type_count": len(result.get("unit_types", [])),
            "expense_line_count": len(result.get("expense_lines", [])),
            "sheet_names": sheet_names,
            "sheet_columns": sheet_columns,
            "STANDARD_OPEX_CATEGORIES": STANDARD_OPEX_CATEGORIES,
        },
    )
# ... rest of existing preflight logic unchanged
```

Store hash on the file bytes key too so the task can write back to it:
```python
r.set(f"proforma:{task_id}:file", content, ex=86_400)
r.set(f"proforma:{task_id}:file_hash", file_hash, ex=86_400)  # new
```

### Step 2 — Write hash cache on task completion

In `parse_proforma` Celery task (`proforma_parse.py`), after writing the task result:

```python
r.set(f"proforma:{task_id}:result", json.dumps(result), ex=_REDIS_TTL)

# Write to content-hash cache (longer TTL)
file_hash = r.get(f"proforma:{task_id}:file_hash")
if file_hash:
    file_hash = file_hash.decode() if isinstance(file_hash, bytes) else file_hash
    _HASH_TTL = 7 * 86_400  # 7 days
    r.set(f"proforma:filehash:{file_hash}:result", json.dumps(result), ex=_HASH_TTL)
    r.set(f"proforma:filehash:{file_hash}:parsed_at",
          datetime.utcnow().isoformat(), ex=_HASH_TTL)
```

### Step 3 — Cache-hit → review shortcut

When user clicks "Use Cached Result" in the cache-hit UI:

`POST /ui/models/{model_id}/proforma-use-cached` with `task_id` and `file_hash` as form fields.

Route reads `proforma:{task_id}:result` (which was written with the file bytes in the preflight) — or falls back to `proforma:filehash:{file_hash}:result` — and renders the review template directly, skipping Celery entirely.

### Step 4 — Purge route

```python
@router.post("/ui/models/{model_id}/proforma-purge-cache", response_class=HTMLResponse)
async def proforma_purge_cache(request: Request, model_id: UUID) -> HTMLResponse:
    form = await request.form()
    file_hash = str(form.get("file_hash", "")).strip()
    if file_hash and len(file_hash) == 64:  # SHA-256 hex
        r = _redis_client_str()
        r.delete(f"proforma:filehash:{file_hash}:result")
        r.delete(f"proforma:filehash:{file_hash}:parsed_at")
    # Return normal sheet picker (cache busted, fresh parse will run)
    ...
```

---

## Files to Create/Modify

| File | Change |
|---|---|
| `app/api/routers/ui.py` | `proforma_preflight`: compute SHA-256, check cache, store hash on Redis key; add `proforma-use-cached` route; add `proforma-purge-cache` route |
| `app/tasks/proforma_parse.py` | Write `filehash` cache keys after task completes |
| `app/templates/partials/proforma_preflight_cached.html` | New — cache-hit state with Use/Re-analyze/Purge options |

No DB migration needed. All state in Redis.

---

## Edge Cases

| Case | Behavior |
|---|---|
| File modified but same bytes | Cache hit, shows old result. User can purge and re-analyze. |
| File modified and bytes changed | SHA-256 differs → cache miss → fresh parse automatically |
| Cache TTL expired (7 days) | Miss → fresh parse. No stale data served. |
| Two users upload same file | Both benefit from cache. Results are content-based, not user-specific. |
| LLM output was wrong (user wants fresh) | Purge cache → re-analyze |
| Redis restart clears all cache keys | All future uploads simply re-parse. No data loss (cache is advisory). |

---

## Non-Goals

- Persistent file storage (files are not kept beyond Redis TTL)
- Per-user cache isolation (hash is global — intentional, same file = same result)
- Caching partial results (revenue-only or opex-only runs) — always cache full result
