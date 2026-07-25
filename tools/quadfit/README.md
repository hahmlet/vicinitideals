# Quadfit — Multnomah County quadplex buildability analysis

Standalone, re-runnable pipeline answering: **on how many Multnomah County lots
does a quadplex footprint of shape W×D physically fit inside the zoning setback
envelope, by-right?** Statistics only — no app/DB/UI integration.

Legal frame: HB 2001 / OAR 660-046 — Large Cities (Portland, Gresham,
Troutdale, Fairview, Wood Village) + urban unincorporated Multnomah inside the
Metro UGB must allow quadplexes in residential zones that allow detached
single-family homes. Results are an **upper bound**: private easements, tree
code, utilities, driveway access, and overlay zones (phase 2) are not modeled.
On-lot parking is explicitly out of scope.

## Run

```bash
uv sync --extra tools --extra gis
uv run --extra tools --extra gis python tools/quadfit/run_all.py           # all stages
uv run --extra tools --extra gis python tools/quadfit/run_all.py --stage s6 --force
```

Stages cache intermediates in `data/quadfit/*.parquet` (WKB geometry columns);
`run_all.py` skips stages whose outputs are newer than their inputs. Editing
`config/footprints.yaml` only requires re-running s6–s7 (minutes).

## Stages

| Stage | Script | Does |
|---|---|---|
| s0 | `s0_acquire.py` | Downloads: RLIS taxlots + streets (ZIP range-extraction via `tools/gis_cache/rlis_delta.py` helpers), per-city zoning layers (`tools/gis_cache/cache_layers.py`), UGB |
| s1 | `s1_normalize.py` | Reproject to EPSG:2913 (ft), make_valid, condo-stack dedupe |
| s2 | `s2_assign.py` | Jurisdiction tag (JURIS_CITY) + majority-area zone spatial join (STRtree) + Portland Constrained Sites "z" overlay flag (PCC 33.418) |
| s3 | `s3_filter.py` | Eligibility funnel — every exclusion counted (incl. z-overlay voiding the fourplex allowance, per-zone quadplex minimum lot areas) |
| s4 | `s4_edges.py` | Front/side/rear edge classification vs street centerlines; confidence tiers A/B/C/D |
| s5 | `s5_envelope.py` | Setback envelope: lot − per-edge buffers (conservative) |
| s6 | `s6_fit.py` | Rotate→rasterize→integral-image rectangle fit; max-depth-per-width frontier; constant-area sweeps; coverage cap |
| s7 | `s7_report.py` | `lots_results.parquet`/CSV, `summary.md`, `spot_check.geojson` |

## Config

- `config/rules.yaml` — per (jurisdiction, zone): quadplex_allowed, setbacks,
  coverage cap, source citation, confidence flag. `needs_verification` rows are
  preliminary; do not publish results until verified.
- `config/footprints.yaml` — candidate rectangles, orientations, fixed-area
  aspect-ratio sweeps, frontier grid.

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
