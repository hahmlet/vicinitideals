# Quadfit — Multnomah County quadplex buildability analysis

Standalone, re-runnable pipeline answering: **on how many Multnomah County lots
does a quadplex footprint of shape W×D physically fit inside the zoning setback
envelope, by-right?** Statistics only — no app/DB/UI integration.

Legal frame: HB 2001 / OAR 660-046 — Large Cities (Portland, Gresham,
Troutdale, Fairview, Wood Village) + urban unincorporated Multnomah inside the
Metro UGB must allow quadplexes in residential zones that allow detached
single-family homes. Results are an **upper bound**: private easements, tree
code, utilities, driveway access, and overlay zones (phase 2) are not modeled.
On-lot parking is a crude area budget in the base pipeline: out of scope for
1-for-1 conversion lots (street parking assumed); split candidates budget a
per-quad parking buffer (stalls only, no travel lanes) via the `split:` block
in `config/footprints.yaml`. **Stage s6s (site-plan generator, Gresham LDR-5
pilot)** replaces that crude budget with a real per-lot layout — building +
driveway + 90° stalls + a 15% private open-space reservation — and tightens the
conversion verdict to "a full site plan resolves", not just "a bare rectangle
fits". Pilot-scoped; every other cell passes through untightened.

## Run

```bash
uv sync --extra tools --extra gis
uv run --extra tools --extra gis python "Lot Analysis/quadfit/run_all.py"           # all stages
uv run --extra tools --extra gis python "Lot Analysis/quadfit/run_all.py" --stage s6 --force
```

Stages cache intermediates in `data/quadfit/*.parquet` (WKB geometry columns);
`run_all.py` skips stages whose outputs are newer than their inputs.

**Structural vs policy split — what needs re-running when:**

| Change | Re-run |
|---|---|
| Jurisdiction on/off (`eligible:`), min lot area, min frontage, orientation constraint, coverage cap, parking buffer / split thresholds, overlay kill↔flag reclassification, slope tier cutlines, sewer cutoff (`SEWER_REVIEW_FT`) / district gate | `python "Lot Analysis/quadfit/s7_report.py"` only (**seconds**) |
| Sampled site-plan drawings only (no counts change) | `python "Lot Analysis/quadfit/s7_report.py"` only (**seconds**) |
| `siteplan:` block values (stall/aisle/driveway dims, parking tiers, open-space %, pilot cell) | s6s–s7 (minutes) |
| New footprint rectangle or sweep | s6–s7 (minutes) |
| Overlay carve buffer_ft, new carve overlay layer | s5o–s7 (~40 min) |
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
| s5o | `s5o_overlays.py` | Phase 2: per-overlay any-touch flags + intersection sqft, CARVE overlays subtracted from the envelope, per-lot slope stats (USGS 3DEP 1 m DEM), sewer-main distance, sanitary sewer-district membership (`in_sewer_district`, Clackamas `Sewer_Districts` polygons). Driven by `config/overlays.yaml`; missing layers degrade to caveats, never crashes |
| s6 | `s6_fit.py` | Rotate→rasterize→integral-image rectangle fit against the CARVED envelope, BOTH orientations raw; max-depth-per-width frontier |
| s6s | `s6s_siteplan.py` | Procedural site-plan generator (Gresham LDR-5 pilot). Re-reads the carved envelope from s5o and lays out an attached-townhome site plan per lot (Gresham §7.0431): pod at the front, one consolidated driveway down a SIDE to a REAR 90° parking court, forward access (nothing backs onto the street), plus a 15% private open-space reservation; reports best parking tier + `site_plan_ok`. One typology (`townhome_rear_court`); the layout tries every pod size × orientation and keeps the most stalls, capped at the preferred tier (8/pod). Non-pilot lots pass through as `not_evaluated` |
| s7 | `s7_report.py` | POLICY gates (eligibility, z overlay, min lot/frontage, orientation, coverage) + split screen + site-plan tightening of the pilot's conversion verdict + **per-lot binding-constraint attribution and green/review/red triage** + `summary.md`, `lots_results.csv`, `conversion_candidates.csv`, `split_candidates.csv`, `binding_constraints.csv`, `review_candidates.csv`, `spot_check.geojson`, `siteplans.geojson` |

## Config

- `config/rules.yaml` — per (jurisdiction, zone): quadplex_allowed, setbacks,
  coverage cap, source citation, confidence flag. `needs_verification` rows are
  preliminary; do not publish results until verified.
