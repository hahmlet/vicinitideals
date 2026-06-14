# Market Data Model Reference

This document defines how the platform generates market-based
revenue and expense recommendations for deals.  It is the market
intelligence counterpart of `FINANCIAL_MODEL.md` (cashflow math) and
`DATA_MODEL.md` (entity model and reconciliation).

**Last updated**: 2026-04-16

> **Status (2026-06):** The KNN comp engine is **retained** but is not yet a production
> deal-creation feature (Integration Points in §5 remain planned). The decommissioned
> *data-acquisition* pieces that fed it — the **LoopNet** comp source and the **HelloData**
> enrichment harness — are gone; their detail moved to the **Archive** at the end of this
> doc. KNN now sources every feature-vector input from `Opportunity` own-fields
> (`unit_count`, `year_built`, `building_sqft`, `jurisdiction`/`city`), not from a linked parcel.

---

## 1. Overview

When a user creates a deal, the platform recommends income and
operating expense assumptions based on comparable properties in the
market data pool.  Rather than hard-coded benchmarks or static
clusters, the system uses **K-Nearest Neighbors (KNN) interpolation**
against a pool of listings with known financials.

Every deal gets a unique weighted blend from its nearest neighbors in
a normalized feature space.  There are no predefined clusters — the
"synthetic comp" is computed on-the-fly as a weighted average of the
K most similar properties.

### Why KNN Over Static Clusters

- **No arbitrary boundaries** — a 1979 building pulls from neighbors
  on both sides of any decade line, weighted by actual similarity.
- **Graceful with small samples** — with ~50 comps, hard clusters of
  3–4 properties each are statistically unreliable.  KNN with K=5–10
  uses 10–20% of the pool per query, giving reasonable estimates.
- **Self-improving** — adding properties (from HelloData quarterly
  dumps, manual enhancement, or new scrapes) improves results without
  reconfiguring cluster definitions.
- **Auditable** — every recommendation shows "these N properties
  informed this assumption, weighted as follows."

---

## 2. Comp Pool

### 2.1 Eligibility Criteria

A listing qualifies as a market comp when it has:

| Field | Required | Rationale |
|---|---|---|
| `unit_count` | > 0 | Feature vector dimension |
| `year_built` | Present, < 2100 | Feature vector dimension |
| `asking_price` | Present | Needed for price/unit metric |
| `noi` | > 0 | Core financial output |
| `priority_bucket` | != `out_of_market` | In-market only |

**Current pool**: 50 eligible listings (as of 2026-04-16).

Optional fields that improve comp quality when present:
- `building_sqft` — enables sqft/unit and rent/sqft metrics
- `cap_rate` — cross-validation signal
- `occupancy_pct` — stabilized occupancy reference
- `jurisdiction` — geographic similarity dimension
- `property_type` — asset class matching

### 2.2 Data Sources (Current and Planned)

| Source | Status | Contribution |
|---|---|---|
| Crexi scraped listings | Active | Primary comp pool (~50 eligible) |
| Manual enhancement | Planned | UI for filling gaps in existing listings |

As new sources are added, eligible listings automatically join the
comp pool — no configuration changes needed.

> **Decommissioned:** the **LoopNet** comp source (subscription cancelled) and the
> **HelloData** quarterly enrichment dump were removed — see Archive. Crexi is the
> only live comp source.

---

## 3. Feature Vector and Distance

### 3.1 Dimensions

Each property is represented as a point in a normalized feature space:

| Dimension | Raw Field | Normalization | Weight | Rationale |
|---|---|---|---|---|
| **Unit count** | `unit_count` | log₂ scale | 1.0 | Log scale because 10→20 units is a bigger jump than 100→110 |
| **Vintage** | `year_built` | (year - 1900) / 130 | 0.8 | Normalized to [0, 1] range; slightly less important than size |
| **Size per unit** | `building_sqft / unit_count` | value / 1500 | 0.6 | Normalized around ~1500 sqft/unit median; NULL → excluded from distance |
| **Location** | `jurisdiction` | Categorical match | 0.5 | Same jurisdiction = 0 distance, different = 1.0 |

### 3.2 Distance Function

Weighted Euclidean distance with NULL-tolerant dimensions:

```
distance(A, B) = sqrt(
    w_units  × (log2(A.units) - log2(B.units))² +
    w_vintage × (norm(A.year) - norm(B.year))² +
    w_sqft   × (norm(A.sqft_per_unit) - norm(B.sqft_per_unit))²  [if both present] +
    w_location × (0 if same jurisdiction, 1 otherwise)²
) / sum_of_active_weights
```

When a dimension is NULL for either property, that dimension is
excluded from the distance calculation and its weight is removed from
the denominator.  This allows comps with missing `building_sqft` to
still participate.

### 3.3 Similarity Score

```
similarity = 1 / (1 + distance)
```

Range: (0, 1].  Used as weight when blending neighbor values.

---

## 4. KNN Query

### 4.1 Parameters

