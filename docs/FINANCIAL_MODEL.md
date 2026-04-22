# Vicinitideals Financial Model — Math, Assumptions, and Justification

**Purpose.** This document is the source of truth for every formula the cashflow and waterfall engines use. If someone asks "what is this math based on?", the answer lives here. Each section gives:

1. The variable-form formula (as it appears in code)
2. A plain-English translation using CRE conventions
3. Why we chose that formulation over alternatives
4. The specific file/line reference in the codebase

**Scope.** Sources, Uses, Revenue, OpEx, Reserves, Period Cash Flow, Debt Service, Waterfall, Profit Metrics (IRR/MOIC/Cash-on-Cash). The schema is defined in `app/models/*.py`; the math lives in `app/engines/cashflow.py` and `app/engines/waterfall.py`.

**Conventions used throughout.**
- `TPC` = Total Project Cost (all non-exit, non-balance-only Use lines)
- `P` = principal of a sized loan
- `f_c` = construction interest factor (fraction of principal consumed by construction-period interest)
- `f_m` = monthly P&I payment factor (standard amortization)
- `L` = lease_up_months
- `R` = operation_reserve_months
- `N` = number of months in a loan's active phase (for carry calculations)
- `NOI` = Net Operating Income (annual unless specified)
- `DS` = Debt Service
- `EGI` = Effective Gross Income (gross revenue − vacancy loss)
- `DSCR` = NOI / DS

### Multi-project engine (Phase 2, merged 2026-04-21) — math unchanged per project

Migrations `0048` (junction + anchors), `0050` (`project_id` on cashflow output tables), and `0051` (UNIQUE swap) let one Scenario compute N Projects' cashflows independently. The engine loops per project; each project reads its own UseLines, IncomeStreams, OpEx, OperationalInputs, Milestones, and a junction-filtered view of CapitalModules. Output rows (CashFlow, CashFlowLineItem, OperationalOutputs) carry `project_id`. The `app/engines/underwriting_rollup.py` module aggregates across projects for Scenario-level display.

**None of the formulas in this document changed.** Every per-project computation runs the same math as pre-Phase-2: same TPC, same auto-sizing, same carry types, same DSCR convergence, same XIRR, same waterfall. Validated byte-identical against 5 baseline prod scenarios (`tests/phase2_baseline/*.json`).

### Shared Sources — independent sizing, grouped display

A **shared Source** is one `CapitalModule` (one contract identity — one lender, one rate, one carry_type, one exit vehicle) attached to multiple Projects via `capital_module_projects` junction rows. Product decision (2026-04-21): each project sizes its own share against its own numbers. No cross-project constraint pooling.

- **Per-project sizing**: Project A's share of Source-1 is sized on A's DSCR / LTV / gap-fill against A's uses. Project B's share is sized on B's. Total principal on the loan = Σ per-project principals.
- **Per-project carry / IR / CI**: each project's `Interest Reserve` / `Capitalized Construction Interest` / `Acquisition Interest` UseLine is sized on that project's own uses × carry factor, where the carry factor's `N` comes from the module's active window (which in turn is bounded by the exit vehicle). Since a shared Source has one exit vehicle, `N` is the same across covering projects.
- **Draw cadence**: at the engine's month-level resolution, joint cadence (one requisition on the 1st) and independent cadence (each project draws on its own schedule) produce identical numbers, because the cadence factor `(N+1)/2` (interest_reserve) or `N` (capitalized_interest) is calendar-month-integer-based. Day-level divergence (Project A draws on day 1, Project B draws on day 15 and pays 2 extra weeks of carry) is not representable at month resolution. Phase 2f joint-cadence code is deferred until day-level modeling lands.
- **Underwriting-level DSCR / LTV on a shared Source**: informational notification only. No feedback into sizing.
- **Rollup display**: `rollup_sources` returns one row per CapitalModule with `total_principal = Σ junction.amount`, `covered_project_ids`, and `is_shared: bool`. The UI draws a "covers: P1, P2" chip on shared rows.

### Underwriting rollup CF display — NOI-focused (Phase 3a)

The Underwriting tab's Combined Cashflow table shows only **NOI / Debt Service / Net CF** — no Revenue, EGI, or OpEx columns. Reason: only these three fields sum meaningfully when projects are in different income modes.

| Field | NOI-mode contribution | Rev/OpEx-mode contribution | Summable across modes? |
|---|---|---|---|
| NOI | stabilized NOI input | revenue − opex | ✅ always |
| Debt Service | ✅ | ✅ | ✅ always |
| Net CF | ✅ | ✅ | ✅ always |
| Revenue / EGI | == NOI (by construction) | revenue − vacancy | ⚠️ inflates combined total for mixed |
| OpEx | $0 (no breakout) | actual opex | ⚠️ under-reports combined total for mixed |

Today `income_mode` is a scenario-level setting (one value per Scenario, applied to every Project). The "mixed mode across projects" case is not yet possible in prod — but the NOI-focused rollup is the right design regardless, because:

- All-NOI scenarios: showing Revenue/OpEx $0 alongside NOI is just noise.
- All-Rev/OpEx scenarios: the detail is still available per-project on the Cashflow module panel; the Underwriting tab is a lender-summary view, not a line-level projection.
- Mixed scenarios (future, when `income_mode` might become per-project): NOI / DS / Net CF are the only columns that stay honest.

The per-project Cashflow module panel shows a purple "Mode: NOI" chip in its header when that scenario is in NOI mode, so operators looking for missing Revenue/OpEx rows see the reason immediately.

### Cross-project compute order

`app/engines/anchor_resolver.py` orders projects via Kahn topological sort over `project_anchors` rows (anchored project runs after its parent). Cycles raise `AnchorCycleError`. Zero-anchor scenarios fall through to `sorted(created_at)` — byte-identical to pre-Phase-2 ordering. Anchor-driven milestone-date resolution (walking the chain + applying offsets) is deferred (2d1); presently the Deal / Underwriting start date = `min(project.start_date)` set per project in the wizard.

---

---

## 1. Uses / Total Project Cost (TPC)

### 1.1 What TPC is

TPC is the sum of every capital outflow required to acquire, build, lease up, and stabilize the project. It is **not** the sum of "hard costs" in the CRE sense — it includes every cost line except sale proceeds and derived/balance-only entries.

**Code (cashflow.py, `total_uses` computation around line 691):**
```python
total_uses = ZERO
for ul in use_lines:
    phase_str = str(getattr(ul.phase, "value", ul.phase))
    if phase_str == "exit":
        continue
    if getattr(ul, "label", "") in _BALANCE_ONLY_LABELS:
        continue
    total_uses += _to_decimal(ul.amount)
```

**Plain English.** Sum every Use line across every phase of the deal, **except**:
- Anything in the `exit` phase (those are sale-related costs subtracted from proceeds, not uses)
- Anything whose label is "balance-only" (see 1.2)

### 1.2 Balance-only Use line exclusions

These labels are excluded from the TPC sum because they are derived from debt sizing itself — including them would double-count the same dollars:

```python
_BALANCE_ONLY_LABELS = {
    "Operating Reserve",
    "Capitalized Construction Interest",
    "Construction Interest Reserve",          # legacy label (pre-rename)
    "Capitalized Pre-Development Interest",
    "Capitalized Acquisition Interest",
    "Interest Reserve",                       # construction IR (new)
    "Pre-Development Interest Reserve",
    "Acquisition Interest Reserve",
    "Lease-Up Reserve",
}
```

**Why.** These are all solved algebraically after debt sizing:
- **Operating Reserve**: `max(OpEx_monthly, DS_monthly) × reserve_months` — depends on the principal we are trying to compute.
- **Interest Reserve / Capitalized Interest**: depends on the principal via `IR = P × rate × months_factor`.
- **Lease-Up Reserve**: depends on perm principal via `(P × pmt_factor × L) − income_offset`.

If these were added to TPC before sizing, we would be asking the lender to cover its own interest bucket with its own principal — a circular double-count.

### 1.3 Phase-based Use line sums (for bridge loan sizing)

In Phase B multi-debt deals, each bridge loan is sized to the costs in its phase:

```python
def _phase_cost_sum(phase_set: set) -> Decimal:
    return sum(
        (_to_decimal(ul.amount)
         for ul in use_lines
         if str(getattr(ul.phase, "value", ul.phase) or "") in phase_set
         and getattr(ul, "label", "") not in _BALANCE_ONLY_LABELS
         and getattr(ul, "label", "") not in _cc_labels),
        ZERO,
    )

pre_dev_costs  = _phase_cost_sum({"pre_construction"})
acq_costs      = _phase_cost_sum({"acquisition", "other"})
constr_costs   = _phase_cost_sum({"construction", "renovation", "conversion"})
```

**Plain English.** The pre-development loan covers costs in the `pre_construction` phase; the acquisition loan covers `acquisition` phase costs (entitlement fees, diligence, purchase price for some deals); the construction loan covers hard-construction costs during `construction` / `renovation` / `conversion` phases.

**Why the `_cc_labels` exclusion?** Closing costs (origination fees, legal, title, appraisal, Phase I ESA) auto-fire at the loan's `active_phase_start`. If we sized the construction loan to include its own origination fee, the fee would grow the loan, which would grow the fee, which would grow the loan — a circular reference. Instead, closing costs are financed by the permanent debt gap-fill, never by the bridge loan being closed. See §2.5.

---

## 2. Sources / Debt Sizing

### 2.1 Two paths: Legacy and Phase B (multi-debt)

**Legacy** (kept for deals predating the multi-debt rewrite):
- `OperationalInputs.debt_structure` ∈ {`perm_only`, `construction_and_perm`, `construction_to_perm`}
- Single construction + permanent loan pair
- Untouched by any Phase B logic

**Phase B multi-debt** (all new deals):
- `OperationalInputs.debt_types`: ordered list like `["pre_development_loan", "acquisition_loan", "construction_loan", "permanent_debt"]`
- Bridge loans sized independently to phase costs, then removed from the gap-fill pool
- Permanent debt gap-fills to TPC

The Phase B path is gated by `if debt_types_list:` in `_auto_size_debt_modules()`.

### 2.2 Carry types (pre-operation interest treatment)

There are **four** economically distinct ways a loan can handle interest before operations begin. Each produces a different principal for the same base cost, and each shows up differently on the S&U.

