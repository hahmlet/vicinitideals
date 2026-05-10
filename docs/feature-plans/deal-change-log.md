# Deal Change Log & Revert — Design Plan

## Context

User wants: audit trail of deal changes, cascading diff reports (what metrics changed and by how much), and the ability to revert a deal to a prior state.

Concerns: practical limits, logging granularity, scope (deals first), and how to communicate cascading diffs.

---

## Codebase Facts (Exploration Results)

**Existing infrastructure that can be reused:**
- Full JSON import/export already works (`app/exporters/` + `tests/fixtures/tower_acquisition.json` = ~238 KB serialized deal)
- `WorkflowRunManifest` table already logs every compute run (inputs + output summary JSON)
- `Sensitivity.model_version_snapshot` pattern already captures input state at sensitivity run time — same pattern we'd extend
- `Scenario.version` integer field exists but is completely unused (no code writes to it)

**Deal input footprint (what needs versioning):**
- ~50–80 input rows total per scenario (IncomeStreams, OpEx, UseLines, UnitMix, CapitalModules, WaterfallTiers, OperationalInputs, Milestones)
- Serialized as compact JSON: **~20–30 KB** per snapshot (inputs only, not computed CashFlow rows)
- Gzipped: **~4–6 KB** per snapshot

**Compute is already explicit (not per-keypress):**
- Form saves persist inputs, NO auto-recalculation
- Compute button (`POST /models/{model_id}/compute`) is a manual explicit trigger
- This is the natural snapshot point

---

## Answers to User's 4 Concerns

### 1. Practical limits at 100 changes
Not a problem. 100 snapshots × 25 KB gzipped ≈ 2.5 MB per scenario. PostgreSQL handles this trivially. A history table with 100 rows per scenario is a tiny query. No breakdown at this scale.

### 2. Granularity — when to save
**Recommended: snapshot on each explicit Compute run.**

Why this is the right boundary:
- User changes income, opex, capital, etc. (form saves — fast, no log)
- User clicks "Calculate" → system computes and stores a snapshot
- Result: "20 edits to set up Revenue" = 0 logs. One Compute click = 1 log.
- Maps exactly to the user's mental model: "I ran numbers, now I can see what they were"

### 3. Scope
Deal/Scenario only in V1. Parcel/Opportunity have much simpler data models and can be added later using the same pattern.

### 4. Cascading diff reports
Two-level diff on each snapshot pair:

**Input diff** (what the user changed):
- Which input rows were added/removed/modified
- Plain-English labels: "Gross Revenue (Unit A) $1,200 → $1,450/mo"

**Output diff** (what cascaded):
- Compare `OperationalOutputs` before vs. after
- Show delta for: DSCR, IRR (levered), Total Project Cost, NOI, Equity Required, Cap Rate on Cost
- Example: "DSCR +0.12, IRR +1.4%, Equity Required −$48k"

NOT in V1: causal attribution (proving WHY IRR moved because of revenue change). Users can connect the dots from input diff → output diff.

---

## Recommended Architecture

### New DB table: `scenario_snapshots`

```sql
scenario_snapshots:
  id              UUID PK
  scenario_id     UUID FK → scenarios (cascade delete)
  version         INTEGER    -- matches Scenario.version at time of snapshot
  created_at      TIMESTAMPTZ
  triggered_by    ENUM ('compute', 'manual')
  label           TEXT NULL  -- reserved for future named checkpoints
  inputs_json     JSONB      -- full input state (~20-30 KB)
  outputs_json    JSONB      -- { dscr, irr, tpc, noi, equity_required, cap_rate }
```

### Snapshot trigger

Hook into `POST /models/{model_id}/compute` (in `app/api/routers/models.py` ~line 557):
1. Increment `Scenario.version`
2. Before writing new OperationalOutputs: serialize current inputs → `inputs_json`
3. After compute completes: read new OperationalOutputs → `outputs_json`
4. Insert `scenario_snapshots` row with new version number

