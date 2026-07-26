# Quadfit — Multnomah County quadplex buildability analysis

Standalone, re-runnable pipeline answering: **on how many Multnomah County lots
does a quadplex footprint of shape W×D physically fit inside the zoning setback
envelope, by-right?** Statistics only — no app/DB/UI integration.

Legal frame: HB 2001 / OAR 660-046 — Large Cities (Portland, Gresham,
Troutdale, Fairview, Wood Village) + urban unincorporated Multnomah inside the
Metro UGB must allow quadplexes in residential zones that allow detached
single-family homes. Results are an **upper bound**: private easements, tree
code, utilities, driveway access, and overlay zones (phase 2) are not modeled.
On-lot parking is out of scope for 1-for-1 conversion lots (street parking
assumed); split candidates budget a per-quad parking buffer (stalls only, no
travel lanes) via the `split:` block in `config/footprints.yaml`.

## Run

```bash
uv sync --extra tools --extra gis
uv run --extra tools --extra gis python tools/quadfit/run_all.py           # all stages
uv run --extra tools --extra gis python tools/quadfit/run_all.py --stage s6 --force
```

Stages cache intermediates in `data/quadfit/*.parquet` (WKB geometry columns);
`run_all.py` skips stages whose outputs are newer than their inputs.

**Structural vs policy split — what needs re-running when:**

| Change | Re-run |
|---|---|
| Jurisdiction on/off (`eligible:`), min lot area, min frontage, orientation constraint, coverage cap, parking buffer / split thresholds | `python tools/quadfit/s7_report.py` only (**seconds**) |
| New footprint rectangle or sweep | s6–s7 (minutes) |
| Setback values, new zone rows | s5–s7 (run_all handles cascade) |
| New jurisdiction with no compiled rules yet | s3 onward |

s3 keeps a geometry SUPERSET (drops only what no config change can revive:
condo stacks, unmapped/no-rules jurisdictions, outside-UGB, quadplex-never
zones, slivers); s6 computes both orientations raw. Everything configurable —
jurisdiction toggles, z overlay, min-lot/frontage gates, orientation policy,
coverage, split math — is applied at report time in s7 from stored columns.
Note run_all's mtime cascade re-runs from s2 when `rules.yaml` changes; for
policy-only edits invoke s7 directly as above.

## Stages

| Stage | Script | Does |
|---|---|---|
| s0 | `s0_acquire.py` | Downloads: RLIS taxlots + streets (ZIP range-extraction via `tools/gis_cache/rlis_delta.py` helpers), per-city zoning layers (`tools/gis_cache/cache_layers.py`), UGB |
| s1 | `s1_normalize.py` | Reproject to EPSG:2913 (ft), make_valid, condo-stack dedupe |
| s2 | `s2_assign.py` | Jurisdiction tag (JURIS_CITY) + majority-area zone spatial join (STRtree) + Portland Constrained Sites "z" overlay flag (PCC 33.418) |
| s3 | `s3_filter.py` | STRUCTURAL funnel only — drops nothing a config toggle could revive; every drop counted |
| s4 | `s4_edges.py` | Front/side/rear edge classification vs street centerlines; confidence tiers A/B/C/D |
| s5 | `s5_envelope.py` | Setback envelope: lot − per-edge buffers (conservative) |
| s6 | `s6_fit.py` | Rotate→rasterize→integral-image rectangle fit, BOTH orientations raw; max-depth-per-width frontier |
| s7 | `s7_report.py` | POLICY gates (eligibility, z overlay, min lot/frontage, orientation, coverage) + split screen + `summary.md`, `lots_results.csv`, `conversion_candidates.csv`, `split_candidates.csv`, `spot_check.geojson` |

## Config

- `config/rules.yaml` — per (jurisdiction, zone): quadplex_allowed, setbacks,
  coverage cap, source citation, confidence flag. `needs_verification` rows are
  preliminary; do not publish results until verified.
- `config/footprints.yaml` — candidate rectangles, orientations, fixed-area
  aspect-ratio sweeps, frontier grid, and the `split:` block. **Product frame
  (2026-07-24): 1,000 sqft 2-story townhomes, ~500 sqft ground footprint,
  built as pods of 4 side-by-side — the fit rectangle is the whole pod
  (4×unit-width × unit-depth, ~2,000 sqft). The 2,000 sqft constant-area
  sweep's pod width ÷ 4 = unit width.** Also the `split:` block (large-lot
  subdivision screen: per carved quadplex lot = `quad_ground_sqft` buildable +
  units × slots/unit × sqft/slot parking, stalls only, plus the zone's quadplex
  minimum lot area; `min_quads` sets the split-candidate bar). Split math is
  pure attribute arithmetic — any knob change is an s7-only re-run. Conversion
  (non-split) lots carry NO parking requirement by design.

## Outputs

`data/quadfit/summary.md` (headline stats) · `lots_results.csv` (whole geometry
universe, `policy_exclusion` + `eligible` columns) · `conversion_candidates.csv`
(eligible, a footprint fits, NOT split-worthy — the 1 SFR→4plex list) ·
`split_candidates.csv` (eligible, carves ≥ min_quads quadplex lots, sorted by
carve count) · `spot_check.geojson` (eyeball in geojson.io).

## Confidence tiers

A = clean rectangular-ish lot · B = corner (two frontages, both orientations
tested) · C = flag/irregular (conservative uniform-setback envelope) ·
D = landlocked/failed classification (excluded from headline numbers).

## Known blind spots (also restated in every summary.md)

Private easements (title-report only), Portland tree preservation, environmental
/historic overlays beyond the z gate (phase 2), steep slopes, utility conflicts,
driveway curb-cut feasibility, existing structures assumed demolished (building
value + year built carried in output for later filtering). Per-jurisdiction
quirks not modeled: maximum front setbacks (Gresham DRL, Fairview base zones)
which force the building toward the street; Gresham 15% private-open-space
minimum; Wood Village 5/12 roof-pitch minimum; Lake Oswego front-porch
requirement and Mountain Park HOA CC&Rs (pre-HB-2001 private covenants);
Portland maintained-street-frontage + visitability gates; alley setback
reductions. Substandard lots of record below a zone's quadplex minimum may
still carry quadplex rights under OAR 660-046 — the funnel counts that drop
separately (`lot_below_zone_min_area`).
