# Feature Plan: Per-Deal-Type Timeline Defaults in Org/User Settings

## Context

The milestone timeline system already has `DEFAULT_DURATIONS` in `app/models/milestone.py` — a hardcoded Python dict that defines which milestones are included per deal type and their default durations. When a new deal's timeline is created via the wizard, those system-level defaults seed the milestone list.

This plan makes those defaults configurable: org admins can override the defaults per deal type, and (where allowed) users can set their own. The resolution chain mirrors the existing org/user settings system:

```
User override → Org override → DEFAULT_DURATIONS system baseline
```

**Deal Types** (existing `ProjectType` enum):
- `acquisition` → "Acquisition"
- `value_add` → "Value-Add"
- `conversion` → "Acquisition – Conversion"
- `new_construction` → "New Construction"

**Milestone Types** (existing `MilestoneType` enum):
- `offer_made`, `under_contract`, `close`
- `pre_development`, `construction`, `operation_lease_up`, `operation_stabilized`, `divestment`

---

## What's New (vs. Existing DEFAULT_DURATIONS)

| Capability | System Baseline | New |
|---|---|---|
| Which milestones are included | Implicit (presence in dict) | Explicit `included` checkbox |
| Duration (days) | Fixed int | Editable; null = user sets in deal |
| Starts After | Implicit ordering in code | Explicit dropdown; null = user must wire in deal |
| Offset Days | Always 0 | Editable integer |
| Org override | None | New `org_deal_type_defaults` table |
| User override | None | New `user_deal_type_defaults` table |
| User override lock | None | `user_overridable` flag per row |

---

## Step 1 — New DB Tables

### `org_deal_type_defaults`

```sql
CREATE TABLE org_deal_type_defaults (
    id            UUID PRIMARY KEY,
    org_id        UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    deal_type     VARCHAR(40) NOT NULL,     -- ProjectType enum value
    milestone_type VARCHAR(40) NOT NULL,    -- MilestoneType enum value
    included       BOOLEAN NOT NULL DEFAULT TRUE,
    duration_days  INTEGER,                 -- NULL = system baseline
    starts_after_type VARCHAR(40),          -- NULL = user must set in deal
    offset_days    INTEGER NOT NULL DEFAULT 0,
    user_overridable BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by    UUID REFERENCES users(id),
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (org_id, deal_type, milestone_type)
);
```

### `user_deal_type_defaults`

```sql
CREATE TABLE user_deal_type_defaults (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id        UUID NOT NULL,
    deal_type     VARCHAR(40) NOT NULL,
    milestone_type VARCHAR(40) NOT NULL,
    included       BOOLEAN NOT NULL DEFAULT TRUE,
    duration_days  INTEGER,
    starts_after_type VARCHAR(40),
    offset_days    INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (user_id, deal_type, milestone_type)
);
```

Alembic migration: `0078_add_deal_type_timeline_defaults.py`

---

## Step 2 — ORM Models

Add to `app/models/settings.py` (alongside `OrgSetting` / `UserSetting`):

```python
class OrgDealTypeDefault(Base):
    __tablename__ = "org_deal_type_defaults"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    milestone_type: Mapped[str] = mapped_column(String(40), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_after_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_overridable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=True, onupdate=datetime.utcnow)

class UserDealTypeDefault(Base):
    __tablename__ = "user_deal_type_defaults"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    milestone_type: Mapped[str] = mapped_column(String(40), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_after_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(nullable=True, onupdate=datetime.utcnow)
```

---

## Step 3 — Resolver

New file (or add to `app/settings/resolver.py`):

```python
async def resolve_timeline_defaults(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, dict[str, dict]]:
    """
    Returns: { deal_type: { milestone_type: { included, duration_days, starts_after_type, offset_days } } }
    """
```

Resolution logic per (deal_type, milestone_type):

1. Load org row → check `user_overridable`
2. If `user_overridable` is True: load user row
3. Merge: user → org → `DEFAULT_DURATIONS` system baseline
4. `included`: default True if not in system baseline for this deal_type
5. `duration_days`: null means "use system baseline value if it exists, else null (user sets)"
6. `starts_after_type`: null means user must configure in-deal
7. `offset_days`: default 0

---

## Step 4 — Settings API

### New endpoints (add to `app/api/routers/settings.py`):

```
GET  /api/settings/timeline-defaults          — resolve full template for current user/org
PUT  /api/settings/timeline-defaults/org      — org admin batch upsert
PUT  /api/settings/timeline-defaults/user     — user batch upsert (respects user_overridable)
```

**PUT /api/settings/timeline-defaults/org** body:
```json
{
  "acquisition": {
    "offer_made": { "included": true, "duration_days": 14, "starts_after_type": null, "offset_days": 0 },
    "close":      { "included": true, "duration_days": 30, "starts_after_type": "under_contract", "offset_days": 0 }
  },
  "value_add": { ... },
  "permissions": {
    "acquisition": {
      "construction": { "user_overridable": false }
    }
  }
}
```

**PUT /api/settings/timeline-defaults/user** body: same shape, without `permissions`.

---

## Step 5 — UI Routes (`app/api/routers/ui.py`)

### `/settings/organization` GET
Also load `OrgDealTypeDefault` rows, build `timeline_defaults_map`:
```python
{
  deal_type: {
    milestone_type: {
      "included": bool,
      "duration_days": int | None,
      "starts_after_type": str | None,
      "offset_days": int,
      "user_overridable": bool,
    }
  }
}
```
Pass to template alongside existing `org_settings_map`.