### Diff computation

On-demand, server-side: compare two consecutive snapshot rows' JSON. Return:
- Input field deltas (compare JSONB keys)
- Output metric deltas (arithmetic diff)

### Revert

Reuse the existing JSON import pipeline:
1. User selects snapshot to revert to
2. Server reads `inputs_json`
3. Delete current child rows (UseLines, IncomeStreams, etc.)
4. Re-insert from snapshot JSON
5. Invalidate OperationalOutputs (mark stale or delete)
6. User re-runs Compute to see numbers

### UI surface

- "History" button on the deal builder → side drawer
- List of compute runs with version number, timestamp, key output summary
- Click a row → show input diff + output diff vs. prior snapshot
- "Revert to this version" button on any row
- "Export Log" button → downloads JSON

---

## Files to Create/Modify

| File | Change |
|---|---|
| `alembic/versions/0065_scenario_snapshots.py` | New migration: `scenario_snapshots` table |
| `app/models/deal.py` | Add `ScenarioSnapshot` ORM class + relationship |
| `app/api/routers/models.py` ~line 557 | Hook snapshot creation + version increment into compute endpoint |
| `app/api/routers/ui.py` | Add history drawer route, revert endpoint, log export endpoint |
| `app/exporters/snapshot.py` (new) | Serialize/deserialize scenario inputs; build diff; emit export JSON |
| `app/exporters/investor_export.py` | Stamp scenario version number into Excel workbook (cell or sheet metadata) |
| `app/templates/partials/history_drawer.html` (new) | History list + diff view + Export Log button |
| `tests/exporters/test_snapshot.py` (new) | Round-trip: serialize → deserialize → compare; diff format; export JSON shape |

### Version increment (reuse existing field)
`Scenario.version` (integer, already in DB, currently always 0) → incremented on every compute run. Becomes the canonical version label across snapshots, Excel exports, and the JSON log.

### Excel version stamp
Add version to the Underwriting Summary sheet: a single cell `v{n}` near the workbook title. Named range `s_version` for AI/export consumption.

### JSON export format
`GET /models/{model_id}/history/export.json` returns:
```json
{
  "scenario_id": "...",
  "scenario_name": "...",
  "exported_at": "...",
  "entries": [
    {
      "version": 3,
      "computed_at": "2026-05-02T19:43:00Z",
      "input_changes": [
        { "entity": "IncomeStream", "label": "Gross Revenue (Unit A)", "field": "amount_per_unit_monthly", "before": 1200, "after": 1450 }
      ],
      "output_changes": {
        "dscr": { "before": 1.18, "after": 1.31 },
        "project_irr_levered": { "before": 0.142, "after": 0.158 },
        "noi_stabilized": { "before": 148200, "after": 163800 },
        "equity_required": { "before": 512000, "after": 487000 },
        "total_project_cost": { "before": 1840000, "after": 1840000 }
      }
    }
  ]
}
```

---

## Decisions (User-confirmed)

1. **Trigger**: Compute-only. No manual save button.
2. **Diff display**: Inputs + outputs. Show field changes AND metric deltas.
3. **Revert scope**: Entire scenario. Full rollback, no partial revert.
4. **Export**: Change log exportable as JSON (AI-readable). Each entry is a structured diff.
5. **Versioning**: Each Compute run increments `Scenario.version` (field already exists, unused). Excel exports carry this version number. AI agent can correlate Excel export v7 with log entry v7.

---

## Verification

1. Run compute on a deal → confirm snapshot row created + `Scenario.version` incremented
2. Change an input, recompute → confirm second snapshot with input diff + output diff
3. Revert to first snapshot → confirm input rows match original state
4. Export log → confirm JSON shape matches spec above
5. Export Excel → confirm `v{n}` version stamp on Underwriting Summary sheet
6. Run `uv run pytest tests/exporters/test_snapshot.py -q`
7. Manual UI test: open history drawer, view diff, execute revert
