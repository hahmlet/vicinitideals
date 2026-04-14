# Benchmark Fixture Library

Canonical `REAL-42` benchmark exports used for deterministic regression coverage:

| Fixture | Project type | Purpose |
| --- | --- | --- |
| `tower_acquisition.json` | `acquisition_minor_reno` | Tower acquisition / minor-reno benchmark |
| `ap_conversion.json` | `acquisition_conversion` | A&P acquisition / conversion benchmark |
| `synthetic_new_construction.json` | `new_construction` | Synthetic edge-case benchmark for milestone-driven new construction |

Each file is a portable `deal-json-v1` export snapshot plus:

- `benchmark_metadata.fixture_version` for fixture versioning
- `benchmark_expectations.outputs` for NOI / IRR / DSCR / equity-multiple checks
- `benchmark_expectations.waterfall_distribution` for capital-module and tier-level waterfall totals

## Parity tolerances

`REAL-43` uses the following thresholds for regression parity against the known-good Excel baselines:

- **Dollar figures:** ±`$1.00`
- **Rates / ratios / multiples:** ±`0.01`
- **Cash-flow coverage:** the Tower + A&P checks compare the first 48 monthly periods (Years 1–4) row-by-row after recomputing the engine outputs

Regression coverage lives in `tests/exporters/test_benchmark_fixtures.py`.