| Carry type | Periodic DS? | Balance at takeout | Sizing factor |
|---|---|---|---|
| `io_only` (True IO) | Yes — cash paid monthly | Flat (= base cost) | `f_io = 0` |
| `interest_reserve` | No — pre-funded pool | Base cost only | `f_io = rate/12 × (N+1)/2` |
| `capitalized_interest` | No — PIK accrual | Base + accrued interest | `f_io = rate/12 × N` |
| `pi` | Yes — amortized | Decreasing | N/A (standard amort) |

**Why four, not three?** Industry references (Argus, REFM, FDIC handbook) consistently separate True IO from Interest Reserve. Our engine formerly conflated them; Phase 1 of the carry-type rewrite (April 2026) split them to match practice.

**The average-draw factor for Interest Reserve.** Industry convention often cites "50% of the commitment" as the IR factor. That is the large-N limit of a precise formula we can compute exactly because we model monthly draws:

> For `N` evenly spaced monthly draws, the average outstanding balance over the construction period is `(N+1)/(2N)` of the full commitment. Multiplied by the monthly rate, the interest-consumption fraction is `rate/12 × (N+1)/2`.

For `N = 12`, that is `rate/12 × 6.5 = 0.5417 × rate`. Compared to the naive 50% heuristic, the exact factor is 8% larger — material on short construction timelines.

**The full-balance factor for Capitalized Interest.** Capitalized interest (PIK) accrues on the full commitment from day one — there is no "average draw", because the lender imputes full balance. The factor is `rate/12 × N`.

**Code (cashflow.py, construction loan branch around line 958):**
```python
elif _ft == "construction_loan":
    _r = Decimal(str(_cr or 0))
    _cl_ct = _carry_type_for_phase(_carry, is_construction=True)
    _n = _loan_pre_op_months(_m)   # per-loan active-window months (see §2.8)
    if _cl_ct == "interest_reserve":
        _io_f = (_r / HUNDRED / Decimal("12")
                 * (Decimal(_n + 1) / Decimal("2"))
                 ) if (_r > ZERO and _n > 0) else ZERO
    elif _cl_ct == "capitalized_interest":
        _io_f = (_r / HUNDRED / Decimal("12") * Decimal(_n)
                 ) if (_r > ZERO and _n > 0) else ZERO
    else:  # io_only
        _io_f = ZERO
    _div = ONE - _io_f
    _principal = _q(constr_costs / _div) if (_div > ZERO and constr_costs > ZERO) else constr_costs
```

> **April 2026 change:** `constr_months_total` was replaced by `_loan_pre_op_months(_m)` which computes month count within each loan's `[active_phase_start, active_phase_end)` window. See §2.8 for details.

**Derivation of the principal solve.** We want the principal `P` to cover both base costs and interest:
> `P = base_costs + interest_consumed = base_costs + P × f_io`
> Solving for `P`: `P × (1 − f_io) = base_costs`, so `P = base_costs / (1 − f_io)`.

This is self-consistent: the interest amount `P − base_costs = P × f_io / (1 − f_io) × (1 − f_io) / 1 = base × f_io / (1 − f_io)`.

### 2.3 Bridge loan sizing (per funder type)

#### Pre-development loan
**Formula.** `P_predev = pre_dev_costs / (1 − f_io)` where `f_io` uses pre_dev_months and pre_dev_rate.

**Plain English.** Size the pre-dev loan to cover pre-construction costs (entitlements, design, diligence) plus whatever pre-opening interest its carry type produces.

#### Acquisition loan
**Formula.** `P_acq = acq_costs × LTV / 100`

**Plain English.** Size to a loan-to-value percent of acquisition-phase costs. Default LTV = 70% unless overridden in `debt_terms.acquisition_loan.ltv_pct`.

**Why LTV and not gap-fill?** Acquisition loans are sized on the appraised value of what is being acquired, not on the residual capital stack. LTV is the standard industry input.

#### Construction loan
**Formula.** `P_constr = constr_costs / (1 − f_io)` — same shape as pre-dev, with construction months and construction rate.

#### Bridge (generic)
No auto-sizing; whatever amount is on the module is used as-is. Bridge loans are often sized deal-by-deal on collateral value, so we leave it to the user.

**Why are bridges "removed" from the gap-fill pool?** After sizing, each bridge module is excluded from `auto_modules` (`auto_modules = [x for x in auto_modules if x is not _m]`). Only the permanent debt (or equity) gap-fills the remaining hole. Without this, the perm would shrink by whatever the bridge covered, breaking the Sources = Uses invariant.

### 2.4 Permanent debt — gap-fill solve

This is the core debt sizing formula. It is a closed-form solve for the principal that lands cash-at-stabilization exactly on the operating reserve target.

#### Derivation

