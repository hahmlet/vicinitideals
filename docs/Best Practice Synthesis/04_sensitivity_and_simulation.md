# 04 — Sensitivity and Simulation: Handling Uncertainty in CRE Underwriting

## Why This Matters for Viciniti

Every deal Viciniti underwrites rests on a stack of assumptions that range from the mildly uncertain (Year-1 vacancy in a stabilized asset) to the wildly uncertain (exit cap rate in five years, construction cost escalation on a ground-up build). A deterministic model — one number in, one number out — quietly buries this uncertainty and pretends the single IRR it spits out is truth. Practitioners know better. The whole point of "deal intelligence" is separating the returns that are robust from the returns that exist only on a narrow knife-edge of inputs.

This is why the uncertainty toolchain — sensitivity tables, scenario analysis, and Monte Carlo simulation — exists. It is how institutional LPs, IC members, and savvy sponsors stress-test a deal before wiring capital. Viciniti already ships a multi-variable sensitivity engine (`app/engines/sensitivity.py`); the question is how far up the stack we should climb, and how to do it without misleading the user with false precision. The corpus is clear that each tier solves a different problem, and that Monte Carlo — while powerful — is "rarely used in real estate analysis" in practice, making it a genuine differentiator if implemented honestly (source 75).

## The Spectrum of Uncertainty Techniques

**Deterministic.** A single base case with best-guess inputs. This is the DCF most shops live in. Fast, auditable, and the foundation for everything else. Source 68 treats the deterministic model as the template — blue-font inputs, black-font calcs, and a clean audit trail — and notes that hypothetical assumptions baked into a template "are likely not" right for any specific deal. The deterministic model is where discipline lives; it is not where risk lives.

**Sensitivity tables.** Hold everything constant, flex one or two variables, and tabulate the output (usually IRR, NPV, or price at target return). The classic Excel `Data Table` feeding a two-way grid of exit cap × rent growth is the workhorse of committee memos. It answers "how bad does X have to get before this deal breaks?"

**Scenario analysis.** Define named, internally-consistent bundles — Base, Downside, Upside — where multiple inputs move together in plausible combinations (e.g., a downside where rent growth falls AND vacancy rises AND exit cap expands, because those tend to co-move in a recession). Scenario analysis handles correlation by construction; the analyst's judgment bundles the variables.

**Monte Carlo simulation.** Assign a probability distribution to each uncertain input, draw a random value from each distribution on every iteration, and run thousands of iterations to generate a distribution of outcomes. Source 74 walks through a no-add-in Excel implementation using `RANDBETWEEN()` driving inputs and Excel's `Data Table` feature as the iteration harness, running 1,000 simulations on an apartment DCF. Source 75's more robust model runs 10,000 iterations over eight variables and produces mean, min, max, and standard deviation for both IRR and NPV.

## What Variables Get Sensitized

The corpus converges on a consistent list of the variables that matter most. Source 75's Monte Carlo module parameterizes eight:

1. Rent growth rate
2. Other income growth rate
3. Operating expense growth rate
4. Capital expenditures growth rate
5. Releasing (TI/LC) cost growth rate
6. Terminal (exit) cap rate
7. Days vacant between leases
8. Renewal probability

Source 74's simpler tutorial focuses on three: rent growth, expense growth, and exit cap rate — which are the three that reliably dominate IRR variance in a stabilized acquisition. For development and value-add, add construction cost escalation, lease-up pace, and interest rate (debt carry) to the list. The principle: sensitize the inputs where you have the least conviction and the most leverage on returns.

## Choosing a Distribution

Source 74 demonstrates uniform distribution (every outcome equally likely within a bounded range) via `RANDBETWEEN()`. Source 75 supports both uniform and normal, and recommends normal: "I recommend normal, as I think it is more accurate. You will need to set a mean (average) change in rate and a standard deviation for the change in rate." This is a judgment call, not a law — normal distributions have thin tails and can understate the probability of extreme outcomes (e.g., a GFC-style cap-rate blowout). For variables with hard physical floors (vacancy can't go below 0%, cap rates don't go to zero), truncated distributions are more honest.

Source 75 also introduces a **Random Walk with momentum** concept borrowed from Leung's MIT thesis: each year's rate depends on the prior year's rate rather than being drawn independently. This matters because independent annual draws wash out over a 5-10 year hold (mean reversion by construction), which can make a Monte Carlo falsely comforting. Path-dependence (a bad year leads to another bad year) is closer to how real markets behave.

## Interpreting Monte Carlo Outputs