### `/settings/preferences` GET
Load user rows + org rows for overridable flags. Build:
```python
{
  deal_type: {
    milestone_type: {
      "included": bool,      # resolved
      "duration_days": int|None,
      "starts_after_type": str|None,
      "offset_days": int,
      "overridable": bool,   # from org row or default True
    }
  }
}
```

---

## Step 6 — `settings_organization.html`

New section **"Deal Type Timeline Templates"** below existing field sections.

Layout for each deal type (4 accordions):

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ▸ Acquisition                                          [Expand]          │
├──────────────────┬──────────────┬─────────────────────┬─────────────────┤
│ Milestone        │ Include      │ Duration (days)     │ Starts After    │ + Offset │ Allow Override │
├──────────────────┼──────────────┼─────────────────────┼─────────────────┤
│ Offer Made       │ [✓]          │ [14]                │ [— (anchor) —]  │ [0]      │ [✓ Allow users]│
│ Under Contract   │ [✓]          │ [30]                │ [offer_made  ▼] │ [0]      │ [✓ Allow users]│
│ Close            │ [✓]          │ [45]                │ [under_contr ▼] │ [0]      │ [✓ Allow users]│
│ Pre-Development  │ [ ]          │ [—  ]               │ [—  select —  ] │ [0]      │ [✓ Allow users]│
│ Construction     │ [ ]          │ [—  ]               │ [—  select —  ] │ [0]      │ [✓ Allow users]│
│ Lease-Up         │ [ ]          │ [—  ]               │ [—  select —  ] │ [0]      │ [✓ Allow users]│
│ Stabilized       │ [✓]          │ [1825]              │ [close       ▼] │ [0]      │ [✓ Allow users]│
│ Divestment       │ [✓]          │ [1 ]                │ [stabilized  ▼] │ [0]      │ [✓ Allow users]│
└──────────────────┴──────────────┴─────────────────────┴─────────────────┘
```

**"Starts After" dropdown options**:
- `— (must set in deal) —` → stores `null`
- Each milestone type that's currently checked as `included` for this deal type (dynamically filtered)

**Dirty tracking**:
- JS watches Include checkbox, Duration input, Starts After select, Offset input
- Save pill sends structured JSON to `PUT /api/settings/timeline-defaults/org`
- Permissions (Allow Override checkboxes) tracked separately, same payload `permissions` key

---

## Step 7 — `settings_user.html`

Same table layout, but:
- Rows where `overridable=False` → all inputs `disabled` + "🔒 Set by org" label on row
- Rows where `overridable=True` → editable, participate in dirty tracking
- No "Allow Override" column (that's org admin only)
- Save sends to `PUT /api/settings/timeline-defaults/user`

---

## Step 8 — Timeline Wizard Integration

In the wizard's timeline step (POST handler that creates milestones), replace the direct lookup into `DEFAULT_DURATIONS`:

**Before:**
```python
from app.models.milestone import DEFAULT_DURATIONS
durations = DEFAULT_DURATIONS.get(project_type, {})
```

**After:**
```python
from app.settings.resolver import resolve_timeline_defaults
template = await resolve_timeline_defaults(user_id, org_id, session)
deal_defaults = template.get(project_type, {})
```

For each milestone type in `deal_defaults`:
- Skip if `included=False`
- Use `duration_days` (fall back to system baseline if null)
- Use `starts_after_type` to wire trigger chain (if null, create milestone with `trigger_milestone_id=None`)
- Apply `offset_days` as `trigger_offset_days`

`starts_after_type=null` milestones are created "floating" — same as today when trigger chains are absent. The deal's timeline tab will show them needing a start date.

---

## Step 9 — Plan Doc Update

Update this file and `docs/feature-plans/org-user-defaults.md` to cross-reference.

---

## Data Flow Summary

```
settings_organization.html
  → PUT /api/settings/timeline-defaults/org
  → OrgDealTypeDefault rows (upsert)
  → resolve_timeline_defaults() on next GET

settings_user.html
  → PUT /api/settings/timeline-defaults/user
  → UserDealTypeDefault rows (upsert, skips if user_overridable=False)
  → resolve_timeline_defaults() on next GET

wizard timeline step POST
  → resolve_timeline_defaults()
  → create Milestone rows per included=True entries
  → wire trigger chains for entries with starts_after_type set
  → leave floating (trigger=None) for entries with starts_after_type=null
```

---

## Verification

1. Org sets Construction duration = 240 days, Starts After = close, offset = 30 → new Construction deal gets Construction milestone: 240 days, starts 30 days after close ✓
2. Org sets `construction` user_overridable=False → user settings page shows Construction row locked ✓
3. User sets Construction duration = 180 days when org has 240 and `user_overridable=True` → user's deal gets 180 ✓
4. `starts_after_type=null` → milestone created without trigger_milestone_id → timeline editor shows it as needing a start date ✓
5. `included=False` for `pre_development` on `acquisition` → wizard does not create pre_development milestone ✓
6. Org has no row for a (deal_type, milestone_type) pair → falls back to DEFAULT_DURATIONS → same behavior as today ✓

---

## Implementation Order

1. Alembic migration (tables)
2. ORM models
3. Resolver (`resolve_timeline_defaults`)
4. API endpoints
5. UI routes (pass data to templates)
6. Org settings template
7. User settings template
8. Wizard integration