Let:
- `P` = perm principal (what we're solving for)
- `TPC` = total uses (after bridge interest costs + perm flat closing costs have been added)
- `fixed` = fixed (non-auto-sized) sources (equity, grants, etc.)
- `I_lu` = lease-up income offset (see §2.6 below)
- `f_c` = constr_io_factor — 0 in Phase B multi-debt (the construction loan handles its own IO); nonzero only in the legacy single-loan path
- `f_m` = pmt_factor = `i·(1+i)^n / ((1+i)^n − 1)`, where `i = rate/12/100`, `n = amort_years × 12`
- `L` = lease_up_months
- `R` = operation_reserve_months

The gap-fill invariant is: **perm principal + fixed sources = TPC + construction IO + lease-up DS shortfall + operating reserve**.

Writing each term as a fraction of `P`:
> `P + fixed = TPC + P·f_c + (P·f_m·L − I_lu·L) + P·f_m·R`
> `P − P·f_c − P·f_m·(L + R) = TPC − fixed − I_lu·L`
> `P·(1 − f_c − f_m·(L + R)) = TPC − fixed − I_lu·L`
> `P = (TPC − fixed − I_lu·L) / (1 − f_c − f_m·(L + R))`

#### Code (cashflow.py, gap-fill solve in `_auto_size_debt_modules`)
```python
divisor = ONE - constr_io_factor
_m_cc = _cc_data.get(id(module))
if _m_cc and _m_cc["pct"] > ZERO:
    divisor -= _m_cc["pct"]                 # perm closing-cost % (see §2.5)

# effective_uses = TPC − fixed − lease_up_income_offset
effective_uses = total_uses - fixed - lease_up_income_offset

ds_divisor = divisor - pmt_factor * Decimal(reserve_months + lease_up_months)
if ds_divisor > ZERO:
    principal = _q(effective_uses / ds_divisor)
```

**Plain English.** Solve for the perm loan amount that:
1. Covers every non-exit Use line
2. Covers the construction IO carry (if the loan is bearing it — legacy only)
3. Covers its own closing-cost origination fee (via the divisor adjustment)
4. Covers the debt-service shortfall during lease-up (net of the 1/3 phantom NOI — see §2.6)
5. Leaves exactly `reserve_months × DS` in the bank at first stabilized month

If any of those terms is zero (no construction phase, no lease-up, etc.) the formula collapses gracefully — that term drops out.

**What if `ds_divisor ≤ 0`?** That means the principal requirement, reserves, and lease-up carry exceed the amortization budget — i.e., the deal can't support the requested reserve structure. The engine falls back to an opex-based reserve without lease-up adjustment (cashflow.py:1126).

### 2.5 Closing costs (Phase B only)

#### Defaults

Market-backed, April 2026 (sources: commloan.com, financelobby.com, aegisenvironmentalinc.com, mrrate.com):

```python
_DEFAULT_LOAN_COSTS = {
    "construction_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
        {"label": "Environmental Phase I", "flat": Decimal("2500")},
    ],
    "permanent_debt": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("0.5")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Appraisal",             "flat": Decimal("3500")},
        {"label": "Title",                 "flat": Decimal("2500")},
    ],
    "pre_development_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "acquisition_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
    ],
    "bridge": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "bond": [
        {"label": "Bond Issuance Fee",     "pct_of_principal": Decimal("1.0")},
        {"label": "Bond Counsel Legal",    "flat": Decimal("15000")},
    ],
}
```

**Why these specific numbers?**

| Cost | Range in market | Our default | Source |
|---|---|---|---|
| Construction orig | 0.5–2% (banks 0.5–1%, private 1–2%) | 1.0% | commloan, mrrate |
| Perm orig (agency/bank) | 0.25–1.0% | 0.5% | financelobby |
| Pre-dev / bridge orig | 1.5–3% | 1.5% (low end) | hurstlending, thecreditpeople |
| Lender legal | $3k–$15k (CMBS higher) | $5k (construction/perm); $3k (pre-dev/bridge) | rochfordlawyers, financelobby |
| ALTA survey + title | $2.5k–$10k combined | $3.5k | fastercapital |
| Appraisal (commercial) | $3k–$5k+ | $3.5k | loanbase |
| Phase I ESA | $2k–$5k | $2.5k (median) | aegisenvironmental, geoforward |
| Bond counsel | $10k–$25k | $15k | specialized muni convention |

These are **starting points**. Users can override any cost line in the S&U table and the engine will respect the override.

#### How flat vs. % costs are handled differently

**Flat costs** are known before sizing — they get added to `total_uses` directly:

```python
# (cashflow.py around line 995)
for _cc_obj in _cc_data.values():
    _cc_ref = _cc_obj["module"]
    if id(_cc_ref) in _auto_mod_ids:
        total_uses += _cc_obj["flat"]    # perm flat: add to TPC before gap-fill
    else:
        _cc_br_p = Decimal(str((_cc_ref.source or {}).get("amount") or 0))
        total_uses += _cc_obj["flat"]
        total_uses += _q(_cc_br_p * _cc_obj["pct"])   # bridge: principal known, add now
```

**Percent-of-principal costs** for the perm loan are the tricky case. The origination fee is `P × 0.5%`, but `P` is what we're solving for. We fold the % into the divisor:

> **Naive (wrong):** `P = TPC / divisor`, then origination fee = `P × 0.5%`. But then TPC should have grown by that fee, and P should have grown to cover it. Iterative, never converges in one pass.
>
> **Algebraic (correct):** `P × (1 − 0.5%) = TPC`, so `P = TPC / 0.995`. One pass, exact.

That is what the line `divisor -= _m_cc["pct"]` does — it extends the gap-fill divisor by the perm origination percent. The result is that on the first compute run, `Sources = Uses` holds exactly, not approximately.

**Verified April 2026**: all three Phase B regression tests pass with `Gap = $0` on first compute.

#### The `_cc_labels` exclusion from `_phase_cost_sum`

Closing cost Use lines live at `active_phase_start` of their loan. A construction loan's origination fee lives in `pre_construction`, because that's when the loan closes. But `pre_construction` is also the phase that sizes the pre-dev loan. Without an exclusion, the pre-dev loan would grow to cover the construction loan's origination fee — wrong.

We pre-compute the full set of closing-cost labels before calling `_phase_cost_sum`:

```python
_cc_labels: set[str] = set()
for _pre_cm in capital_modules:
    _pre_ft = str(getattr(_pre_cm, "funder_type", "") or "").replace("FunderType.", "")
    if _pre_ft not in _DEFAULT_LOAN_COSTS or not (_pre_cm.source or {}).get("auto_size"):
        continue
    _pre_cm_lbl = getattr(_pre_cm, "label", "") or _pre_ft.replace("_", " ").title()
    for _pre_cost in _DEFAULT_LOAN_COSTS[_pre_ft]:
        _cc_labels.add(f"{_pre_cm_lbl} — {_pre_cost['label']}")
```

`_phase_cost_sum` skips anything in this set. Closing costs are still in TPC (through the `_cc_data` additions after bridge sizing), so the permanent loan still covers them. They simply don't inflate the bridge loans.

#### User override sentinel

- `amount == 0` (or the Use line doesn't exist) → engine computes from the default table and writes the line
- `amount > 0` → user override — engine leaves it alone and counts it through normal `total_uses`

Users can adjust any closing cost in the S&U table directly. If their actual deal has a 2% origination fee on a construction loan, they change the dollar amount and the engine respects it on the next compute.

### 2.6 The lease-up income offset — why `1/3`, not `1/2`

During lease-up, the perm loan is accruing debt service but income is ramping. The gap-fill formula must decide how much lease-up income to credit against the debt burden. Naive linear accounting would use 50% (half of stabilized, since occupancy ramps 0→100% linearly). That is wrong.

**Why 50% overstates lease-up income.** Operating costs don't scale linearly with occupancy — fixed costs (salaries, insurance, property tax) persist from day one. Variable costs (utilities, maintenance) do scale. A reasonable model is opex ramping from 50% → 100% over lease-up, while revenue ramps 0% → 100%.

**Derivation, assuming 60/40 revenue/opex split at stabilization:**

Let `R` = stabilized revenue, `E` = stabilized opex, `NOI_stab = R − E`. Assume `R = 0.6 × gross`, `E = 0.4 × gross`. Revenue ramps linearly `0 → R`, opex ramps linearly `0.5E → E`.

> Avg revenue over lease-up = 0.5 × R
> Avg opex over lease-up = 0.75 × E
> Avg NOI during lease-up = 0.5R − 0.75E
> Avg NOI as a fraction of stabilized NOI = (0.5R − 0.75E) / (R − E)

With `R = 833k, E = 333k, NOI_stab = 500k`:
> (0.5 × 833 − 0.75 × 333) / 500 = (417 − 250) / 500 = 167 / 500 = **1/3**

**Month-by-month check** (`L = 9`):

| Month | Rev% | OpEx% | Revenue | OpEx | NOI |
|---|---|---|---|---|---|
| 1 | 0% | 50% | $0 | $13,889 | −$13,889 |
| 2 | 13% | 56% | $8,681 | $15,625 | −$6,944 |
| 3 | 25% | 63% | $17,361 | $17,361 | $0 |
| 4 | 38% | 69% | $26,042 | $19,097 | $6,944 |
| 5 | 50% | 75% | $34,722 | $20,833 | $13,889 |
| 6 | 63% | 81% | $43,403 | $22,569 | $20,833 |
| 7 | 75% | 88% | $52,083 | $24,306 | $27,778 |
| 8 | 88% | 94% | $60,764 | $26,042 | $34,722 |
| 9 | 100% | 100% | $69,444 | $27,778 | $41,667 |

Total NOI over 9 months = $125,000. Monthly avg = $13,889 = **33.3%** of stabilized $41,667. ✓

**Impact.** Using 50% instead of 33.3% would overstate lease-up income by 17 percentage points × 9 months × $41,667/month ≈ $63k. That is cash the deal would not actually generate. By the time the model told you so, you'd be 9 months into lease-up with a shortfall.

**Code (`_LEASE_UP_INCOME_FACTOR` constant):**
```python
_LEASE_UP_INCOME_FACTOR = Decimal("1") / Decimal("3")
noi_monthly_est = noi_annual / Decimal("12") if noi_annual > ZERO else ZERO
lease_up_income_offset = _q(noi_monthly_est * _LEASE_UP_INCOME_FACTOR * Decimal(lease_up_months))
```

### 2.7 DSCR-capped mode

Some deals use a different sizing mode: size the loan to the **minimum DSCR** required by the lender, not to the gap. This is selected via `OperationalInputs.debt_sizing_mode = "dscr_capped"`.

**Logic:**
1. Compute the gap-fill principal `P_gap` using §2.4.
2. Compute the resulting DSCR at stabilization: `DSCR_gap = NOI / (P_gap × pmt_factor × 12)`.
3. If `DSCR_gap ≥ dscr_minimum`: use `P_gap` (the lender's minimum doesn't bind).
4. Otherwise: cap the principal so DSCR exactly equals the minimum:
   > `DS_target = NOI / DSCR_min / 12`
   > `P_capped = DS_target × PV_annuity_factor`
   > where `PV_annuity_factor = (1 − (1+i)^(-n)) / i`

This shows the user a **real funding gap** in the S&U table (Uses > Sources) rather than silently levering up past what the lender would actually fund.

### 2.8 Dual-constraint mode (MIN of LTV, DSCR, gap-fill)

Industry-standard loan sizing: the lender computes both LTV-based and DSCR-based maximums and funds the smaller. Selected via `debt_sizing_mode = "dual_constraint"`.

**Logic:**
1. Compute the gap-fill principal `P_gap` using §2.4 (with closing-cost divisor fold-in).
2. Compute LTV-based principal:
   > `property_value = NOI_annual / cap_rate`
   > `P_ltv = property_value × LTV%`

   The cap rate defaults to the going-in cap (`exit_cap_rate_pct`) but can be overridden via `source.refi_cap_rate_pct` on the CapitalModule.
3. Compute DSCR-based principal:
   > `DS_target = NOI_annual / DSCR_min / 12`
   > `P_dscr = DS_target × PV_annuity_factor`
4. Final principal: `P = MIN(P_gap, P_ltv, P_dscr)`
5. The `binding_constraint` is tagged on the source (`"ltv"`, `"dscr"`, or `"gap_fill"`) for UI transparency.

**Why three-way MIN?** `P_gap` acts as a ceiling: no point funding more than the project actually needs. `P_ltv` and `P_dscr` are lender constraints. The binding one determines what the lender will actually write.

### 2.9 Balloon balance tracking

Remaining loan balance at any point in time, handling IO-then-amortizing transitions:

```
if months_elapsed <= io_months:
    balance = principal                         # still in IO period
else:
    n_amort = months_elapsed − io_months
    factor = (1 + r)^n_amort
    balance = principal × factor − pmt × (factor − 1) / r
```

Where `pmt = _monthly_pmt(principal, rate, amort_years)` and `r = rate / 12`.

Used by: refi proceeds calculation (§2.10), prepay penalty at exit (§6.4).

### 2.10 Cash-out refinance (bridge → perm takeout)

**Exit Vehicle is the only input that defines when a loan ends.**

Each Capital Module's `exit_terms.vehicle` declares how its balance is resolved.  The previously user-editable `active_phase_end` field is deprecated — the engine derives the active-end rank from the vehicle at compute time via `_resolve_active_end_rank(module, all_modules)` (in [app/engines/cashflow.py](app/engines/cashflow.py)), with a matching helper `_resolve_waterfall_end_index` in [app/engines/waterfall.py](app/engines/waterfall.py).  The DB column still exists (transition-period rollback safety) but the POST handler writes a derived value on save.

| Vehicle value | Meaning | Refi event? | Derived end-rank |
|---|---|---|---|
| `"maturity"` | Balloon paid at amort term end | No | 99 (perpetuity through exit) |
| `"sale"` | Balloon paid from divestment proceeds | No (handled in exit period) | 6 (exit / divestment) |
| `<module_uuid>` | Another Capital Module absorbs the balance at the handoff point | **Yes** — §2.10 math below | Retirer's `active_phase_start` rank |

**Funder-type classification.** Exit Vehicle applies only to funder types that have a real ending (loans with maturity/refi/sale semantics):

`_EXIT_VEHICLE_APPLIES` = `{permanent_debt, senior_debt, mezzanine_debt, bridge, construction_loan, acquisition_loan, pre_development_loan, soft_loan, bond, owner_loan}`.

All other funder types (preferred_equity, common_equity, owner_investment, grant, tax_credit, other) are perpetuity-like — the waterfall distributes them at exit, and the draw schedule funds them as a single lump-sum draw at their `active_from` milestone.  `owner_loan` is promoted to full debt treatment (accrues interest, gets a debt-service line, uses Exit Vehicle).  The UI hides Exit Vehicle + draw cadence for non-exit-vehicle types.

The engine computes pairings in a generic pre-pass. For every module `B`, `_resolve_vehicle(B, all_modules)` reads `B.exit_terms.vehicle` and returns the literal or the retiring module.

**Explicit user picks are honoured regardless of overlap.** If `B.exit_terms.vehicle` is set to another module's UUID and that module exists, the engine uses it — even when the retirer's active window doesn't literally overlap `B.end_rank`. Adjacent-vs-overlapping distinctions are brittle (a new loan often closes the same day the old one matures), so the engine trusts the user's pick and lets the §2.10 refi math handle the handoff.

Default selection (when `vehicle` is unset or points at a missing module):

1. Among eligible retirers (modules whose active window `[start_rank, end_rank)` covers `B.end_rank`), prefer those where `R.start_rank == B.end_rank` (enter exactly at handoff). Tie-break by lowest `stack_position`, then alphabetical label.
2. Else if `B.end_rank >= 6` (exit/divestment): `"sale"`.
3. Else: `"maturity"`.

For each `(B, R)` pair the engine tags `B.source.is_bridge = True`, removes `B` from the gap-fill pool (so only the retirer sizes to TPC), and writes `R.source.construction_retirement = B.amount`. This generalises the legacy `debt_structure == "construction_and_perm"` specialisation — that path now flows through the generic detector and produces identical results.

**Refi cash flow.** When a perm loan has `construction_retirement` set on its source, the engine computes net refi proceeds at the first period of the perm's `active_phase_start`:

```
net_refi = perm_amount
         − bridge_balloon_balance
         − prepay_penalty
         − perm_financing_costs
```

**Components:**
- `bridge_balloon_balance`: computed via §2.9 at the takeover month
- `prepay_penalty`: `bridge_balloon × source.prepay_penalty_pct` (see §6.4)
- `perm_financing_costs`: sum of `_DEFAULT_LOAN_COSTS` for the perm funder type

**Cash flow injection:**
- Positive `net_refi` → "Refi — Net Proceeds to Equity" (inflow)
- Negative `net_refi` → "Refi — Equity Call (Shortfall)" (outflow)
- Bridge payoff, prepay penalty, and financing costs are each separate line items

**Perm sizing at stabilized NOI.** The perm's `dual_constraint` or `dscr_capped` sizing uses the engine's projected stabilized NOI (from income streams with escalation), not the going-in NOI. The cap rate for LTV defaults to the going-in cap but can be overridden via `source.refi_cap_rate_pct`. This is self-consistent: the only "invented" number is the deal's own NOI projection, which flows from the same income/expense assumptions used for every other metric.

---

## 3. Reserves

### 3.1 Operating Reserve

**Formula.**
```
if income_mode == "noi":
    operating_reserve = DS_monthly × R
else (revenue_opex mode):
    operating_reserve = max(OpEx_monthly, DS_monthly) × R
```

Where `R = operation_reserve_months` (default 6).

**Why `max(OpEx, DS)`?** At stabilization, two obligations compete for the reserve bucket: debt service and operating costs. They are both ongoing. The reserve must cover whichever is larger, because a project short on opex cash defaults on vendors and eventually on the lender anyway.

In NOI mode the user has input stabilized NOI directly, so OpEx is not broken out — we size on DS alone.

**How it's enforced.** The entire gap-fill debt solve (§2.4) is designed so that the cash balance at month 1 of stabilized = exactly the operating reserve. The cash flow loop then seeds `cumulative_cash_flow` to the reserve amount at that point (cashflow.py:189):

```python
if _is_stabilized and not _operating_reserve_seeded:
    cumulative_cash_flow = _op_reserve_amount
    _operating_reserve_seeded = True
```

**Plain English.** "Size the loan so that after all construction costs, lease-up carry, and IO payments, the project has exactly `reserve_months × max(OpEx, DS)` left in the bank at first stabilized month."

### 3.2 Lease-Up Reserve

**Formula.**
```
LeaseUpReserve = (P × f_m × L) − (1/3 × NOI_monthly × L)
               = (DS during lease-up) − (phantom income during lease-up)
```

This is the **net debt-service shortfall** during lease-up that the permanent loan cannot cover from income alone.

**Why is it a separate Use line?** Because it is part of what the perm loan must cover, and if we didn't surface it, Sources would not equal Uses. The gap-fill formula produces this exact number as a by-product (`_lu = principal × pmt_factor × L − lease_up_income_offset`) and we write it to the `Lease-Up Reserve` Use line so the S&U balances.

**Plain English.** "How much does the lender need to advance beyond TPC so the project can make its debt payments during the months where income is ramping and can't cover them?"

---

## 4. Revenue / NOI

### 4.1 Two income modes

`Scenario.income_mode` selects between:
- **`revenue_opex`** (default): sum `IncomeStream` rows minus `OperatingExpenseLine` rows → NOI
- **`noi`**: user enters stabilized NOI directly via `OperationalInputs.noi_stabilized_input`; engine applies an annual escalation factor

Both produce the same downstream math (DSCR, reserves, gap-fill). The difference is where NOI comes from.

### 4.2 Income streams (revenue_opex mode)

**Schema (deal.py:372):**
```python
class IncomeStream:
    unit_count: int | None
    amount_per_unit_monthly: Decimal | None
    amount_fixed_monthly: Decimal | None
    stabilized_occupancy_pct: Decimal      # default 95
    bad_debt_pct: Decimal                  # default 0 — % of GPR lost to bad debt
    concessions_pct: Decimal               # default 0 — % of GPR lost to concessions
    renovation_absorption_rate: Decimal | None  # if set, ramps premium 0→100% over reno+lease-up
    escalation_rate_pct_annual: Decimal    # default 0
    active_in_phases: list[str]            # e.g. ["lease_up", "stabilized"]
```

**Base amount per month:**
```
if amount_fixed_monthly is set:
    base = amount_fixed_monthly
else:
    base = amount_per_unit_monthly × unit_count
```

**Per-period computation:**
```
escalated = base × (1 + escalation_rate)^(period/12)

# Renovation absorption: if renovation_absorption_rate is set, ramp
# the premium linearly from 0→100% over reno + lease-up months
if renovation_absorption_rate > 0 and phase is reno/construction/lease-up:
    absorption = min(period + 1, reno_months + leaseup_months) / (reno_months + leaseup_months)
    escalated = escalated × absorption

after_vacancy = escalated × occupancy_pct_this_phase
vacancy = escalated − after_vacancy
bad_debt = escalated × bad_debt_pct
concessions = escalated × concessions_pct
net_income = after_vacancy − bad_debt − concessions
```

Summed across all active streams → gross_revenue, vacancy_loss, EGI.

**Bad debt and concessions** are separate percentage deductions from GPR, distinct from vacancy. Default to 0% (backward-compatible). These match the industry-standard CRE pro forma structure where vacancy, bad debt, and concessions are separate line items between GPR and EGI.

**Why `(1 + rate)^(period/12)`?** This is continuous annual escalation — `rate = 3%` compounds monthly at `(1.03)^(1/12) − 1 ≈ 0.247%`. At month 24 (two years in), the factor is `1.03^2 = 1.0609` exactly.

### 4.3 Occupancy ramp (lease-up)

**Formula:**
```
step = (stabilized_occ − initial_occ) / (months − 1)
occupancy_month_i = clamp(initial_occ + step × i, 0, stabilized_occ)
```

Where `initial_occ` defaults to 50% and `stabilized_occ` defaults to 95% (configurable per stream / per deal).

**Why 50% initial?** This is the `OperationalInputs.initial_occupancy_pct` field. In new construction it might be 0%; in acquisition-with-repositioning it might be 60% (existing tenants retained). The default of 50% is a reasonable lease-up scenario that users will commonly overwrite.

**S-curve option.** When `OperationalInputs.lease_up_curve = "s_curve"`, the ramp uses a logistic function instead of linear:

```
t_norm = month_index / (months - 1)           # 0.0 → 1.0
raw = 1 / (1 + e^(-k × (t_norm - 0.5)))       # logistic sigmoid
normalized = (raw - sigmoid(-k/2)) / (sigmoid(k/2) - sigmoid(-k/2))
occupancy = initial_occ + (stabilized_occ - initial_occ) × normalized
```

Where `k` = `lease_up_curve_steepness` (default 5; range 1=flat to 10=steep). At k=5 this produces the classic slow-start → rapid-middle → slow-finish absorption pattern observed in real lease-ups. The normalization ensures occ(0) = initial and occ(N) = stabilized exactly.

**When to use S-curve.** Large new-construction or major-reno projects where absorption follows a marketing-driven pattern. Keep linear (default) for smaller value-add deals where units turn one at a time.

### 4.4 Occupancy in hold / renovation phases

**Hold phase:** `stabilized_occ × (1 − hold_vacancy_rate_pct)` — user-specified vacancy during the hold period (e.g., while planning renovations).

**Renovation phase:** `stabilized_occ × (1 − income_reduction_pct_during_reno)` — user-specified income hit during renovations.

### 4.5 Renovation absorption rate (value-add premium phase-in)

When `renovation_absorption_rate` is set on an income stream, the stream's escalated amount is scaled by an absorption fraction that ramps linearly from 0 to 1 over the combined renovation + lease-up timeline:

```
total_abs_months = renovation_months + lease_up_months
absorption_frac = min(current_period + 1, total_abs_months) / total_abs_months
escalated_amount = escalated_amount × absorption_frac
```

**Why this matters for value-add deals.** In a 200-unit renovation where you're adding a $200/mo premium, not all units come online at once. Without absorption, the pro forma shows full premium from day one — overstating Year 1-2 revenue, which directly affects:
- Leveraged IRR (very sensitive to early-period cash flows)
- DSCR during the ramp period (could show false covenant breach)
- Draw schedule sizing (lower early cash flow = more reserves needed)

**When to use.** Set `renovation_absorption_rate = 1.0` on premium-driven income streams for value-add deals. Leave it `NULL` (default) for acquisition deals where income is already stabilized.

**Discrete capture schedule (engine only — not exposed in UI).** The engine supports `renovation_capture_schedule` as a JSON array of `{year, capture_pct}` entries for PropRise-style discrete steps. However, the UI exposes only the continuous ramp (`renovation_absorption_rate`). The discrete schedule is available for API/import use but is not a primary modeling path. Continuous ramp is simpler to configure and produces smoother cash flows.

### 4.7 LTL Catchup Escalation

When an income stream has `catchup_target_rent` set, the engine applies accelerated escalation capped at `LTL_CATCHUP_CAP_PCT` (hardcoded 10%) per year until the target is reached, then reverts to normal `escalation_rate_pct_annual`.

**Formula (per year):**
```
if current_rent < catchup_target_rent:
    increase = min(target - current, current × 0.10)
    current = current + increase
else:
    current = current × (1 + normal_escalation_rate)
```

**Example** ($1,200 in-place → $1,500 market, 10% cap, 3% normal):
```
Year 0: $1,200 (in-place)
Year 1: $1,200 + min($300, $120) = $1,320  (10% cap binds)
Year 2: $1,320 + min($180, $132) = $1,452  (10% cap binds)
Year 3: $1,452 + min($48, $145)  = $1,500  (gap closed, full amount < cap)
Year 4: $1,500 × 1.03            = $1,545  (normal escalation resumes)
```

**Partial-year interpolation.** Within a year, the catchup increase is pro-rated by month: `increase × (month_in_year / 12)`. This preserves monthly granularity.

**Why 10% cap?** A 10% annual rent increase is at the upper end of what the Portland multifamily market can absorb without mass turnover. Higher increases (15-20%) are theoretically possible but cause vacancy spikes that offset the revenue gain. The cap is a global constant (`LTL_CATCHUP_CAP_PCT`) — not user-configurable — to enforce realistic modeling.

**Relationship to renovation absorption.** LTL catchup and renovation absorption are independent and apply to different unit pools:
- **LTL catchup** applies to units NOT being renovated — closing the gap between in-place and market rent through lease renewals
- **Renovation absorption** applies to units being renovated — phasing in the post-renovation premium as units are turned

For units in the value-add pool, renovation supersedes LTL: the unit goes directly from `in_place_rent` to `post_reno_rent`. The LTL gap ($300 in the example) is captured implicitly because `post_reno_rent` ($1,800) already exceeds `market_rent` ($1,500).

### 4.8 Unit Strategy Assignment (UnitMix)

Each unit type in `UnitMix` can be assigned one of three strategies via `unit_strategy`:

| Strategy | Driving Fields | Rent Trajectory |
|---|---|---|
| `base_escalation` | `in_place_rent_per_unit` | `in_place` → normal annual escalation |
| `ltl_catchup` | `in_place_rent_per_unit`, `market_rent_per_unit` | `in_place` → accelerated (cap 10%/yr) to `market_rent` → normal |
| `value_add_renovation` | `post_reno_rent_per_unit`, `renovation_absorption_rate` | `in_place` → renovation → `post_reno_rent` → normal |

**UnitMix schema fields (April 18 2026):**

| Field | Type | Notes |
|---|---|---|
| `label` | str | Display label (e.g., "1BR/1BA") |
| `unit_count` | int | Number of units of this type |
| `avg_sqft` | Numeric(18,2) | Average square footage |
| `beds` | Numeric(4,1) | Bedrooms: 0, 1, 2, 3, 4, 5+ (5 represents "5 or more") |
| `baths` | Numeric(4,1) | Baths in 0.5 increments: 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5+ |
| `in_place_rent_per_unit` | Numeric(18,2) | Current tenant rent (loss-to-lease anchor) |
| `market_rent_per_unit` | Numeric(18,2) | Market rent (LTL target + property value basis) |
| `post_reno_rent_per_unit` | Numeric(18,2) | Post-renovation rent (value-add strategy only) |
| `unit_strategy` | str | `base_escalation` / `ltl_catchup` / `value_add_renovation` |

**Removed April 18 2026**: `avg_monthly_rent` (legacy). It duplicated `in_place_rent_per_unit` semantically and created ambiguity. Migration 0046 drops the column. Bed/bath were added as numeric variables so comp-data ingestion (HelloData, etc.) can populate them directly.

**Apply to Revenue** (endpoint: `POST /ui/models/{id}/unit-mix/apply-to-revenue`) auto-generates IncomeStream rows per unit type:
- `ltl_catchup` units → stream with `catchup_target_rent = market_rent_per_unit`, base = `in_place_rent_per_unit`
- `value_add_renovation` units → stream labeled `"{unit} Rent (Renovated)"` with `renovation_absorption_rate = 1.0`, base = `post_reno_rent_per_unit or market_rent_per_unit or in_place_rent_per_unit`
- `base_escalation` units → stream with standard escalation only, base = `in_place_rent_per_unit or market_rent_per_unit`

Idempotent — re-running replaces matching-labeled streams, preserves one-off streams (parking, laundry, etc.). Only available in `revenue_opex` mode; hidden in `noi` mode.

### 4.6 NOI-mode direct input

```python
_noi_annual = _to_decimal(inputs.noi_stabilized_input)
_esc_period = max(0, period - first_stab_period)  # anchored at first stabilized month
_esc_factor = _growth_factor(inputs.noi_escalation_rate_pct or Decimal("3"), _esc_period)
_noi_monthly = _q(_noi_annual / Decimal("12") * _esc_factor)
```

Applied month-by-month in stabilized/lease-up/exit phases. Construction phases see `_noi_monthly = 0`.

**Escalation anchor (important — April 18 2026).** Escalation is anchored at `first_stab_period` (the month index of the first stabilized period), **not** at deal month 0. Semantics: the user-entered `noi_stabilized_input` is the NOI at **year 1 of stabilization**, the underwriting convention. Previously the engine applied escalation from deal month 0, so a 22-month construction/lease-up timeline lifted the displayed first-stabilized-month NOI above the raw input by `(1+rate)^(22/12)`. This caused DSCR in `dscr_capped` / `dual_constraint` sizing to drift above the minimum (e.g. 1.1557 instead of 1.15) because sizing used the raw input but display used the escalated value.

With the anchor fix:
- First stabilized month: `esc_period = 0` → `esc_factor = 1.0` → NOI = raw input
- Year 2 of stabilization: `esc_period = 12` → `esc_factor = (1+rate)^1`
- Lease-up months (if any, period < first_stab_period): clamped to 0 via `max(0, ...)` → factor = 1.0 (simplification — lease-up NOI isn't modeled separately in NOI mode)

The `first_stab_period` is computed once in the main compute loop from the phase plan and passed into `_compute_period`.

### 4.7 Fix-point iteration for DSCR convergence

When `debt_sizing_mode` is `dscr_capped` or `dual_constraint`, the **first** sizing pass within a compute can only use an **estimated** stabilized NOI (from `_estimate_stabilized_noi_monthly`) or a `prev_noi_stabilized` from a prior compute. The estimator misses escalation carry-in and capex reserve deductions; `prev_noi_stabilized` is stale if inputs changed. Either way, the NOI used for sizing may differ from the NOI the compute ultimately produces, causing DSCR to drift above the target minimum.

The `POST /api/models/{id}/compute` endpoint wraps `compute_cash_flows` in a fix-point loop:

```python
MAX_ITERATIONS = 5
DSCR_CONVERGENCE_TOLERANCE = Decimal("0.005")
for _iter in range(MAX_ITERATIONS):
    result = await compute_cash_flows(...)
    if sizing_mode not in {"dscr_capped", "dual_constraint"}:
        break
    cur_dscr = result.get("dscr")
    if prev_dscr is not None and abs(cur_dscr - prev_dscr) < TOLERANCE:
        break
    prev_dscr = cur_dscr
```

Each iteration reads the **previous** `OperationalOutputs.noi_stabilized` (via the code at line 116 of `cashflow.py`) and passes it to `_auto_size_debt_modules` as `prev_noi_stabilized`. Iteration N+1 sizes using iteration N's actual computed NOI, so by iteration 2–3 the sized debt service matches the final NOI and DSCR converges.

- **Convergence tolerance**: 0.005× (half a basis point of DSCR).
- **Iteration cap**: 5. If math doesn't converge (shouldn't happen — NOI is debt-independent so convergence is in 2 passes), the 5th iteration's result is returned as-is.
- **Performance**: typical deals run in 2 iterations (~600ms–1s total). Cap of 5 bounds worst case at ~3s.
- **Observability**: `result["sizing_iterations"]` surfaces the count used (exposed to logs and the frontend).

Note: `gap_fill` mode doesn't iterate — only sizes once.

---

## 5. Operating Expenses

### 5.1 Stabilized OpEx (pre-compute)

Before the cash flow loop runs, we sum up stabilized OpEx to use in reserve sizing:

```python
opex_monthly_pre = ZERO
for line in expense_lines:
    active = {str(phase) for phase in (line.active_in_phases or [])}
    if "stabilized" in active:
        opex_monthly_pre += _q(_to_decimal(line.annual_amount) / Decimal("12"))
```

This feeds the `max(OpEx, DS)` computation in the operating reserve (§3.1).

### 5.2 Per-period OpEx

Each month in the cash flow loop, for each expense line active in the current phase:

```
line_growth = (1 + escalation_rate)^(period/12)
line_base = (annual_amount / 12) × line_growth

if phase is lease_up and line.scale_with_lease_up:
    lease_up_scale = clamp(occupancy_ramp_this_month, floor_pct, 1.0)
    line_amount = line_base × lease_up_scale
else:
    line_amount = line_base
```

**Why `scale_with_lease_up` and `lease_up_floor_pct`?** Some expense lines (utilities, trash, leasing commissions) scale directly with occupancy — `scale_with_lease_up = True`, `lease_up_floor_pct = 0`. Others (property taxes, insurance, base salaries) are fixed — `scale_with_lease_up = False`, they stay at 100% regardless. Some are in between (maintenance at 50% minimum even when empty) — `scale_with_lease_up = True, lease_up_floor_pct = 0.5`.

The default when creating a new expense line is `scale_with_lease_up = False` (conservative: costs show at full during lease-up). Users opt in to lease-up scaling.

### 5.3 CapEx Reserve

```python
capex_reserve = (
    _q((_to_decimal(inputs.capex_reserve_per_unit_annual) * units / Decimal("12")) * expense_growth)
    if phase.period_type in {lease_up, stabilized, exit}
    else ZERO
)
```

**Plain English.** Per-unit annual CapEx reserve × unit count / 12, escalated by the expense growth rate, applied in operational phases only. This is a below-the-NOI-line deduction that reduces distributable cash but does not hit the P&L NOI figure.

**Why below-NOI and not an OpEx line?** CapEx reserves are a cash deduction, not an accounting expense. The distinction matters for DSCR (calculated on NOI, which excludes CapEx) vs. cash-on-cash returns (calculated on distributable cash, which includes CapEx).

---

## 6. Period Cash Flow (`_compute_period`)

Each month of the project runs through this calculation:

```
1. Gross Revenue        = Σ escalated_stream_amounts
2. Vacancy Loss         = Σ (escalated − net_income) per stream
3. EGI                  = Gross Revenue − Vacancy Loss
4. OpEx                 = property_tax + insurance + opex_per_unit + Σ itemized_lines + mgmt_fee + carrying_cost
5. CapEx Reserve        = capex_per_unit × units × growth / 12  (operational phases only)
6. NOI                  = EGI − OpEx − CapEx Reserve
7. Debt Service         = construction_debt_monthly or operation_debt_monthly (by phase)
8. Capital Outflows     = Σ use_line_amounts active this month
9. Capital Inflows      = exit-phase inflows (sale proceeds)
10. Net Cash Flow       = NOI − DS − Capital Outflows + Capital Inflows
```

### 6.1 UseLine timing: `first_day` vs `spread`

```python
if ul_timing == "spread":
    monthly_amount = total_amount / phase.months
    # last month picks up the rounding remainder
    if month_index == phase.months - 1:
        monthly_amount = total_amount - (monthly_amount × (phase.months − 1))
else:  # first_day
    if month_index != 0: continue
    amount = total_amount
```

**Plain English.** `first_day` drops the full amount on month 1 of its phase (used for closing costs, deposits, lump-sum payments). `spread` divides the amount evenly across all months of the phase (used for hard construction costs, ongoing soft costs).

### 6.2 Construction vs operation debt service

```python
debt_service = (
    construction_debt_monthly
    if phase.period_type in _CONSTRUCTION_PERIOD_TYPES
    else operation_debt_monthly
)
```

Where `_CONSTRUCTION_PERIOD_TYPES = {acquisition, hold, pre_construction, construction, minor_renovation, major_renovation, conversion}`.

This lets a single loan charge IO during construction and P&I during operations (the `io_then_pi` carry pattern). The two monthly figures are computed once at sizing time from the carry config.

### 6.3 Cash balance seeding invariant

```python
cumulative_cash_flow = total_sources  # period 0

for each period:
    ncf = compute_period(...)
    if is_stabilized and not seeded:
        cumulative_cash_flow = operating_reserve_amount   # reset
        seeded = True
    elif seeded:
        if ncf < 0:
            cumulative_cash_flow += ncf   # drain only on negative NCF
    else:
        cumulative_cash_flow += ncf       # pre-seed: accumulate everything
```

**What this enforces.** Pre-stabilization, the cash balance carries the running net of sources and uses — it can go negative, triggering equity calls in the waterfall. At first stabilized month, it resets to exactly the operating reserve (the gap-fill math guarantees this). Post-stabilization, positive NCF is distributable (not banked) and negative NCF drains the reserve.

**Why not carry forward post-stabilization NCF?** Because positive post-stabilized NCF goes out to investors through the waterfall. If we also added it to the cash balance, we'd be double-counting.

### 6.4 Prepay penalty at exit

At exit (sale), any debt module with `source.prepay_penalty_pct > 0` incurs a prepay penalty computed on the remaining balloon balance:

```
balloon = _balloon_balance(principal, rate, amort_years, total_hold_months, io_months)
prepay_cost = balloon × prepay_penalty_pct / 100
```

This is injected as a capital event line item ("Prepay Penalty — {label}") in the exit period, reducing net cash flow. Bridge modules (`is_bridge = True`) are excluded — their prepay is handled at refi (§2.10).

### 6.5 Refi capital events

When a bridge→perm takeout is detected (§2.10), the following line items are injected at the first month of the perm's active phase:

| Line Item | Direction | Amount |
|---|---|---|
| Refi — Bridge Payoff | outflow | bridge balloon balance |
| Refi — Prepay Penalty | outflow | bridge balloon × prepay_pct (if > 0) |
| Refi — Financing Costs | outflow | perm closing costs |
| Refi — Net Proceeds to Equity | inflow | surplus (if positive) |
| Refi — Equity Call (Shortfall) | outflow | deficit (if negative) |

---

## 7. Waterfall & Profit Metrics

**Waterfall style: American.** Distributions are computed period-by-period (cash distributed as earned, not held until exit). This is the industry standard for US multifamily syndications and JV structures.

### 7.1 Module stack and tiers

**Capital modules** (`CapitalModule`) define the stack: debt and equity lines with a `stack_position` (0 = senior, higher = junior) and a `funder_type` (`permanent_debt`, `construction_loan`, `common_equity`, etc.).

**Waterfall tiers** (`WaterfallTier`) define the distribution order. Each tier has:
- `priority`: execution order (1 = first)
- `tier_type`: one of `debt_service`, `pref_return`, `return_of_equity`, `catch_up`, `irr_hurdle_split`, `deferred_developer_fee`, `residual`
- `lp_split_pct`, `gp_split_pct`: split ratios (for splittable tiers)
- `irr_hurdle_pct`: hurdle rate (for `irr_hurdle_split`)
- `capital_module_id`: optional link to a specific module

### 7.2 Asset management fee (pre-distribution deduction)

When `OperationalInputs.asset_mgmt_fee_pct` is set (> 0), the AM fee is deducted from positive net cash flow **before** it enters the waterfall tier distribution:

```
if available_cash > 0 and am_fee_pct > 0:
    am_fee = available_cash × am_fee_pct / 100
    available_cash = available_cash − am_fee
```

**Why pre-distribution?** The AM fee compensates the asset manager (typically the GP/sponsor's management entity) for ongoing oversight. It's an operational cost of the partnership, not a profit split. Deducting it before the waterfall ensures it's senior to all investor distributions — consistent with how AM fees work in real fund structures.

### 7.3 Capital calls (pre-distribution)

When `net_cash_flow < 0` in any period, the waterfall allocates capital calls in stack-position order:

```python
if net_cash < ZERO:
    capital_calls = _allocate_capital_calls(-net_cash, phase_name, module_states)
    for module_id, amount in capital_calls.items():
        if _is_gp_equity_module(state.module):
            _append_period_cashflow(gp_cashflows, cash_flow.period, -amount)
        elif _is_equity_module(state.module):
            _append_period_cashflows(lp_cashflows, cash_flow.period, -amount)
```

**Plain English.** Negative periods (usually construction/lease-up) are funded first by drawing debt up to commitments, then by calling equity from the lowest-priority capital (GP first if `_is_gp_equity_module`, then LP).

### 7.3 Distribution tiers (positive cash flow)

In each period with positive cash, the engine iterates through waterfall tiers in priority order, allocating until cash is exhausted.

#### Tier: `debt_service`
Pays accrued interest first, then principal at exit:
```
due = accrued_interest_due + (outstanding_principal if exit and full_payoff else 0)
amount = min(remaining_cash, due)
```

#### Tier: `pref_return`
Pays accrued preferred return on equity modules up to the cap:
```
amount = min(remaining_cash, accrued_pref_due)
```
Pref typically accrues at a fixed annual rate on outstanding contributed capital.

#### Tier: `return_of_equity`
Returns original contributions before any profit split:
```
amount = min(remaining_cash, outstanding_principal)
```

#### Tier: `catch_up`
Allows GP to "catch up" to its target share after LP pref has been paid:
```
gp_target = (gp_split / (1 − gp_split)) × total_LP_distributions_to_date
gp_shortfall = max(gp_target − total_GP_distributions_to_date, 0)
gp_amount = min(available_cash, gp_shortfall)
lp_amount = available_cash − gp_amount
```

**Plain English.** If the split is 80/20 LP/GP and LP has received $80k pref while GP has received nothing, GP's target is `(20/80) × 80k = $20k`. Catch-up tier sends up to $20k to GP before the normal split resumes.

#### Tier: `irr_hurdle_split`
LP gets everything until its IRR reaches the hurdle; above the hurdle, cash splits by tier ratios:
```
lp_irr = compute_xirr(lp_cashflows)
if lp_irr < hurdle_pct:
    all_to_lp
else:
    lp_amount = cash × lp_split
    gp_amount = cash × gp_split
```

**Why use XIRR (not IRR)?** Because our periods are monthly but distributions can happen at any period. XIRR handles irregular-date cash flows; IRR assumes equal periods.

#### Tier: `residual`
Whatever remains after all earlier tiers — split by tier ratios. This is "the promote above the final hurdle".

### 7.4 Profit metrics

#### LP IRR, GP IRR (via XIRR)

```python
def _compute_xirr_fraction(period_cashflows: dict[int, Decimal]) -> Decimal | None:
    ordered = sorted(period_cashflows.items())
    values = [float(amount) for _, amount in ordered if amount != 0]
    dates = [_period_to_date(period) for period, amount in ordered if amount != 0]
    return pyxirr.xirr(dates, values)
```

**Period → date mapping:**
```python
def _period_to_date(period: int) -> date:
    year = 2020 + (period // 12)    # DEFAULT_IRR_BASE_YEAR
    month = (period % 12) + 1
    return date(year, month, 1)
```

**Formula.** IRR solves for the rate `r` such that:
> `Σ (CF_i / (1+r)^((t_i − t_0) / 365)) = 0`

Where `CF_i` are individual cash flows (negative = contribution, positive = distribution) and `t_i` are the month-1 dates of each period.

**Why 2020 as base year?** It's arbitrary — XIRR only cares about the date differences between flows, not their absolute values. 2020 is a round number inside the pyxirr-supported range.

#### Equity Multiple (MOIC)

```python
equity_multiple = (total_LP_positive + total_GP_positive) / (total_LP_contributed + total_GP_contributed)
```

**Plain English.** Total dollars out divided by total dollars in, across LP and GP combined. A value of 2.0× means investors doubled their money.

**Why combined LP + GP?** This is the **project-level** equity multiple. Separate LP and GP multiples are also computed but are not the headline metric.

#### Cash-on-Cash Year 1

```python
year_one_distributions = Σ positive cash flows (LP + GP) in periods 0–11
total_contributed = Σ all capital calls (LP + GP)
cash_on_cash_year_1_pct = (year_one_distributions / total_contributed) × 100
```

**Plain English.** "If I put in $1M, how much cash did I receive in year 1 as a percentage of what I put in?" — a standard first-year yield metric that's easy to explain to investors.

**Why "periods 0–11" and not "the year after stabilization"?** By convention, "year 1" means the first 12 months from deal close. If the deal is still in construction during year 1, cash-on-cash will be 0% or negative. That is the correct, honest number — the user should interpret it in context.

#### Debt Yield

```
debt_yield_pct = (NOI_stabilized / total_outstanding_debt_balance) × 100
```

Where `total_outstanding_debt_balance` sums all non-bridge debt module amounts (bridge modules with `is_bridge = True` are excluded to avoid double-counting with the perm that takes them out).

**Why lenders care.** Debt yield is a coverage metric independent of interest rate and amortization. A 10% debt yield means NOI covers 10% of the loan balance annually — the lender can recover their principal in ~10 years of NOI alone. Most institutional lenders require 8-10% minimum.

#### Loss-to-Lease

Tracked on `UnitMix` rows via `market_rent_per_unit` and `in_place_rent_per_unit`:

```
loss_to_lease_pct = (market_rent - in_place_rent) / market_rent × 100
```

A positive LTL indicates below-market rents — the primary value-add opportunity in multifamily acquisitions. Three of five benchmark CRE models (A.CRE Acquisition, PropRise, A Simple Model) track LTL as a first-class metric. Exported in the JSON payload via `unit_mix` and available for investor-facing reports.

### 7.5 Debt service in the waterfall (true DS, not placeholder)

The cashflow engine produces an estimate of debt service using simple IO/P&I formulas. The waterfall engine then **recomputes** levered cash flows using the actual distributions from `debt_service` tiers in the waterfall:

```python
debt_service_rows = select(WaterfallResult where tier_type = 'debt_service')
debt_service_by_period = aggregate by period

for cash_flow in cash_flows:
    waterfall_ds = debt_service_by_period.get(period, ZERO)
    debt_service = waterfall_ds if waterfall_ds > ZERO else prior_debt_service
    cash_flow.net_cash_flow = NOI − debt_service + adjustments
```

**Why this two-step dance?** Because the waterfall can enforce constraints the cashflow engine cannot: DSCR cutoffs, priority-of-payment rules, deferred-interest accruals, actual timing of lender payments. The cashflow engine gives us a closed-form sizing; the waterfall produces the **authoritative** levered cash flows that feed IRR.

### 7.6 Levered vs unlevered project IRR

- **Unlevered project IRR**: `XIRR(TPC outflows, NOI inflows, exit proceeds)` — returns as if the deal were 100% equity. Measures asset quality.
- **Levered project IRR**: `XIRR(equity contributions, post-DS distributions, post-payoff residual)` — returns to the equity stack. Measures the deal's return after leverage.

The spread between the two is the "leverage amplification" — positive if leverage is accretive, negative if the deal is over-levered.

### 7.7 Calculation Status diagnostic (3-factor model)

The Calculation Status pill in the builder topbar surfaces the health of the model via three factors. Any factor in `warn` or `fail` state marks the overall as `warn` (yellow); all `ok`/`na` = `ok` (green).

**Factor 1: Sources = Uses**
```
gap = capital_total − uses_total
```
- `|gap| < $1` → `ok` "Sources = Uses"
- `gap > 0` → `warn` "Surplus $X" (extra capital not needed)
- `gap < 0` → `fail` "Gap $X" (Uses exceed Sources)

**Factor 2: DSCR**
```
dscr = noi_stabilized / (operation_debt_monthly × 12)
```
- `dscr ≥ dscr_minimum` → `ok` with headroom amount
- `dscr < dscr_minimum` → `fail` with shortfall amount

**Factor 3: LTV**
```
property_value = noi_stabilized / (exit_cap_rate_pct / 100)
actual_ltv_pct = total_non_bridge_debt / property_value × 100
```
- Computed regardless of sizing mode (always shown as informational)
- When `debt_sizing_mode == "dual_constraint"`: green/red status based on binding constraint (red if LTV binds AND gap exists)
- When any other sizing mode: grey `na` status with the computed LTV %

**Pill label (center-top of builder):**
- All `ok`: "✓ Calculation Valid"
- Single failing factor: specific label (e.g., "⚠ -$478,284 Sources Gap", "⚠ 1.14× DSCR — Too Low", "⚠ 72.3% LTV — Too High")
- Multiple failures: "⚠ N issues"

Click opens a modal with per-factor details, current/target values, and actionable explanation text.

**Endpoints:**
- `GET /ui/models/{id}/calc-status` — pill HTML
- `GET /ui/models/{id}/calc-status/modal` — modal body HTML

The pill replaces the legacy sidebar "Sources = Uses" banner (removed April 18 2026).

---

## 8. Key constants and defaults (quick reference)

| Constant | Value | Where it lives | What it controls |
|---|---|---|---|
| `MONEY_PLACES` | `Decimal("0.000001")` | cashflow.py | 6-decimal rounding for all cash math |
| `DEFAULT_IRR_BASE_YEAR` | `2020` | waterfall.py | Period → date conversion origin for XIRR |
| `PLACEHOLDER_DSCR` | `Decimal("1.25")` | cashflow.py | Fallback if `dscr_minimum` not set |
| `_LEASE_UP_INCOME_FACTOR` | `1/3` | cashflow.py | Phantom CF avg income during lease-up |
| `operation_reserve_months` | `6` (default) | OperationalInputs | Reserve horizon for gap-fill sizing |
| `initial_occupancy_pct` | `50` (default) | OperationalInputs | Starting point of lease-up ramp |
| `stabilized_occupancy_pct` | `95` (default) | IncomeStream | Ending point of lease-up ramp |
| `expense_growth_rate_pct_annual` | `3` (default) | OperationalInputs | Annual OpEx escalation |
| `noi_escalation_rate_pct` | `3` (default) | OperationalInputs | NOI-mode escalation |
| `bad_debt_pct` | `0` (default) | IncomeStream | % of GPR lost to bad debt |
| `concessions_pct` | `0` (default) | IncomeStream | % of GPR lost to concessions |
| `renovation_absorption_rate` | `NULL` (default) | IncomeStream | Ramp fraction for reno premium phase-in |
| `prepay_penalty_pct` | `NULL` (default) | CapitalSourceSchema (JSONB) | % of balloon balance at payoff |
| `refi_cap_rate_pct` | `NULL` (default) | CapitalSourceSchema (JSONB) | Cap rate override for refi LTV sizing |
| `asset_mgmt_fee_pct` | `NULL` (default) | OperationalInputs | AM fee deducted pre-waterfall |
| `debt_yield_pct` | computed | OperationalOutputs | NOI / total debt balance × 100 |
| `sensitivity_matrix` | computed (JSON) | OperationalOutputs | 5×5 grid storage for investor export |
| `lease_up_curve` | `NULL` → "linear" | OperationalInputs | "linear" or "s_curve" ramp shape |
| `lease_up_curve_steepness` | `NULL` → 5 | OperationalInputs | S-curve steepness (1=flat, 10=steep) |
| `market_rent_per_unit` | `NULL` | UnitMix | Market rent for loss-to-lease calculation |
| `in_place_rent_per_unit` | `NULL` | UnitMix | Current lease rent for LTL |
| `renovation_capture_schedule` | `NULL` | IncomeStream | Discrete year-by-year capture rates (JSON, engine only) |
| `catchup_target_rent` | `NULL` | IncomeStream | Market rent target for LTL catchup escalation |
| `LTL_CATCHUP_CAP_PCT` | `10` | cashflow.py constant | Max annual rent increase % during LTL catchup |
| `unit_strategy` | `NULL` | UnitMix | "base_escalation", "ltl_catchup", or "value_add_renovation" |
| `post_reno_rent_per_unit` | `NULL` | UnitMix | Monthly rent after renovation (value-add strategy) |
| `beds` | `NULL` | UnitMix | Bedrooms (0–5+, whole numbers) |
| `baths` | `NULL` | UnitMix | Baths (0–3.5+, 0.5 increments) |
| `MAX_ITERATIONS` | `5` | models.py compute endpoint | Fix-point iteration cap for DSCR convergence |
| `DSCR_CONVERGENCE_TOLERANCE` | `0.005` | models.py compute endpoint | DSCR stability threshold between iterations (half a bp) |
| `first_stab_period` | computed | compute_cash_flows loop | Month index of first stabilized phase; anchor for NOI-mode escalation |

---

## 9. Why we made the choices we made — summary

1. **Exact avg-draw formula (`rate/12 × (N+1)/2`) over industry 50% heuristic** for Interest Reserve sizing. We model monthly draws, so we can compute the exact factor rather than the large-N limit. On short construction timelines this matters.

2. **Four distinct carry types** (True IO, Interest Reserve, Capitalized Interest, P&I) instead of three or two. Phase 1 rewrite split True IO from Interest Reserve because they produce different principals for the same base cost. Matches Argus / REFM / FDIC handbook conventions.

3. **`max(OpEx, DS)` for operating reserve** in revenue_opex mode. Both obligations are ongoing; the reserve must cover the larger one. NOI mode sizes on DS only because OpEx isn't broken out.

4. **`1/3` lease-up income factor** (not `1/2`). The derivation in §2.6 shows that linear revenue ramps combined with sticky fixed costs produce a 33.3% average, not 50%. The difference is material (~$63k on a 9-month lease-up at $500k NOI).

5. **Closing costs folded into perm divisor** (not iterated). `P × (1 − 0.5%) = TPC → P = TPC / 0.995` is exact in one pass. Iterative convergence would work but is fragile and ugly.

6. **Closing costs excluded from bridge loan sizing via `_cc_labels`**. A construction loan should not cover its own origination fee — the fee lives in `pre_construction`, the same phase that sizes the pre-dev loan. Without the exclusion, pre-dev loan would double-count. Perm gap-fill covers all closing costs.

7. **Waterfall re-derives debt service** from `debt_service` tier allocations rather than reusing the cashflow-engine placeholder. This preserves accrual logic, DSCR cutoffs, and priority-of-payment rules that the cashflow engine cannot enforce alone.

8. **Cumulative cash flow resets to operating reserve at first stabilized month**. This is the invariant the entire gap-fill formula is designed to satisfy. Without it, you couldn't prove that Sources = Uses after the cash flow loop runs. With it, the reserve is guaranteed to exist at stabilization regardless of what happens in lease-up.

9. **6-decimal Decimal precision throughout**. Eliminates rounding drift across 60+ periods of compounding math. Sources = Uses must balance to the penny, not "close enough".

10. **Always-recompute vs user-override sentinels**. Operating Reserve, Capitalized Interest, Lease-Up Reserve are always recomputed from current debt (pure derivation). Closing costs respect `amount > 0` as a user override (allows real deal terms to override market defaults). This split matches how users actually think about these numbers.

11. **MIN(LTV, DSCR, gap-fill) three-way constraint** (not just MIN(LTV, DSCR)). Gap-fill acts as a ceiling: there's no point borrowing more than the project needs, even if the lender would fund it. This prevents deals from showing negative equity (sources > uses) when LTV/DSCR constraints are loose.

12. **Refi cap rate defaults to going-in cap, not exit cap**. Conservative: assumes no cap rate compression from value-add. The projected NOI at stabilization already reflects vacancy, bad debt, concessions, and lease-up — so the cap rate applied to it is purely about market pricing of the income stream, not operational risk discounting. Override via `refi_cap_rate_pct` for scenarios modeling cap compression.

13. **Bad debt and concessions as separate named fields** (not bundled into vacancy). The math is equivalent (all are % deductions from GPR), but separating them matches the standard CRE pro forma format and enables HelloData/CoStar data feeds that provide these as distinct fields.

14. **American-style waterfall only** (no European toggle). American (period-by-period distribution) is the standard for US multifamily syndications. European (return-all-capital-plus-pref-before-any-promote) can be modeled by arranging `return_of_equity` and `pref_return` tiers in the correct priority order — no separate engine path needed.

15. **Renovation absorption as a per-stream attribute** (not a global deal setting). Different income streams may have different absorption profiles — e.g., residential rent premiums phase in with unit turns, but parking income may stabilize immediately. Per-stream gives the user control without global assumptions.

16. **S-curve lease-up as opt-in** (linear default). Linear is transparent, conservative, and produces verifiable results. S-curve is more realistic for large projects but adds a steepness parameter that most users won't calibrate. Default to the simpler model; power users can switch via `lease_up_curve = "s_curve"`. Modeled after Adventures in CRE Development Model which offers a similar toggle.

17. **Debt yield as a standard output metric** alongside DSCR. Three of five benchmark models expose debt yield. Lenders increasingly use it as a rate-independent coverage measure. Computed as `NOI / total_debt_balance` — no new inputs required, just a new output.

18. **Loss-to-lease on UnitMix** (not IncomeStream). LTL is a property characteristic (market vs. in-place rent), not an income stream attribute. It lives on UnitMix because that's where unit-level rent data belongs. The value-add thesis is literally "buy at in-place, renovate to market."

19. **Discrete capture schedule as alternative to continuous ramp**. PropRise uses 0%/50%/100% year-by-year steps. This is simpler to explain to investors than a continuous fraction. Both options available per-stream: `renovation_capture_schedule` (discrete) overrides `renovation_absorption_rate` (continuous) when set.

20. **NOI-mode escalation anchored at first stabilized month** (April 18 2026). The user-entered `noi_stabilized_input` means "NOI at year 1 of stabilization" (underwriting convention), not "NOI at deal close". Previously escalation ran from deal month 0, causing DSCR drift in `dscr_capped` / `dual_constraint` sizing. Anchor fix: `esc_period = max(0, period − first_stab_period)`. First stabilized month = raw input (no escalation applied yet).

21. **Fix-point iteration for sizing convergence** (April 18 2026). DSCR-bound sizing requires knowing the "true" NOI, but the first compute pass can only use an estimate. Each subsequent call reads the previous OperationalOutputs.noi_stabilized, so re-running converges in 2 passes. The `/compute` endpoint loops up to 5x with a 0.005× DSCR tolerance. `gap_fill` mode breaks after one pass.

22. **Deal type labels renamed for business clarity** (April 18 2026). Display labels updated throughout the UI:
    - `acquisition` → "Acquisition" (was "Minor Renovation"). Construction milestone removed from the default preset — this strategy is pure hold/stabilize with LTL catchup or base escalation on unrenovated units.
    - `value_add` → "Value-Add" (was "Major Renovation"). Used for unit renovations with measurable rent uplift.
    - `conversion` → "Conversion" (was "Acquisition — Conversion"). Change-of-use projects.
    - `new_construction` unchanged.
    Enum values kept for DB compatibility; only display strings changed.

23. **Calculation Status pill over sidebar balance bar** (April 18 2026). A center-top pill replaces the legacy sidebar "Sources = Uses" banner. Surfaces three factors (S=U gap, DSCR vs. minimum, LTV vs. binding constraint) with per-factor details in a modal. Single-issue label shows the specific value ("⚠ -$478,284 Sources Gap" rather than "⚠ 1 issue") for immediate diagnostic context.

24. **Legacy `avg_monthly_rent` removed; beds/baths added** (April 18 2026). `avg_monthly_rent` duplicated `in_place_rent_per_unit` semantically. Beds (0–5+, whole numbers) and baths (0–3.5+, 0.5 increments) are now first-class numeric variables so comp-data ingestion can populate them directly. Migration 0046 drops the legacy column.

---

## 10. Sources (market data for closing cost defaults)

- [How Much Are Commercial Property Closing Costs? — commloan](https://www.commloan.com/research/commercial-property-closing-costs/)
- [Commercial Property Closing Costs: What to Know — Finance Lobby](https://financelobby.com/cre-insights/commercial-property-closing-costs-what-to-know/)
- [Bridge Loan Costs in 2025 — Hurst Lending](https://hurstlending.com/cost-of-a-bridge-loan/)
- [Phase I ESA Costs & Best Practices for 2025 — Aegis Environmental](https://aegisenvironmentalinc.com/phase-i-environmental-site-assessment-costs/)
- [Ins and Outs of Construction Loan Closing Costs — FasterCapital](https://fastercapital.com/content/Ins-and-Outs-of-Construction-Loan-Closing-Costs.html)
- [Construction Loan Closing Costs — mrrate](https://mrrate.com/guide/construction-loan-closing-costs-on-fees/)
- [Understanding Commercial Closing Costs — Rochford Law](https://info.rochfordlawyers.com/resources/understanding-commercial-closing-costs)
- FDIC Comptroller's Handbook — Commercial Real Estate Lending (for carry type conventions)
- Argus Enterprise, REFM documentation (for industry practice on IR, CI, True IO distinctions)

---

*Document current as of April 18, 2026. Recent updates: NOI escalation anchor + fix-point iteration (§4.6–4.7), Calculation Status diagnostic (§7.7), UnitMix bed/bath + strategy (§4.8), deal type rename, constants table. Prior: HelloData model parity (§2.8–2.10, §4.5, §6.4–6.5, §7.2 AM fee). When changing any formula, update the corresponding section and reference the commit hash.*

---

## Appendix A: Per-Loan Active-Window Months (April 2026)

### A.1 Why per-loan windowing replaced `constr_months_total`

Prior to April 2026, every bridge loan used the same global `constr_months_total` — the sum of all construction-type phase months. This was wrong for multi-debt deals where loans have different active periods. A pre-development loan active from close to construction should only count pre-construction months, not the full construction duration.

### A.2 Phase rank system

Each phase has a numeric rank. A loan's active window is `[start_rank, end_rank)` — half-open, end-exclusive.

```python
_PERIOD_TYPE_RANK = {
    PeriodType.acquisition:      0,
    PeriodType.hold:             1,
    PeriodType.pre_construction: 2,
    PeriodType.construction:     3,  # also minor_renovation, major_renovation, conversion
    PeriodType.lease_up:         4,
    PeriodType.stabilized:       5,
    PeriodType.exit:             6,
}

_APS_TO_RANK = {
    "acquisition": 0, "close": 0,
    "pre_construction": 2,
    "construction": 3,
    "lease_up": 4, "operation_lease_up": 4,
    "stabilized": 5, "operation_stabilized": 5,
    "exit": 6, "divestment": 6,
}
```

### A.3 `_loan_pre_op_months(module)` function

```python
def _loan_pre_op_months(module) -> int:
    start_rank = _APS_TO_RANK.get(module.active_phase_start, 0)
    end_rank   = _APS_TO_RANK.get(module.active_phase_end, 99)
    return sum(
        p.months for p in phases
        if p.period_type in _CONSTRUCTION_PERIOD_TYPES
        and start_rank <= _PERIOD_TYPE_RANK.get(p.period_type, 99) < end_rank
    )
```

**End-exclusive semantics.** `active_phase_end = "operation_stabilized"` (rank 5) means the loan is active for all phases with rank < 5. The loan is NOT active during stabilized itself — it is taken out at the START of stabilized. This matches CRE convention: a construction loan is retired when the project stabilizes.

**Example.** A construction loan with `active_phase_start = "pre_construction"` (rank 2) and `active_phase_end = "lease_up"` (rank 4):
- Counts pre_construction (rank 2) + construction (rank 3) = both included
- Does NOT count lease_up (rank 4) — end-exclusive
- If pre_construction = 3 months, construction = 12 months → N = 15

### A.4 Impact on carry formulas

All three bridge loan branches (pre-dev, acquisition, construction) call `_n = _loan_pre_op_months(_m)` instead of the global `constr_months_total`. The carry formulas themselves are unchanged — only the input `N` is now per-loan.

---

## Appendix B: Milestone Trigger Chains (April 2026)

### B.1 How phase durations reach the engine

The cashflow engine derives phase months from milestone dates. Milestones form a **trigger chain**: each non-anchor milestone has a `trigger_milestone_id` pointing to the previous milestone, with `trigger_offset_days = 0`. The chain is:

```
close (anchor, fixed date) → pre_development → construction → lease_up → stabilized → divestment
```

`computed_start(milestone_map)` walks the chain: `start = trigger_milestone.computed_start() + trigger_milestone.duration_days + offset_days`.

### B.2 Fallback behavior

If a milestone has no `trigger_milestone_id`, `computed_start()` returns `None`. The engine then falls back to `OperationalInputs.*_months` scalars. If those are also NULL (common for wizard-created deals), the phase defaults to 1 month.

This fallback produces degenerate carry math — e.g., a 12-month construction project computing with N=1. Deals created before the trigger-chain fix (commit `5d5caf4`) may need a backfill script.

### B.3 Timeline wizard two-pass creation

The timeline wizard creates milestones in two passes:
1. **Pass 1:** Create all milestones with durations + target_date on the anchor
2. **Pass 2:** Wire `trigger_milestone_id` so `computed_start()` resolves for every non-anchor milestone

Without Pass 2, the engine can't derive phase durations from milestones.

### B.4 Divestment as a single-day event

Divestment has `duration_days = 1` across all deal types. It represents the sale closing date — a point-in-time event, not a phase with duration. The cashflow engine uses `PhaseSpec(PeriodType.exit, 1)` for the exit phase regardless of the milestone's actual duration.

On the Gantt, divestment gets a minimum display width of 30 days for visual presence (`_GANTT_DISPLAY_MINS`).

---

## Appendix C: Multi-Phase Carry Configuration (April 2026)

### C.1 Phased carry format

A single loan can have different carry types in different phases. The `carry` JSONB column stores this as:

```json
{
  "phases": [
    {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": 7.0},
    {"name": "operation",    "carry_type": "pi",               "io_rate_pct": 6.5, "amort_term_years": 30}
  ]
}
```

The engine's `_carry_type_for_phase(carry, is_construction)` extracts the carry type for the relevant phase. The `_get_phase_carry(carry, phase_name)` function returns the full phase dict for rate lookup.

### C.2 Rate lookup precedence

For any carry calculation, the rate is resolved as:
1. `source["interest_rate_pct"]` (from the capital module's source config)
2. `carry_phase["io_rate_pct"]` (from the phase-specific carry dict)
3. `carry["io_rate_pct"]` (from the flat carry format, legacy)

### C.3 Common patterns

| Pattern | Construction carry | Operations carry | Example |
|---|---|---|---|
| True IO → P&I | `io_only` | `pi` | Typical construction + perm |
| Interest Reserve → P&I | `interest_reserve` | `pi` | Construction with reserve |
| Capitalized Interest → P&I | `capitalized_interest` | `pi` | PIK during construction |
| IO then PI (C2P) | `io_only` | `pi` | Construction-to-perm bond |

### C.4 `"accruing"` alias

The carry type `"accruing"` is normalized to `"capitalized_interest"` by `_carry_type_for_phase()` in the cashflow engine only. The waterfall engine keeps `"accruing"` distinct for side-pocket vs principal accrual treatment. User-facing UI shows "Capitalized Interest (PIK)".
