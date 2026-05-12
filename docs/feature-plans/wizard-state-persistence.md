# Feature Plan: Deal Setup Wizard — State Persistence

## Problem

The deal creation wizard is HTMX-driven: each step is a server-rendered HTML partial that replaces the previous one. State lives only in the browser DOM. Navigating away (to another tab, refreshing, clicking the browser back button) destroys all in-progress wizard state. The user must start over.

This is especially painful after the pro forma import step — the user goes through the 15–60 second LLM parse, reviews matched categories, then accidentally refreshes and loses everything.

---

## Current State

| Data | Where it lives | Survives navigation? |
|---|---|---|
| Pro forma parse result | Redis `proforma:{task_id}:result`, 24h TTL | Yes (key is in the URL) |
| Pro forma review edits (checked rows, overridden categories) | DOM only | No |
| Debt type selections (step 2) | DOM only | No |
| Equity / waterfall config (step 3+) | DOM only | No |
| Committed wizard steps | PostgreSQL (deal row, project row, OpEx lines) | Yes — once confirmed |

Once any wizard step is submitted and committed, that data is durable. The loss window is within a step, between POST and next POST.

---

## Options

### Option A — localStorage (recommended for now)

JavaScript serializes each wizard step's form state to `localStorage` keyed by `model_id + step_key` as the user fills it out. On page load/HTMX settle, if a matching key exists, JS re-populates the fields.

**How it works:**
- Listen for `htmx:afterSettle` events (fires after each HTMX partial swap)
- On input change events, serialize the current form's inputs to `localStorage["wizard:{model_id}:{step}"]` as JSON
- On `htmx:afterSettle`, read back any saved state for the current step and re-populate fields
- Clear the key when the step is successfully submitted (`htmx:afterRequest` on the form, status 200)

**Pros:**
- Zero backend changes
- Zero database migrations
- Works immediately for all wizard steps
- Survives refresh, tab close, power loss

**Cons:**
- Device-specific — doesn't follow the user to a different browser or machine
- Cleared if user clears browser storage
- Requires JS per-step to know which inputs to save/restore (some inputs are dynamic — e.g., debt type checkboxes affect downstream steps)

**Effort:** 1 day. Primary complexity is HTMX event wiring and testing that restore doesn't break dynamic inputs (radio groups, checkboxes that drive visibility of other fields).

**Right fit for:** single-operator self-hosted tool. Most sessions happen on one machine.

---

### Option B — Server-side wizard draft

New DB table:

```sql
CREATE TABLE wizard_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    model_id UUID NOT NULL REFERENCES deals(id),
    step_key VARCHAR(64) NOT NULL,  -- e.g. "revenue_import", "debt_types", "equity"
    state_json JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, model_id, step_key)
);
```

Each wizard step auto-saves to this table via a background HTMX `hx-trigger="input delay:500ms"` PATCH to `/ui/models/{model_id}/wizard-draft/{step_key}`. When the user returns to a deal, a "Resume setup →" link on the deal detail page checks for existing drafts and renders the wizard at the last active step with saved state.

**Pros:**
- Cross-device — works from any browser
- Admin-visible (can see in-progress deals)
- Could show "In Progress" badge on deals list
- Drafts persist beyond browser clear

**Cons:**
- New migration required
- Route handler needed per step key
- Need to define "clear draft" on wizard completion and on explicit abandon
- Most complex option

**Effort:** 2–3 days. Migration + 5–6 route handlers + draft serialization schema per step + resume UI on deal page.

---

### Option C — Pro forma resume only (quick win, implement now)

The parse result is already in Redis for 24 hours under `proforma:{task_id}:result`. The `task_id` is in the URL when polling the status endpoint. If the user navigates away while on the review page, the data is still there.

Add a "Resume import →" link/banner on the deal detail page:

1. When a task result exists in Redis for a known `task_id` (stored on the deal row as `last_proforma_task_id`), show the banner
2. Clicking it re-renders the review template with the cached result, same as if the parse just finished
3. TTL is 24h — after that, the banner disappears automatically

**Requires:**
- New nullable column `last_proforma_task_id VARCHAR(64)` on `deals` table (migration)
- Write `task_id` to this column when `upload-proforma` fires
- Deal detail page reads Redis to check if result still exists, renders banner if so

**Effort:** 2–3 hours. One migration column + two small route changes + banner partial.

This does NOT help with lost review edits (checked rows, overridden categories) or any other wizard step.

---

## Recommendation

**Ship Option C now** (pro forma resume) — it solves the most acute pain (losing a 60-second LLM parse) with minimal effort and no architectural commitment.

**Plan Option A** as the full wizard state solution — localStorage is sufficient for a single-operator tool and requires no schema changes. Implement once Option C is validated and the wizard is otherwise feature-complete.

**Option B** if the product ever needs multi-device, admin visibility of drafts, or an "in-progress deals" dashboard — not the right scope today.

---

## Files to Create/Modify

### Option C (pro forma resume)

| File | Change |
|---|---|
| `alembic/versions/XXXX_proforma_task_id.py` | Add `last_proforma_task_id VARCHAR(64)` nullable column to `deals` |
| `app/models/deal.py` | Add `last_proforma_task_id: Mapped[str | None]` to `Scenario` |
| `app/api/routers/ui.py` | Write `task_id` to model in `upload-proforma` route; read Redis in deal detail route; add resume banner to deal detail template |
| `app/templates/partials/deal_header.html` (or equivalent) | Add "Resume pro forma import →" banner when result exists |

### Option A (localStorage for full wizard)

| File | Change |
|---|---|
| `app/templates/partials/deal_setup_wizard.html` | Add wizard state JS: save on input, restore on `htmx:afterSettle`, clear on successful step submit |

No backend changes required.

---

## Non-Goals

- Real-time collaboration (multiple users editing same wizard simultaneously)
- Wizard draft versioning / history
- Auto-submit on resume (user always reviews before confirming)
