# Cash Flow Engine

`app.engines.cashflow` provides the Stage 1A operational cash flow engine.

## Public interface

```python
from app.engines.cashflow import compute_cash_flows

summary = await compute_cash_flows(deal_model_id, session)
```

## Inputs

- `deal_model_id`: UUID (or UUID-like string) for the target `DealModel`
- `session`: SQLAlchemy `AsyncSession`

The engine reads:
- `DealModel`
- `OperationalInputs`
- all `IncomeStream` rows for the deal

## Outputs

On each run, the engine replaces prior computed rows for that deal and writes:

- one `CashFlow` row per monthly period
- granular `CashFlowLineItem` rows for income, expenses, reserves, debt-service placeholders, and capital events
- one `OperationalOutputs` row with key portfolio metrics

It returns a summary dictionary containing:
- `cash_flow_count`
- `line_item_count`
- `total_project_cost`
- `equity_required`
- `noi_stabilized`
- `cap_rate_on_cost_pct`
- `project_irr_unlevered`
- placeholder `project_irr_levered` / `dscr`

## Modeling notes

- All engine math uses `Decimal` and quantizes to `Numeric(18, 6)` precision.
- `entitlement` is currently mapped to `pre_construction` in persisted `CashFlow.period_type` rows.
- Stage 1A is operational-first, so leverage outputs use temporary placeholders until the capital stack engine is implemented:
  - `debt_service = 0`
  - `project_irr_levered = project_irr_unlevered`
  - `dscr = 1.250000`

## Run tests

From `re-modeling/`:

```bash
python -m pytest tests/engines/test_cashflow.py -q
```

The test first tries the seeded deal UUID `e0000000-0000-0000-0000-000000000003` and, if absent, creates a minimal fallback fixture deal inside the test database.
