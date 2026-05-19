# Setup: Work in Worktree

```bash
git worktree add ../vicinitideals-worktrees/email-ingest -b feature/email-ingest main
cp .env ../vicinitideals-worktrees/email-ingest/.env
cd ../vicinitideals-worktrees/email-ingest && uv sync
```

---

# Plan: Email Ingest → Auto Deal Creation

## Context

Brokers email deals to deals@rockwoodcdc.org or we forward deals manually. Goal: receive email → auto-create a "preliminary deal" pre-loaded with extracted data → user reviews, fills gaps, triggers compute. Reduces deal entry from manual form-filling to review-and-confirm.

Key constraints:
- Use deals@viciniti.deals (Cloudflare domain we control) instead of M365 — simpler and free
- Preliminary deal relaxes creation restrictions (no timeline required to save; compute still requires all prerequisites)
- Side-by-side review UI: source doc on left, editable fields on right
- Reuse existing proforma parser for .xlsx attachments
- After user accepts suggestions → route to existing deal setup wizard for timeline/debt

---

## Architecture Overview

```
Email arrives at deals@viciniti.deals
        ↓
Cloudflare Email Worker (tiny JS file in repo)
        ↓ HTTP POST with shared secret
POST /api/email-ingest  (new FastAPI router)
        ↓
InboundEmail row created (status=pending)
        ↓
Celery task: process_inbound_email
        ├─ Parse MIME: extract body text, attachments
        ├─ LLM call: extract address, asking price, unit count from body
        ├─ For .xlsx attachments: queue existing parse_proforma task
        ├─ Match address → Parcel (existing enrich_parcel())
        └─ Create PreliminaryDeal
               ↓
User opens /email-inbox  (new deal-inbox view)
        ↓ clicks email
/deals/email/{inbound_email_id}/review  (new side-by-side UI)
        ├─ Left: source doc viewer + email body
        └─ Right: suggestion chips per field (accept/override/skip)
        ↓ "Continue to Deal Setup"
Existing setup wizard (/ui/models/{model_id}/setup)
        ↓ wizard complete
Compute runs
```

---

## New DB Models (migration 0081)

### `inbound_emails` table
```
id              UUID PK
org_id          UUID FK (orgs)
received_at     TIMESTAMP
sender_email    TEXT
sender_name     TEXT nullable
subject         TEXT nullable
body_text       TEXT nullable           -- stored for human review
raw_mime_b64    TEXT nullable           -- raw email, base64 (72h then nulled)
status          TEXT                    -- pending | processing | deal_created | failed | spam
deal_id         UUID FK nullable        -- set when preliminary deal created
proforma_task_ids  JSONB default '[]'   -- list of proforma Celery task IDs
error_message   TEXT nullable
attachments_meta JSONB default '[]'     -- [{filename, content_type, size_bytes, stored_key}]
```

### `email_deal_suggestions` table
```
id                UUID PK
inbound_email_id  UUID FK (inbound_emails)
deal_id           UUID FK (deals)
field_path        TEXT    -- e.g. "acquisition_cost", "unit_mix.0.rent_monthly"
suggested_value   TEXT    -- serialized as string
confidence        FLOAT
source_type       TEXT    -- "email_body" | "proforma_xlsx" | "llm_extraction"
accepted          BOOL nullable  -- null=pending, true=accepted, false=rejected
```

### Changes to `deals` table
```
is_preliminary      BOOL default false
inbound_email_id    UUID FK nullable (inbound_emails)
```

---

## New Files to Create

| File | Purpose |
|---|---|
| `app/api/routers/email_ingest.py` | Webhook endpoint + inbox + review routes |
| `app/models/email_ingest.py` | InboundEmail + EmailDealSuggestion ORM models |
| `app/tasks/email_ingest.py` | Celery task: parse email, extract, create deal |
| `app/templates/email_inbox.html` | Email inbox list page |
| `app/templates/email_deal_review.html` | Side-by-side review page |
| `app/templates/partials/email_review/` | HTMX partials (suggestions panel, doc viewer, status) |
| `cloudflare-email-worker/index.js` | Cloudflare Email Worker (~30 lines JS) |
| `alembic/versions/0081_inbound_email.py` | Migration |