| Parameter | Default | Notes |
|---|---|---|
| K (neighbors) | 7 | Returns up to K nearest; fewer if pool is small |
| Max distance | 2.0 | Exclude very dissimilar properties |
| Min comps | 3 | Below this, return results but flag as low-confidence |

### 4.2 Algorithm

1. Compute distance from subject property to every eligible comp
2. Exclude comps beyond `max_distance`
3. Sort by distance ascending
4. Take top K
5. Compute similarity weights: `w_i = similarity_i / sum(similarities)`
6. Blend output metrics using weights

### 4.3 Output Metrics (Weighted Averages)

| Metric | Formula | Used For |
|---|---|---|
| `noi_per_unit` | `weighted_avg(comp.noi / comp.units)` | NOI mode prefill |
| `price_per_unit` | `weighted_avg(comp.price / comp.units)` | Acquisition pricing reference |
| `cap_rate` | `weighted_avg(comp.cap_rate)` [where present] | Exit cap reference |
| `occupancy_pct` | `weighted_avg(comp.occupancy)` [where present] | `IncomeStream.stabilized_occupancy_pct` |
| `noi_per_sqft` | `weighted_avg(comp.noi / comp.sqft)` [where present] | Alternative scaling basis |
| `price_per_sqft` | `weighted_avg(comp.price / comp.sqft)` [where present] | Alternative scaling basis |
| `implied_opex_per_unit` | `weighted_avg((comp.price × comp.cap_rate - comp.noi) / comp.units)` | Cross-check only |

### 4.4 Confidence Indicators

| Indicator | Meaning |
|---|---|
| `comp_count` | Number of comps used (K or fewer) |
| `avg_distance` | Mean distance to comps (lower = better match) |
| `avg_similarity` | Mean similarity score |
| `low_confidence` | True if `comp_count < min_comps` |
| `nearest_comp` | Most similar property (address + distance) |
| `farthest_comp` | Least similar of K (shows how far the blend stretches) |

---

## 5. Integration Points

### 5.1 Deal Creation (Planned)

At `deal_setup_wizard_complete()`, after creating blank IncomeStream
and OperatingExpenseLine rows:

1. Query KNN for the deal's subject property characteristics
   (units, vintage, sqft/unit, jurisdiction — all from `Opportunity` own-fields;
   the former linked-parcel source was decommissioned)
2. If sufficient comps found (>= `min_comps`):
   - Prefill `IncomeStream.amount_per_unit_monthly` from
     `noi_per_unit / 12` (as a starting point)
   - Prefill `OperationalInputs.noi_stabilized_input` from
     `noi_per_unit × units` (for NOI mode)
   - Store comp summary on the deal for display
3. User always sees and can override the prefilled values
4. Model builder shows "Market: $X/unit (N comps, avg similarity Y%)"
   alongside the user's assumption

### 5.2 Market Reference Panel (Planned)

In the model builder, a collapsible panel showing:
- The K comps used, sorted by similarity
- Per-comp: address, units, vintage, NOI/unit, price/unit, similarity %
- Weighted average vs. user's current assumption
- "Re-run with different parameters" option

### 5.3 Quarterly Refresh (Planned)

> The HelloData quarterly-dump trigger was **decommissioned** (see Archive); manual
> enhancement is the remaining refresh path.

