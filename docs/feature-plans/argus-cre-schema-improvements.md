# Argus CRE Schema: Three Targeted Improvements

## Agent setup — do this first

Create a worktree before making any changes:

```bash
git worktree add ../vicinitideals-worktrees/cre-schema-improvements -b feature/cre-schema-improvements main
cp .env ../vicinitideals-worktrees/cre-schema-improvements/.env
cd ../vicinitideals-worktrees/cre-schema-improvements && uv sync
```

All work happens in that worktree. Commit there, push, merge to main when done.

---

## Why

Compared vicinitideals data model against Argus FinAsset (professional CRE platform) schema and ARGUS Voyanta API. Model is more complete than expected — three gaps worth closing:

1. **No way to model partial expense recovery** — a NNN lease where landlord absorbs 20% of maintenance has no field for this. Every OpEx line implicitly assumes the landlord pays 100%.
2. **Occupancy/vacancy inversion** — we store occupancy (95%) but every broker, appraiser, and lender talks in vacancy (5%). Users have to mentally flip the number when entering.
3. **`catchup_target_rent` is opaque** — stores the market rent a unit could achieve, but the name communicates nothing. Argus and the broader industry call this ERV (Estimated Rental Value). Renaming removes the need to know our internal LTL-catchup feature to understand the field.

---

## Changes

### 1. Add `non_recoverable_pct` to `OperatingExpenseLine`

`app/models/deal.py` — `OperatingExpenseLine` class (lines 510–543):
- Add `non_recoverable_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0, server_default="0")`

`app/engines/cashflow.py` — per-period OpEx calculation:
- Only the `non_recoverable_pct` share of each line reduces NOI. Default 0 = backward-compatible (landlord pays full amount, as today).

`app/api/routers/models.py` — `create_expense_line` / `update_expense_line` (lines 420–450):
- Include `non_recoverable_pct` in read/write.

`app/api/routers/ui.py` — OpEx line form:
- Add "Non-recoverable %" input field.

New Alembic migration: add column with `DEFAULT 0` (non-breaking).

### 2. Flip vacancy/occupancy UI label (no schema change)

`app/api/routers/ui.py` and relevant templates:
- Input labeled "Vacancy %" — store as `1 - input` in `stabilized_occupancy_pct`.
- Display as vacancy everywhere in UI.
- No migration. No engine change.

### 3. Rename `catchup_target_rent` → `market_rent_monthly`

`app/models/deal.py` — `IncomeStream` class:
- Rename column.

`app/engines/cashflow.py`:
- Update all references (grep: `catchup_target_rent`).

`app/api/routers/` — any route reading/writing this field.

New Alembic migration: `ALTER TABLE income_streams RENAME COLUMN catchup_target_rent TO market_rent_monthly`.

---

## Files to Modify

| File | Change |
|---|---|
| `app/models/deal.py` | Add `non_recoverable_pct` to `OperatingExpenseLine`; rename `catchup_target_rent` → `market_rent_monthly` on `IncomeStream` |
| `app/engines/cashflow.py` | Apply `non_recoverable_pct` in OpEx calc; update `catchup_target_rent` refs |
| `app/api/routers/models.py` | Include `non_recoverable_pct` in expense line CRUD; rename field ref |
| `app/api/routers/ui.py` | Vacancy/occupancy UI flip; new `non_recoverable_pct` field; rename field ref |
| `app/templates/` | Vacancy label changes; `non_recoverable_pct` input |
| `alembic/versions/` | Two migrations: new column + column rename |

---

## Verification

1. `uv run pytest tests/ -q --ignore=tests/e2e` — all pass (default=0 keeps existing behavior)
2. Create OpEx line with `non_recoverable_pct=0.20` on a NNN deal; confirm NOI only reflects 20% of that line as landlord cost
3. Confirm `non_recoverable_pct=0` line unchanged from pre-migration behavior
4. Confirm vacancy input stores correctly as occupancy (enter 5% vacancy → `stabilized_occupancy_pct=95`)
5. Confirm `market_rent_monthly` field works identically to old `catchup_target_rent` in LTL-catchup logic
6. Deploy, smoke-test deal builder OpEx and income stream forms

---

## Doc Updates (required — agent must do this)

After implementing, update both schema docs to reflect changes:

**`docs/DATA_MODEL.md`** — Financial Entity Field Reference section:
- Add `non_recoverable_pct` to `OperatingExpenseLine` field table with description: "Fraction of this expense the landlord cannot recover from tenants (0 = fully recoverable; 1 = fully landlord cost). Default 0."
- Update `IncomeStream` field table: rename `catchup_target_rent` → `market_rent_monthly`, update description to: "Market rent (ERV) this unit could achieve. Used as LTL-catchup target; escalation accelerates until base rent reaches this value."
- Note vacancy UI convention: `stabilized_occupancy_pct` is stored as occupancy (0–100) but displayed/entered as vacancy in UI.

**`docs/FINANCIAL_MODEL.md`** — OpEx section (§5):
- Add note that per-period OpEx = Σ(line.annual_amount × line.non_recoverable_pct / 12 × escalation). Lines with non_recoverable_pct=0 contribute zero to landlord NOI reduction (fully tenant-paid).
- Update any reference to `catchup_target_rent` → `market_rent_monthly`.