---

## Files to Modify

| File | Change |
|---|---|
| `app/models/deal.py` | Add `is_preliminary`, `inbound_email_id` to Deal |
| `app/api/main.py` or router registration | Register `email_ingest` router |
| `app/tasks/celery_app.py` | Register new task module |
| `app/config.py` | Add `EMAIL_INGEST_WEBHOOK_SECRET` setting |
| `docker-compose.yml` | Add `EMAIL_INGEST_WEBHOOK_SECRET` env var |
| `app/templates/partials/deals_list.html` (or equivalent) | Show preliminary badge on deal cards |

---

## Component Detail

### 1. Cloudflare Email Worker (`cloudflare-email-worker/index.js`)
- Trigger: email to deals@viciniti.deals
- Reads: sender, subject, raw MIME stream
- POSTs to `https://viciniti.deals/api/email-ingest` with header `X-Email-Ingest-Secret: {secret}`
- Body: JSON `{from, subject, rawMime}` (base64 MIME)
- Responds 200 immediately (Cloudflare requires fast ACK)
- Setup: deploy via `wrangler deploy` or Cloudflare dashboard; route rule in CF Email Routing

### 2. Webhook Endpoint (`POST /api/email-ingest`)
- Validate `X-Email-Ingest-Secret` header → 403 if wrong
- Parse JSON body, create `InboundEmail` row (status=pending), return 200 immediately
- Queue Celery task `process_inbound_email.delay(inbound_email_id)`
- No auth required (public webhook, protected by secret)

### 3. Celery Task (`app/tasks/email_ingest.py: process_inbound_email`)
Steps:
1. Update status → processing
2. Decode raw MIME → extract body_text, attachments list
3. **Address/price extraction** (LLM call, same Ollama/Instructor pattern as proforma parser):
   - Input: subject + first 2000 chars of body
   - Extract: address, asking_price, unit_count, property_type, broker_name, broker_email
   - Return confidence per field
4. **Parcel match**: call existing `enrich_parcel(address)` → get Parcel or None
5. **For each .xlsx attachment**: queue `parse_proforma` task (already exists), store task ID in `proforma_task_ids`
6. **Create preliminary deal**:
   - Reuse existing `create_deal` logic (or call directly) with:
     - `name` = subject (trimmed) or address
     - `deal_type` = "acquisition" (default, user confirms in wizard)
     - `acquisition_cost` = extracted price or 0 (flagged as required before compute)
     - `is_preliminary = True`
     - `inbound_email_id` = this email's ID
   - Wire `opportunity.parcel_id` if parcel found
7. **Create EmailDealSuggestion rows** for each extracted field with confidence scores
8. Update status → deal_created, set `deal_id`
9. Send notification email to org members (using existing `sender.py` pattern)

### 4. Preliminary Deal Creation Logic
New route: `POST /ui/deals/create-preliminary` (or internal function called by task):
- Same as existing `POST /ui/deals/create` but:
  - `acquisition_cost` optional (defaults to 0; compute will flag it)
  - `is_preliminary = True`
  - `inbound_email_id` stored on Deal
  - Skips source_vehicle auto-selection
  - Does NOT redirect to setup wizard — leaves deal in "pre-wizard" state
- OperationalInputs still created (required for compute engine not to crash)
- All fields at defaults

### 5. Email Inbox Page (`GET /ui/email-inbox`)
- Lists `InboundEmail` rows for org, newest first
- Status badges: pending (gray), processing (blue spinner), deal_created (green), failed (red)
- Click → goes to review page
- Nav link added to sidebar

### 6. Side-by-Side Review UI (`GET /ui/deals/email/{inbound_email_id}/review`)