When new eligible listings are ingested:
1. New properties meeting eligibility criteria join the comp pool
2. Existing deals do NOT auto-update (user's assumptions are final)
3. User can manually "re-run market recommendations" to see updated comps

---

## 6. Future Enhancements

### 6.1 HelloData Integration — DECOMMISSIONED (removed 2026-06)

The HelloData.ai enrichment harness (`app/scrapers/hellodata.py`) was removed in the
decommission (DC-2). Its full historical detail is preserved in the **Archive** at the
end of this doc. The `hellodata_*` columns on `opportunities` were intentionally **kept**
(deferred drop) but are no longer written; comp eligibility and NOI seeding now fall back
to broker-reported Crexi fields + manual entry.

### 6.2 Future Enhancements

- **Per-unit-type rent recommendations** — HelloData returns rent per floorplan
  (studio, 1BR, 2BR).  Current synthesis averages these; a future enhancement
  could break out UnitMix-level recommendations when the deal's UnitMix has
  multiple rows.
- **Confidence ranges** — HelloData returns 20th/80th percentile bounds for
  expense distributions.  These could surface as "market range" alongside
  the single recommendation.
- **Expense line-item decomposition** — HelloData provides individual line
  items (property tax, insurance, utilities, etc.) that could prefill the
  19-line OpEx template instead of just the aggregate NOI.

### 6.2 Enhancement UI

Keyboard-driven triage view for manually filling financial data gaps
on existing listings.  Increases comp pool size and quality.

### 6.3 Feature Vector Expansion

Additional dimensions as data quality improves:
- Property class (A/B/C) from HelloData quality scores
- Submarket (more granular than jurisdiction)
- Unit mix composition (% studios vs. 1BR vs. 2BR)
- Proximity to transit/amenities

### 6.4 Expense Ratio Decomposition

When HelloData expense benchmarks are available, the KNN output
expands from single `noi_per_unit` to per-line OpEx estimates:
- Property tax / unit
- Insurance / unit
- Management fee %
- Utilities / unit
- Maintenance / unit
- etc.

These would prefill the 19-line OpEx template with market-derived
values instead of $0.

---

## 7. Design Decisions

1. **No static clusters** — KNN interpolation over the full comp pool.
   Every deal gets a unique blend.  Avoids bias-variance tradeoff of
   choosing cluster boundaries with small sample sizes.

2. **Log scale for unit count** — The difference between 5 and 10 units
   is more significant than between 95 and 100 units.

3. **Jurisdiction as categorical** — Same = 0, different = 1.  No
   attempt to model geographic distance between jurisdictions (Portland
   and Gresham are equally "different" from each other).  This may
   evolve to lat/lng distance if comp pool grows.

4. **NULL-tolerant distance** — Missing dimensions are excluded rather
   than imputed.  A comp with NULL sqft still participates using its
   other dimensions.  This maximizes pool utilization with incomplete
   data.

5. **Recommendations are suggestions, not constraints** — The user
   always sees the source comps and can override every value.  The
   system never forces market assumptions onto a deal.

6. **Comp pool queries `scraped_listings` directly** — No separate
   comp table.  Eligibility is a WHERE clause, not a data copy.  This
   means any listing enhancement immediately improves the comp pool.

---

## 8. Key Constants

| Constant | Value | Location |
|---|---|---|
| `DEFAULT_K` | 7 | `app/engines/market.py` |
| `MAX_DISTANCE` | 2.0 | `app/engines/market.py` |
| `MIN_COMPS` | 3 | `app/engines/market.py` |
| `WEIGHT_UNITS` | 1.0 | `app/engines/market.py` |
| `WEIGHT_VINTAGE` | 0.8 | `app/engines/market.py` |
| `WEIGHT_SQFT_PER_UNIT` | 0.6 | `app/engines/market.py` |
| `WEIGHT_LOCATION` | 0.5 | `app/engines/market.py` |
| `SQFT_PER_UNIT_NORM` | 1500 | `app/engines/market.py` |

These are tunable.  As the comp pool grows, weights may be adjusted based on
backtesting recommendation accuracy against known deal outcomes.

---

## Archive — Decommissioned Comp Data Sources

> **🗄 ARCHIVED — does not reflect the live system.** The KNN engine itself is retained
> (see §1–§8). What was removed are the *data-acquisition* sources that fed it. Crexi
> remains the only live comp source; KNN sources its feature-vector inputs from
> `Opportunity` own-fields. The `hellodata_*` columns on `opportunities` were kept
> (deferred drop) but are no longer written.

### A1. LoopNet comp source

LoopNet scraped listings were a secondary comp source (subscription cancelled, scraper
removed in DC-1). When active, eligible LoopNet listings joined the comp pool on the same
eligibility criteria as Crexi (§2.1).

### A2. HelloData enrichment harness (was §6.1 — SHIPPED 2026-04-17, removed 2026-06)

The HelloData.ai enrichment harness (`app/scrapers/hellodata.py`) called four endpoints
per property (~$1.50/listing at default rates):

| Endpoint | Purpose | Stored On Opportunity |
|---|---|---|
| `/property/search` | Resolve HelloData property ID | `hellodata_property_id`, `hellodata_raw_search` |
| `/property/market_rents` | Unit-level rent predictions | `hellodata_raw_rents`, synthesized `hellodata_market_rent_per_unit/sqft` |
| `/property/expense_benchmarks` | ML-predicted OpEx + NOI | `hellodata_raw_expenses`, synthesized `hellodata_egi_per_unit`, `hellodata_noi_per_unit`, `hellodata_opex_per_unit`, `hellodata_occupancy_pct` |
| `/property/comparables` | Optional: nearby comps | `hellodata_raw_comparables` |

**Budget enforcement** (`HelloDataUsage` table):
- Monthly cost cap in cents (default $100/month)
- Per-call cost configurable in `settings.hellodata_cost_per_call_cents` (default 50)
- Hard lock once monthly budget is reached
- Per-run `--max-dollars` cap via CLI

**Portland exclusion** (safety):
- `_is_portland()` checks `jurisdiction` then `city` against
  `PORTLAND_JURISDICTION_VALUES`.  Portland listings were never paid for,
  enforcing the CLAUDE.md Market Coverage Policy.

**Comp pool integration** (while active):
- Eligibility filter accepted listings with EITHER broker NOI OR
  `hellodata_noi_per_unit > 0`.
- `CompResult.noi_source` recorded `"broker"` vs `"hellodata"` for audit.
- Broker-reported NOI won when present; HelloData synthesized values filled the gap
  for listings without broker financials. Same preference order applied to occupancy.

**CLI** (removed): `docker exec vicinitideals-api python -m app.scripts.enrich_hellodata`

### A3. Parcel-derived KNN inputs

Before the parcel decommission (migration 0113), KNN sourced subject-property
characteristics (units, vintage, sqft/unit, jurisdiction) from the linked **parcel**.
These now come from `Opportunity` own-fields; the distance math (§3) is unchanged.
