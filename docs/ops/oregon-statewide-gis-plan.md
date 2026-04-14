# Oregon Statewide GIS Integration Plan

## Goal

Build a reproducible Oregon GIS stack with **local versioned storage** as the system of record for parcel screening, zoning fallback, incentive eligibility, flood evidence, and environmental review support.

## In Scope

- Building footprints
- Address points
- City and county boundaries
- UGB
- Statewide zoning
- Comprehensive plan designations
- Enterprise zones
- Opportunity Zones
- NMTC qualified tracts
- USDA rural designation / RUCA baseline
- Public-transit parking-relief eligibility
- Wetlands
- Flood evidence family
- Landslide / debris-flow hazards

## Architecture

### 1. Local storage first
- Keep raw source artifacts locally for reproducibility.
- Normalize large statewide layers into `GeoParquet`.
- Export lighter `GeoJSON` where needed for preview tools.
- Track checksums, feature counts, timestamps, and provenance in `manifest.json`.

### 2. Source precedence
1. City GIS
2. County GIS
3. Statewide zoning fallback
4. Manual review

### 3. Flood handling
Treat flood as one evidence family with three distinct sources:
- FEMA Flood Insurance Studies
- Observed Inundation
- Other Flood Studies

These are **additive**, but not equivalent.

### 4. Transit / parking waiver
If no authoritative statewide waiver polygon exists, derive a local GIS eligibility layer from transit `GTFS` feeds and rule geometry, then version it like any other layer.

## Update Cadence

| Dataset family | Suggested cadence |
|---|---|
| Address points, building footprints, transit-derived layers | Monthly |
| Zoning, comp plan, boundaries, UGB, enterprise zones, Opportunity Zones, NMTC | Quarterly metadata check + annual full refresh |
| Wetlands, flood family, landslide hazards | Quarterly metadata check + semiannual full refresh |
| USDA rural / RUCA | Annual or source-release-driven |

## Implementation slices

### Slice 1
- Add a registry-driven statewide source catalog.
- Extend the local cache builder to support Oregon statewide layers.
- Record raw metadata and checksums in the manifest.

### Slice 2
- Wire the cache into the parcel-screening pipeline.
- Add provenance-aware screening outputs for zoning, flood, and eligibility overlays.

### Slice 3
- Add derived transit parking-relief polygons.
- Add flood-source comparison QA for ambiguity reporting.

## Verification

1. Rebuild a statewide vintage from local artifacts only.
2. Validate statewide zoning fallback on a city with weak/no zoning GIS (for example `Happy Valley`).
3. Confirm parcel outputs preserve per-source provenance for flood and eligibility overlays.
4. Promote only after QA passes on clear / flagged / ambiguous parcels.
