# GIS Cache

Local, generated GIS cache for Gresham overlays plus the first slice of Oregon statewide screening layers.

## Refresh

From `re-modeling/`:

```powershell
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/cache_layers.py
```

Useful filters:

```powershell
# Show all configured sources, including planned/manual layers
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/cache_layers.py --list

# Show refresh status (fresh / due / missing / planned) from the current manifest
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/cache_layers.py --status

# Cache only Oregon statewide layers
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/cache_layers.py --group oregon

# Cache selected layers
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/cache_layers.py --only zoning_or_statewide opportunity_zones_or

# Crawl a complete ArcGIS REST directory catalog (services, layers, metadata)
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/crawl_arcgis_directory.py --services-root https://navigator.state.or.us/arcgis/rest/services

# Crawl REST directory + enrich catalog with SDK page references and links
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gis_cache/crawl_arcgis_directory.py --services-root https://navigator.state.or.us/arcgis/rest/services --include-sdk

```

## Contents

- `gresham/` — cached Gresham ArcGIS layers (planning, environmental, transportation, incentives, parcel boundaries, addresses)
- `oregon/` — statewide Oregon framework layers such as zoning, UGB, city/county boundaries, wetlands, building footprints, and address points
- `external/` — Oregon-scoped external eligibility layers such as:
  - Opportunity Zones
  - New Markets Tax Credit qualified tracts
- `_raw/` — captured source metadata JSON per layer for provenance and reproducibility
- `_raw/oregon/navigator_services_catalog.json` — crawler output with discovered folders/services/layers from the Oregon ArcGIS REST directory
- `_raw/oregon/navigator_services_catalog.md` — compact markdown summary for quick review and handoff
- `sdk_pages` in JSON — SDK reference pages discovered from the ArcGIS SDK index
- `sdk_links` in JSON — best-effort links from SDK pages to crawled services/layers
- `unmatched_sdk_pages` in JSON — SDK pages kept as global references when no catalog match is found
- `manifest.json` — generated metadata summary (feature counts, sizes, source URLs, timestamps, checksums, and source edit metadata)

## Notes

- The cache files are intentionally ignored from git via `.gitignore`.
- This is still a local working cache, but the registry now includes planned statewide sources for USDA rural designation, transit parking-relief eligibility, and the additive flood family.
- `Tax Lots (East County)` provides the Gresham parcel boundaries cache.
- Statewide source definitions now live in `tools/gis_cache/oregon_statewide_sources.py`.
- The previous endpoint validation harness is archived at `tools/gis_cache/archive/validate_arcgis_endpoints.py` and intentionally disabled to avoid recurring sample artifact generation.