Layout:
```
┌─ [email subject] · broker@example.com · May 11, 2026 ──────────────────┐
├──────────────────────────┬─────────────────────────────────────────────┤
│  SOURCE DOCUMENTS        │  DEAL PREVIEW                               │
│                          │                                             │
│  [Tab: Pro Forma]        │  Address: 123 Main St            [matched] │
│  [Tab: Email Body]       │  Asking Price: $2,500,000  [suggested ✓]   │
│                          │  Unit Count:   48 units    [suggested ✓]   │
│  ┌────────────────────┐  │  Deal Type:    [acquisition ▾]  ← required │
│  │ Excel table render │  │                                             │
│  │ or PDF iframe      │  │  Income (from pro forma):                  │
│  └────────────────────┘  │   1BR × 24 @ $1,100/mo    [suggested ✓]   │
│                          │   2BR × 24 @ $1,400/mo    [suggested ✓]   │
│                          │                                             │
│                          │  Expenses (from pro forma):                │
│                          │   Real Estate Taxes $45,000 [suggested ✓] │
│                          │   Insurance $18,000         [suggested ✓] │
│                          │                                             │
│                          │  ⚠ Acquisition cost required for compute  │
│                          │                                             │
│                          │  [Continue to Deal Setup →]                │
└──────────────────────────┴─────────────────────────────────────────────┘
```

HTMX interactions:
- "Accept" chip on a suggestion → PATCH suggestion row (accepted=true), updates field in DB
- User edits field directly → saves to deal, marks suggestion as accepted
- Proforma suggestions loaded asynchronously (poll until proforma task completes)
- "Continue to Deal Setup" → redirects to existing `/ui/models/{model_id}/setup`

### 7. Applying Suggestions to Deal Fields

When user accepts a suggestion:
- `acquisition_cost` → upsert UseLine with phase=acquisition
- `unit_mix.*` → update Project.unit_mix JSONB array
- `income_stream.*` → create/update IncomeStream rows
- `expense_line.*` → create/update OperatingExpenseLine rows
- Mark suggestion as accepted=true

Existing proforma-confirm endpoint (`POST /ui/models/{model_id}/proforma-confirm`) already handles income + expense line commits — reuse this logic.

---

## Build Order (implement in this sequence)

1. **Migration 0081** — new tables + deal columns
2. **ORM models** — `app/models/email_ingest.py` + update `app/models/deal.py`
3. **Webhook endpoint** — `app/api/routers/email_ingest.py` (POST only, no UI yet)
4. **Celery task skeleton** — `app/tasks/email_ingest.py` (parse MIME + create InboundEmail row; stub LLM + deal creation)
5. **LLM extraction** — address/price extractor (Instructor + Ollama, same pattern as `proforma_parse.py`)
6. **Preliminary deal creation** — internal function (reuse create_deal logic, add is_preliminary flag)
7. **Suggestion storage + acceptance** — EmailDealSuggestion CRUD
8. **Email inbox page** — simple list, no review UI yet
9. **Review UI** — side-by-side layout + suggestion chips
10. **Proforma integration** — wire proforma task results as suggestions after parse completes
11. **Cloudflare Worker** — write + deploy
12. **Notification email** — alert org users when new email arrives

---

## Key Reuse Points

| Existing thing | Where used |
|---|---|
| `app/tasks/proforma_parse.py: parse_proforma` | Queue from email task for .xlsx attachments |
| `app/api/routers/ui.py: proforma_confirm` logic | Apply accepted income/expense suggestions |
| `app/api/routers/ui.py: create_deal` | Called internally by email task (relaxed variant) |
| `app/scrapers/parcel_enrichment.enrich_parcel()` | Address → Parcel match |
| `app/emails/sender.py` | Notification email to org on new inbound |
| Existing setup wizard (`/ui/models/{model_id}/setup`) | After review, routes here for timeline/debt |

---

## Verification

1. **Webhook smoke test**: `curl -X POST https://viciniti.deals/api/email-ingest -H "X-Email-Ingest-Secret: ..." -d '{"from":"test@example.com","subject":"test","rawMime":"..."}'` → 200, InboundEmail row created
2. **Task processes**: Send real email to deals@viciniti.deals → InboundEmail status → deal_created
3. **Proforma parsed**: Attach Green Seed xlsx → proforma task queues + completes → suggestions created
4. **Review UI**: Open review page → suggestions visible → accept → deal fields updated
5. **Wizard hand-off**: "Continue to Setup" → wizard loads correctly, deal is preliminary
6. **Compute gate**: deal with acquisition_cost=0 → compute button disabled with error message
7. **Compute runs**: fill price + complete wizard → compute succeeds
