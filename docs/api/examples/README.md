# API Payload Examples

Representative create, update, and read payloads for the `re-modeling` API.

> These examples mirror the public OpenAPI schema examples exposed in `/docs` and use the current contract shape from the FastAPI routers.

## Common headers

```http
X-API-Key: <your-api-key>
X-User-ID: 22222222-2222-2222-2222-222222222222
Content-Type: application/json
```

> **Precision note:** money, rate, and ratio fields are serialized as strings (for example `"1250000"` or `"5.5"`) so client apps do not lose decimal precision.

---

## 1) Create and read a project

### `POST /projects`

```json
{
  "name": "Burnside Courtyard Apartments",
  "org_id": "11111111-1111-1111-1111-111111111111",
  "created_by_user_id": "22222222-2222-2222-2222-222222222222",
  "status": "active",
  "project_category": "proposed",
  "source": "manual"
}
```

### `GET /projects/{project_id}` response

```json
{
  "id": "33333333-3333-3333-3333-333333333333",
  "name": "Burnside Courtyard Apartments",
  "org_id": "11111111-1111-1111-1111-111111111111",
  "created_by_user_id": "22222222-2222-2222-2222-222222222222",
  "status": "active",
  "project_category": "proposed",
  "source": "manual",
  "created_at": "2026-04-03T12:00:00Z"
}
```

---

## 2) Create and read a deal model

### `POST /projects/{project_id}/models`

```json
{
  "project_id": "33333333-3333-3333-3333-333333333333",
  "created_by_user_id": "22222222-2222-2222-2222-222222222222",
  "name": "Base Case",
  "version": 1,
  "is_active": true,
  "project_type": "acquisition_minor_reno"
}
```

### `GET /projects/{project_id}/models` item

```json
{
  "id": "44444444-4444-4444-4444-444444444444",
  "project_id": "33333333-3333-3333-3333-333333333333",
  "created_by_user_id": "22222222-2222-2222-2222-222222222222",
  "name": "Base Case",
  "version": 1,
  "is_active": true,
  "project_type": "acquisition_minor_reno",
  "created_at": "2026-04-03T12:00:00Z"
}
```

### `GET /models/{model_id}/inputs` response

```json
{
  "id": "88888888-8888-8888-8888-888888888888",
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "unit_count_existing": 12,
  "purchase_price": "1250000",
  "closing_costs_pct": "2.0",
  "hold_period_years": "5",
  "exit_cap_rate_pct": "5.5",
  "selling_costs_pct": "2.0"
}
```

---

## 3) Create, update, and read an income stream

### `POST /models/{model_id}/income-streams`

```json
{
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "stream_type": "residential_rent",
  "label": "Market Rent",
  "unit_count": 12,
  "amount_per_unit_monthly": "1650",
  "stabilized_occupancy_pct": "95",
  "escalation_rate_pct_annual": "2.5",
  "active_in_phases": ["lease_up", "stabilized", "exit"]
}
```

### `PATCH /models/{model_id}/income-streams/{stream_id}`

```json
{
  "label": "Renovated Market Rent",
  "amount_per_unit_monthly": "1825",
  "escalation_rate_pct_annual": "3.0",
  "active_in_phases": ["lease_up", "stabilized", "exit"]
}
```

### `GET /models/{model_id}/income-streams` item

```json
{
  "id": "55555555-5555-5555-5555-555555555555",
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "stream_type": "residential_rent",
  "label": "Market Rent",
  "unit_count": 12,
  "amount_per_unit_monthly": "1650",
  "stabilized_occupancy_pct": "95",
  "escalation_rate_pct_annual": "2.5",
  "active_in_phases": ["lease_up", "stabilized", "exit"]
}
```

---

## 4) Create, update, and read a capital module

### `POST /models/{model_id}/capital-modules`

```json
{
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "label": "Senior Loan",
  "funder_type": "debt",
  "stack_position": 1,
  "source": {
    "amount": "850000",
    "interest_rate_pct": 6.5,
    "funding_date_trigger": "construction_start"
  },
  "carry": {
    "carry_type": "io_only",
    "io_period_months": 12,
    "payment_frequency": "monthly",
    "capitalized": false
  },
  "exit_terms": {
    "exit_type": "full_payoff",
    "trigger": "sale",
    "notes": "Pay off at disposition"
  },
  "active_phase_start": "acquisition",
  "active_phase_end": "exit"
}
```

### `PATCH /models/{model_id}/capital-modules/{capital_module_id}`

```json
{
  "label": "Senior Loan - Requoted",
  "source": {
    "amount": "900000",
    "interest_rate_pct": 6.1
  },
  "carry": {
    "carry_type": "pi",
    "payment_frequency": "monthly",
    "capitalized": false
  }
}
```

### `GET /models/{model_id}/capital-modules` item

```json
{
  "id": "99999999-9999-9999-9999-999999999999",
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "label": "Senior Loan",
  "funder_type": "debt",
  "stack_position": 1,
  "source": {
    "amount": "850000",
    "interest_rate_pct": 6.5
  },
  "carry": {
    "carry_type": "io_only",
    "payment_frequency": "monthly",
    "capitalized": false
  },
  "exit_terms": {
    "exit_type": "full_payoff",
    "trigger": "sale"
  },
  "active_phase_start": "acquisition",
  "active_phase_end": "exit",
  "created_at": "2026-04-03T12:00:00Z"
}
```

---

## 5) Read outputs and waterfall report

### `GET /models/{model_id}/outputs`

```json
{
  "id": "77777777-7777-7777-7777-777777777777",
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "total_project_cost": "1450000",
  "equity_required": "400000",
  "total_timeline_months": 36,
  "noi_stabilized": "198000",
  "cap_rate_on_cost_pct": "6.2",
  "dscr": "1.45",
  "project_irr_levered": "15.7",
  "project_irr_unlevered": "11.9",
  "computed_at": "2026-04-03T12:00:00Z"
}
```

### `GET /models/{model_id}/waterfall/report`

```json
{
  "deal_model_id": "44444444-4444-4444-4444-444444444444",
  "investor_count": 1,
  "total_cash_distributed": "27000",
  "investors": [
    {
      "capital_module_id": "99999999-9999-9999-9999-999999999999",
      "investor_name": "LP Equity",
      "funder_type": "common_equity",
      "stack_position": 1,
      "committed_capital": "40000",
      "total_cash_distributed": "27000",
      "ending_cumulative_distributed": "27000",
      "latest_party_irr_pct": "14.2",
      "equity_multiple": "0.675",
      "cash_on_cash_year_1_pct": "50.0",
      "share_of_total_distributions_pct": "100.0",
      "timeline": [
        {
          "period": 1,
          "cash_distributed": "5000",
          "cumulative_distributed": "5000"
        }
      ]
    }
  ]
}
```