- `config/overlays.yaml` — phase 2 policy: per-overlay kill/carve/flag verdict
  with citation + per-jurisdiction data-coverage grades (A/B/C/X — feed the
  report's coverage matrix + caveats), slope tier cutlines, sewer coverage
  notes. Kill/flag/tier edits are s7-only re-runs; carve buffers are s5o+.
  Legal code-text extracts backing the verdicts live in `provenance/`.
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
  (non-split) lots carry NO parking requirement in the base pipeline by design.
  Also the `siteplan:` block (stage s6s, Gresham LDR-5 pilot): parking tiers
  (min/target/preferred = 1 / 1.5 / 2 stalls per townhome unit — a
  marketability target, NOT the legal floor, which is zero here), stall/aisle/
  driveway dimensions, and the 15% private open-space reservation, all with
  Gresham CDC citations. `enabled: false` turns the stage off (lots pass
  through as `not_evaluated`). Value edits are s6s+s7 re-runs.

## Outputs

`data/quadfit/summary.md` (headline stats) · `lots_results.csv` (whole geometry
universe, `policy_exclusion` + `eligible` columns) · `conversion_candidates.csv`
(eligible, a footprint fits, NOT split-worthy — the 1 SFR→4plex list) ·
`split_candidates.csv` (eligible, carves ≥ min_quads quadplex lots, sorted by
carve count) · `viable_candidates.csv` (fitting lots that clear the per-door
land-cost ceiling from `screen:`, cheapest dirt first — the practical target
list) · `spot_check.geojson` (eyeball in geojson.io) · `siteplans.geojson`
(sampled Gresham LDR-5 site-plan drawings from s6s — one feature per role:
`lot`, `envelope`, `building`, `parking_court`, `driveway`, `stall_<i>`,
`utility`; drop into geojson.io).

Pilot (Gresham LDR-5) conversion candidates additionally carry `site_plan_ok`,
`parking_tier`, `stalls_provided`, `layout_method`, `driveway_len_ft`,
`open_space_sqft`, and `open_space_ok` from s6s.

Every candidate CSV carries the acquisition economics: `acq_estimate`
(post-COVID arm's-length sale where recorded, else county Real Market Value),
`acq_basis`, `doors_planned`, `land_cost_per_unit`, and `viability`
(preferred ≤ $30k / viable ≤ $45k / over_budget / unknown).

### Triage & binding constraint (s7)

`lots_results.csv` additionally carries these per-lot columns:

- `triage` — **green** (passes every hard, trustworthy test — safe to pursue) ·
  **review** (passes the hard tests but a silent-killer or low-trust signal
  needs a human before diligence spend: a narrow flag-lot neck, an irregular
  tier-C shape, steep/unknown slope, unconfirmed sewer, an unverified zone
  rule, or a flag-action overlay) · **red** (a hard test fails). Review
  deliberately absorbs the wide-flag-pole false-green — the raster fit can't
  see the access strip, so a suspect flag lot is never hard-greened.
- `flag_suspect` — narrow street neck (frontage ≤ 30 ft) on an otherwise large
  lot (≥ 4,000 sqft): the flag-lot pole heuristic that routes to review.
- `binding_constraint` — the single first-hit reason a lot is NOT buildable
  (`policy → no-envelope → no-fit → over-coverage → site-plan sub-reason →
  no_public_sewer`), `""` when buildable.
- `in_sewer_district` — lot falls inside a mapped Clackamas sanitary sewer
  district polygon (the basis for the sewer gate below).

Locator columns on every result CSV: `TLID` (tax-lot ID), `SITEADDR` (address,
often `NO SITUS` on vacant/unaddressed lots), and `lat` / `lng` (raw lot polygon
centroid, WGS84) so the list maps and navigates without a GIS join.

**Sewer gate.** A 4-plex ties into a main at the street, so "on sewer" means a
mapped main within `SEWER_REVIEW_FT` = **50 ft** (`s7_report.py`) — a real
nearby main always wins (green-eligible). Where no main is that close, the
Clackamas `Sewer_Districts` polygon layer decides, but only in Clackamas (its
coverage): **inside a district → review** (connectable, unconfirmed — the WES /
Clean Water Services gap areas with no published main linework); **outside every
district → red** (`no_public_sewer` — genuine septic). Multnomah has no district
map, so its no-main lots stay review, never forced red.

Two derived files: `binding_constraints.csv` (the binding-constraint histogram —
where design or acquisition strategy pays off most, structural-funnel counts
folded in) and `review_candidates.csv` (the `triage == review` human queue).

## Confidence tiers

A = clean rectangular-ish lot · B = corner (two frontages, both orientations
tested) · C = flag/irregular (conservative uniform-setback envelope) ·
D = landlocked/failed classification (excluded from headline numbers).

## Known blind spots (also restated in every summary.md)

Private easements (title-report only), Portland tree preservation, historic
overlays, driveway curb-cut feasibility, sewer capacity (proximity only),
unincorporated-county SEC overlays (unmapped publicly — Metro Title 3 used as
proxy), Wood Village local environmental mapping (none exists — regional layers
only), existing structures assumed demolished (building
value + year built carried in output for later filtering). Per-jurisdiction
quirks not modeled: maximum front setbacks (Gresham DRL, Fairview base zones)
which force the building toward the street; Gresham 15% private-open-space
minimum; Wood Village 5/12 roof-pitch minimum; Lake Oswego front-porch
requirement and Mountain Park HOA CC&Rs (pre-HB-2001 private covenants);
Portland maintained-street-frontage + visitability gates; alley setback
reductions. Substandard lots of record below a zone's quadplex minimum may
still carry quadplex rights under OAR 660-046 — the funnel counts that drop
separately (`lot_below_zone_min_area`).

**Retired for the Gresham LDR-5 pilot (stage s6s):** on-lot parking geometry,
driveway layout (curb-cut *throat length/spacing* still a documented gap — lives
in Gresham PWS A5.000, not the CDC), and the Gresham 15% private-open-space
minimum are now modeled per lot. Still pilot-scoped; the rest of the market
retains the blind spots above until the engine is generalized (needs each
cell's utility data + a slope DEM).