The output of a Monte Carlo is not "the answer" — it is a distribution. Source 74 calculates the mean as the "Expected Value" (what you'd pay to hit an 8% return given the assumptions), plus min, max, and standard deviation, invoking the 68-95-99 rule: 68% of outcomes within one standard deviation, 95% within two. In the tutorial's apartment example: expected value ~$1.2M, range $925K–$1.5M.

In practice, committees and LPs look at:

- **P10 / P50 / P90** — the 10th, 50th (median), and 90th percentile outcomes. P10 IRR is the "how bad could this plausibly get" number.
- **Probability of hitting return thresholds** — e.g., "what's the probability IRR ≥ 15%?" computed by counting iterations above the threshold.
- **Loss probability** — fraction of iterations where equity multiple < 1.0x.
- **Distribution shape** — skew and kurtosis matter. A right-skewed IRR distribution (long upside tail) tells a different story than a symmetric one.

Source 75 reports mean, min, max, and standard deviation for both unlevered IRR and NPV across 10,000 simulations — the core dashboard.

## When Each Approach Is Appropriate

- **Deal screening (dozens of parcels/week).** Deterministic. Speed matters; a Monte Carlo on a deal you'll kill in 20 minutes is waste.
- **Initial underwrite / LOI prep.** Sensitivity tables. Two-way grids of exit cap × rent growth flag whether the deal has obvious fragility.
- **Investment committee memo.** Scenario analysis (Base/Down/Up) plus targeted sensitivity. Committees want to see "what breaks the deal" explicitly, not a probability cloud.
- **LP presentation / fund-level risk reporting.** Monte Carlo. Institutional LPs increasingly want distributional answers (P10 IRR, loss probability) not single-point estimates. Source 75 notes this is "rarely used in real estate analysis" — meaning it's differentiated when done well.
- **Portfolio / fund aggregation.** Monte Carlo with correlated draws across deals.

## Common Pitfalls

1. **Assuming normal distributions inappropriately.** Cap rates and construction costs have fat tails. A normal assumption understates tail risk (source 75 prefers normal but this is a simplification, not gospel).
2. **Ignoring correlation.** In a real recession, rent growth falls *and* vacancy rises *and* cap rates expand *simultaneously*. Independent draws across these variables produce an artificially narrow outcome distribution. Scenario analysis handles this by construction; naive Monte Carlo does not.
3. **Path independence.** Drawing each year's rent growth independently washes out variance over long holds. Source 75's Random Walk with momentum addresses this.
4. **False precision.** Reporting "mean IRR = 14.73%" from 10,000 iterations implies a confidence the inputs don't support. The ranges (P10–P90) are the story, not the mean.
5. **Garbage-in amplification.** Monte Carlo multiplies the analyst's input uncertainty by the number of variables. If the rent-growth distribution is itself a guess, running 10,000 iterations doesn't make it any more accurate — it just dresses up the guess.
6. **Hidden circularity.** Source 68 warns strongly against circular references and iterative calculation, which become especially dangerous under stochastic inputs because the iteration can fail to converge differently on each simulation draw.
7. **Running simulations by accident.** Source 75 disables autocalculate on open/save because Data Table-driven Monte Carlo can hang Excel for minutes if triggered unintentionally — a UX lesson that applies directly to any web-based simulation feature.

## Viciniti Implications

- **Keep sensitivity tables as the default, first-class output.** They're fast, auditable, and match how committees actually consume risk. The existing `app/engines/sensitivity.py` multi-variable module is the right primary surface. Add two-way grid presets for exit cap × rent growth and DSCR × interest rate.
- **Add named scenarios (Base/Down/Up) as the next tier before Monte Carlo.** Let users save scenario bundles on a `Scenario` and compare side-by-side. Scenarios handle variable correlation by analyst judgment — a better fit for IC memos than naive stochastic draws.
- **If/when we build Monte Carlo, report P10/P50/P90 and probability-of-threshold, not just mean/stdev.** Source 74's "expected value" framing undersells the real output; institutional users want percentiles and threshold probabilities (e.g., P(IRR ≥ 15%), P(EM < 1.0x)).
- **Run simulations server-side via Celery analysis queue, not in-request.** 10,000 iterations of the cashflow engine will not fit in an HTTP request. The `vicinitideals-worker-analysis` queue already exists; a `simulate_scenario` task that returns a result ID for later poll/download is the right shape. Use `Decimal` throughout to match the cashflow engine's money semantics.
- **Offer truncated/bounded distributions and optional correlation structure.** At minimum, allow users to bound a variable (cap rate ≥ 0, vacancy ∈ [0%, 100%]) and optionally link variables (e.g., "when rent growth draws below base, vacancy draws above base") so we don't ship a feature that systematically understates tail risk. Adopt source 75's Random Walk with momentum for multi-year growth variables.

## Sources

- Source 68 — *Best Practices in Real Estate Financial Modeling*
- Source 74 — *Monte Carlo Simulations in Excel for Real Estate*
- Source 75 — *Apartment Acquisition Model with Monte Carlo Simulation Module*
- Source 76 — *How to Use the Apartment Acquisition Model's Monte Carlo Simulation Module*
