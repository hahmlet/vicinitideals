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

**Code (cashflow.py, construction loan branch around line 821):**
```python
elif _ft == "construction_loan":
    _r = Decimal(str(_cr or 0))
    _cl_ct = _carry_type_for_phase(_carry, is_construction=True)
    if _cl_ct == "interest_reserve":
        _io_f = (_r / HUNDRED / Decimal("12")
                 * (Decimal(constr_months_total + 1) / Decimal("2"))
                 ) if (_r > ZERO and constr_months_total > 0) else ZERO
    elif _cl_ct == "capitalized_interest":
        _io_f = (_r / HUNDRED / Decimal("12") * Decimal(constr_months_total)
                 ) if (_r > ZERO and constr_months_total > 0) else ZERO
    else:  # io_only
        _io_f = ZERO
    _div = ONE - _io_f
    _principal = _q(constr_costs / _div) if (_div > ZERO and constr_costs > ZERO) else constr_costs
```

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

#### Code (cashflow.py, line ~1049)
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
net_income = escalated × occupancy_pct_this_phase
vacancy = escalated − net_income
```

Summed across all active streams → gross_revenue, vacancy_loss, EGI.

**Why `(1 + rate)^(period/12)`?** This is continuous annual escalation — `rate = 3%` compounds monthly at `(1.03)^(1/12) − 1 ≈ 0.247%`. At month 24 (two years in), the factor is `1.03^2 = 1.0609` exactly.

### 4.3 Occupancy ramp (lease-up)

**Formula:**
```
step = (stabilized_occ − initial_occ) / (months − 1)
occupancy_month_i = clamp(initial_occ + step × i, 0, stabilized_occ)
```

Where `initial_occ` defaults to 50% and `stabilized_occ` defaults to 95% (configurable per stream / per deal).

**Why 50% initial?** This is the `OperationalInputs.initial_occupancy_pct` field. In new construction it might be 0%; in acquisition-with-repositioning it might be 60% (existing tenants retained). The default of 50% is a reasonable lease-up scenario that users will commonly overwrite.

**Why linear, not S-curve?** An S-curve (slow-fast-slow) would be more realistic for brand-new lease-up, but it introduces a second parameter (curve steepness) that users don't know how to set. Linear is transparent and produces conservative results in the middle months.

### 4.4 Occupancy in hold / renovation phases

**Hold phase:** `stabilized_occ × (1 − hold_vacancy_rate_pct)` — user-specified vacancy during the hold period (e.g., while planning renovations).

**Renovation phase:** `stabilized_occ × (1 − income_reduction_pct_during_reno)` — user-specified income hit during renovations.

### 4.5 NOI-mode direct input

```python
_noi_annual = _to_decimal(inputs.noi_stabilized_input)
_esc_factor = _growth_factor(inputs.noi_escalation_rate_pct or Decimal("3"), period)
_noi_monthly = _q(_noi_annual / Decimal("12") * _esc_factor)
```

Applied month-by-month in stabilized/lease-up/exit phases. Construction phases see `_noi_monthly = 0`.

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

---

## 7. Waterfall & Profit Metrics

### 7.1 Module stack and tiers

**Capital modules** (`CapitalModule`) define the stack: debt and equity lines with a `stack_position` (0 = senior, higher = junior) and a `funder_type` (`permanent_debt`, `construction_loan`, `common_equity`, etc.).

**Waterfall tiers** (`WaterfallTier`) define the distribution order. Each tier has:
- `priority`: execution order (1 = first)
- `tier_type`: one of `debt_service`, `pref_return`, `return_of_equity`, `catch_up`, `irr_hurdle_split`, `deferred_developer_fee`, `residual`
- `lp_split_pct`, `gp_split_pct`: split ratios (for splittable tiers)
- `irr_hurdle_pct`: hurdle rate (for `irr_hurdle_split`)
- `capital_module_id`: optional link to a specific module

### 7.2 Capital calls (pre-distribution)

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

*Document current as of April 2026. When changing any formula, update the corresponding section and reference the commit hash.*
