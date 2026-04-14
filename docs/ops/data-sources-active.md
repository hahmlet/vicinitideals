# Active Data Sources

Last updated: 2026-04-12

Active sources powering parcel seeding, classification, enrichment, and screening. For the full historical inventory (including evaluated-and-rejected sources), see [data-sources-inventory.md](data-sources-inventory.md).

---

## Source Types — Scraping vs. Caching

There are two fundamentally different kinds of data sources in this system:

| Type | What it means | How it updates | Dashboard |
|---|---|---|---|
| **Listing scraper** | Hits a property listing website (Crexi, LoopNet) to pull for-sale listings | Automated Celery task, daily | Settings → Scraping Services |
| **Cached GIS layer** | Downloads a full GIS dataset from a government/public API and stores it as a local GeoJSON file | Quarterly, user/admin-triggered or cron | Settings → Data Sources |
| **On-demand enrichment** | Calls a county assessor or city GIS API per-parcel for owner/zoning detail | Celery beat drip queue (Prime/Target parcels only) | — |

**Crexi is the only active listing scraper.** LoopNet is intentionally disabled. Every other source in this document is a cached GIS layer or an on-demand enrichment scraper — not a listing scraper.

---

## Listing Scrapers

### Crexi
- **Status:** Active
- **What it does:** Scrapes commercial property listings for sale in the Portland metro area. Listings are ingested as `ScrapedListing` records and auto-linked to `Parcel` records by address/APN match.
- **Schedule:** Daily at 06:00 UTC (Celery beat)
- **Proxy:** Proxyon residential proxy (required — Crexi blocks datacenter IPs)
- **Files:** `vicinitideals/scrapers/crexi.py`, `vicinitideals/tasks/scraper.py`

### LoopNet
- **Status:** Intentionally disabled
- **Why:** LoopNet aggressively detects and blocks scrapers. Residential proxy insufficient. Disabled pending a different acquisition strategy (partner data feed or licensed API).
- **Files:** `vicinitideals/scrapers/loopnet.py` (disabled)

---

## Parcel Universe — Seeding

### Metro RLIS Taxlots — Multnomah + Clackamas
- **Slug:** `tax_lots_metro_rlis`
- **Source:** Metro Regional Land Information System (RLIS), Portland, OR
- **URL:** `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/0`
- **Direct download:** `https://drcmetro.maps.arcgis.com/sharing/rest/content/items/3949bc39e980444384312a8c4d7bdb08/data` (quarterly delta ZIP, ~1.37 GB)
- **Filter:** `COUNTY IN ('M', 'C')` → ~452k features after county filter
- **Update cadence:** Quarterly. Metro publishes a delta ZIP on the 1st of Jan/Apr/Jul/Oct containing all layers updated during the prior quarter.
- **Update method:** `tools/gis_cache/rlis_delta.py` — uses HTTP Range requests to extract only `TAXLOTS/taxlots_public.shp+dbf` (~265 MB) without downloading the full 1.37 GB ZIP. After writing the cache, dispatches `rlis_quarterly_refresh_task` to Celery.
- **Proxy:** None — drcmetro.maps.arcgis.com is public, direct download
- **Fields used:** TLID (APN), SITEADDR, SITECITY, SITEZIP, JURIS_CITY, COUNTY, LANDVAL, BLDGVAL, ASSESSVAL, BLDGSQFT, GIS_ACRES, YEARBUILT, TAXCODE, LANDUSE, STATECLASS, SALEPRICE, SALEDATE, ORTAXLOT, PRIMACCNUM, ALTACCNUM
- **What it lacks:** Owner name/mailing address (privacy-stripped in public layer)
- **Delta ZIP also contains:** TAXLOTS/taxlot_change.dbf (ADDCHANGE ∈ {CHANGE, ADDED, DELETED} — Q1-2026: 126k CHANGE, 1,647 ADDED, 452 DELETED), TAXLOTS/master_address.dbf (902k addresses with TLID linkage), LAND/zoning.shp (Metro-wide comp plan / zoning context)
- **DB pipeline:** `rlis_quarterly_refresh_task` → purges DELETED TLIDs, re-seeds from refreshed GeoJSON, classifies new parcels
- **Files:** `tools/gis_cache/rlis_delta.py`, `tools/gis_cache/oregon_statewide_sources.py`, `vicinitideals/tasks/parcel_seed.py`

### Oregon Address Points — Multnomah + Clackamas
- **Slug:** `address_points_or`
- **Source:** Oregon 911 / NENA NG911 statewide address database
- **URL:** `https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Address_Points/FeatureServer/0`
- **Filter:** `County IN ('Multnomah County', 'Clackamas County')` → 462,110 features
- **Update cadence:** Quarterly
- **Status:** Downloaded, not actively seeding. PARCEL_ID is 0% populated by Portland/Clackamas 911 agencies (voluntary NENA field — not submitted). Cannot be used as a parcel join key. Retained for address-level enrichment against existing parcel records.
- **Files:** `tools/gis_cache/oregon_statewide_sources.py`, `vicinitideals/tasks/parcel_seed.py`

---

## Jurisdiction Routing + Boundary Screening

All quarterly, direct (no proxy), cached as GeoJSON.

| Slug | Source | URL / Service | Purpose |
|---|---|---|---|
| `city_limits_or` | ODOT | MapServer/220 at gis.odot.state.or.us | Point-in-polygon jurisdiction routing for listings without a clean city |
| `county_boundaries_or` | BLM / Oregon GEO | services1.arcgis.com/KbxwQRRfWyEYLgp4 | County routing fallback for unincorporated addresses |
| `urban_growth_boundaries_or` | Metro / Oregon GEO | services8.arcgis.com UGB_2022 | Urban/rural gate — parcels outside UGB are Out of Market |

---

## Incentive Eligibility Screening

All quarterly, direct, cached as GeoJSON.

| Slug | Source | URL / Service | Purpose |
|---|---|---|---|
| `enterprise_zones_or` | Business Oregon / Oregon GEO | services8.arcgis.com EnterpriseZones2023 | Oregon Enterprise Zone designation |
| `opportunity_zones_or` | U.S. Treasury / ESRI | services.arcgis.com/VTyQ9soqVukalItT | Federal Opportunity Zone designation (filter: STATE='41') |
| `nmtc_qualified_tracts_or` | CDFI Fund / ESRI | services6.arcgis.com NMTC_Qualified_Tracts_2020 | New Markets Tax Credit eligible census tracts (filter: STATE_FIPS='41') |

---

## Environmental Screening

All quarterly, direct, cached as GeoJSON.

| Slug | Source | Purpose |
|---|---|---|
| `wetlands_lwi_or` | Oregon GEO (services8) | Oregon Local Wetland Inventories — locally-mapped wetlands, more detailed than NWI |
| `wetlands_nwi_or` | Oregon GEO (services8) | USFWS National Wetland Inventory — federal baseline |
| `wetlands_more_or` | Oregon GEO (services8) | Additional Oregon wetland data — additive third layer |
| `title13_hca_or` | Metro / Oregon GEO | Title 13 Habitat Conservation Areas — regional habitat protection overlay |

All three wetland layers serve the same GeoJSON endpoint (`Oregon_Wetlands_NWI/FeatureServer/0-2`) — layers 0, 1, 2 respectively. Combined at enrichment time via spatial intersection.

---

## Reference / Context Layers

All quarterly, direct, cached as GeoJSON.

| Slug | Source | Purpose |
|---|---|---|
| `building_footprints_or` | Oregon GEO (services8) | Structural screening — confirms existing building + footprint |
| `oregon_zip_reference` | Oregon GEO (services8) | ZIP code polygons for postal routing |
| `census_block_groups_2020_or` | Oregon GEO (services8) | Demographic context, NMTC/OZ joins |
| `census_tracts_2020_or` | Oregon GEO (services8) | Demographic context |

---

## Street Classifications

All quarterly, direct.

| Slug | Source | Notes |
|---|---|---|
| `street_functional_class_state_or` | ODOT MapServer/171 | ODOT-owned roads (state highways). `NEW_FC_TYP` + `NEW_FC_CD` + `JRSDCT` |
| `street_functional_class_nonstate_or` | ODOT MapServer/173 | County/city/other roads. Together with state layer = complete Mult+Clack coverage |

Both are MapServer with query support (`source_type="arcgis-mapserver"`).

---

## City GIS Layers — Multnomah County Cities

All quarterly, direct (no proxy). Cached as GeoJSON.

### Gresham (`gis.greshamoregon.gov/ext/rest/services/GME/`)

| Slug | Layer | Purpose |
|---|---|---|
| `city_limits` | Base_Data/MapServer/0 | Jurisdiction boundary |
| `neighborhoods` | Base_Data/MapServer/2 | Neighborhood routing |
| `tax_lots_east_county` | Base_Data/MapServer/9 | East county taxlots — full RLIS dataset with ZONE + owner fields. Covers Portland, Troutdale, Fairview, Wood Village, unincorporated Multnomah (not Gresham city parcels) |
| `addresses_all` | Base_Data/MapServer/10 | Address-level routing |
| `multifamily_housing` | Base_Data/MapServer/12 | Multifamily housing inventory |
| Planning overlays (5) | Planning/MapServer/0-12 | Regulatory overlays (Pleasant Valley, Kelley Creek, Springwater, Rockwood, design districts) |
| `street_classifications` | Planning/MapServer/8 | Street designations |
| Environmental (10) | Environmental/MapServer/* | Streams, wetlands, open space, historic, natural resource overlays, soils, groundwater |
| Transportation (4) | Transportation/MapServer/* | Bike routes, MAX stops, bus stops/lines |
| Incentive zones (5) | Incentives/MapServer/* | Enterprise zone, New Industries Grant, Rockwood URD, Strategic Investment Zone, Vertical Housing |

### Fairview (`services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/`)

| Slug | Layer | Purpose |
|---|---|---|
| `natural_resources_fairview` | `Natural_Resource_Layer/FeatureServer/0` | Protection areas (riparian buffers 35'/40'/55'/80', Fairview Lake, upland habitat, wetlands) — `TYPE` field |
| `fairview_lake_35ft_buffer` | `Fairview_Lake_35ft/FeatureServer/0` | Fairview Lake 35' buffer (additive) |
| `fairview_lake_50ft_buffer` | `Fairview_Lake_50ft/FeatureServer/0` | Fairview Lake 50' buffer (additive) |
| `enterprise_zone_fairview` | `Enterprise_Zones_201806_FVR/FeatureServer/6` | Columbia Cascade Enterprise Zone (~34 parcels) |
| `streets_jurisdiction_fairview` | `Streets___Jurisdiction/FeatureServer/28` | Street ownership routing |
| `overlay_districts_fairview` | `Overlay_Districts20230406/FeatureServer/0` | Airport Overlay, Storefront District, Four Corners, R/SFLD |

**Note:** Fairview zoning is PDF-only — `zoning_lookup_url` on parcels points to `https://fairvieworegon.gov/DocumentCenter/View/3458/Zoning-Map-PDF`. See `ZONING_PDF_JURISDICTIONS` in `oregon_statewide_sources.py`. Zone painter at `tools/zone_painter/` for manual `zoning_code` assignment.

### Wood Village (`services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/`)

| Slug | Layer | Purpose |
|---|---|---|
| `zoning_wood_village` | `Zoning/FeatureServer/9` | Zoning — `Labeling` (code), `Name` (description) |
| `taxlots_wood_village` | `WV_Taxlots24/FeatureServer/0` | RLIS-compatible taxlots with assessed values + geometry |
| `city_limits_wood_village` | `Wood_Village_City_Limits_Boundary/FeatureServer/34` | Jurisdiction boundary |

### Troutdale (`maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer/`)

| Slug | Layer | Purpose |
|---|---|---|
| `zoning_troutdale` | MapServer/69 | Zoning — `ZONE` field (R10, GI, etc.) |
| `streets_troutdale` | MapServer/43 | Street centerlines — `CLASS`, `OWNER`, `CONDTN` |

Source type: `arcgis-mapserver` (MapServer with query support).

---

## City GIS Layers — Clackamas County Cities

All quarterly, direct (no proxy). Cached as GeoJSON. All confirmed via ArcGIS REST API inspection April 2026.

### Happy Valley (`services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/`)

ArcGIS Online, org ID `fuVQ9NIPGnPhCBXp`.

| Slug | Layer | Purpose |
|---|---|---|
| `zoning_happy_valley` | `Zoning_public_view/FeatureServer/0` | Zoning — `ZONE` (code), `ZOVER` (overlay), `ORDINANCE`, `DATE_` |
| `city_limits_happy_valley` | `City_Limits/FeatureServer/0` | Jurisdiction boundary |
| `natural_resources_happy_valley` | `Natural_Resources_Overlay/FeatureServer/0` | Natural resource overlay zones |

### Milwaukie (`services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/`)

ArcGIS Online, org ID `8e6aYcxt8yhvXvO9`. All layers in the `COM_Zoning_SDE` FeatureServer.

| Slug | Layer | Purpose |
|---|---|---|
| `zoning_milwaukie` | `FeatureServer/11` | Zoning — `ZONE` field (MUTSA, BI, GMU, C-CS, DMU, C-G, NMU, SMU, OS, M, NME, R-MD, R-HD) |
| `city_limits_milwaukie` | `FeatureServer/0` | Jurisdiction boundary |
| `taxlots_milwaukie` | `FeatureServer/1` | Taxlots (reference) |
| `wetlands_milwaukie` | `FeatureServer/5` | Wetland inventory |
| `vegetated_corridors_milwaukie` | `FeatureServer/6` | Vegetated corridors environmental overlay |

### Oregon City (`maps.orcity.org/arcgis/rest/services/`)

ArcGIS Enterprise v11.5. All MapServer with query support (`source_type="arcgis-mapserver"`).

| Slug | Service / Layer | Purpose |
|---|---|---|
| `zoning_oregon_city` | `LandUseAndPlanning_PUBLIC/MapServer/62` | Zoning polygons. Same service also has comp plan (57), enterprise zones (3, 85), opportunity zones (73), urban renewal district (33), historic districts (31-32), parking overlays |
| `city_limits_oregon_city` | `Annexations/MapServer/0` | Jurisdiction boundary |
| `taxlots_oregon_city` | `Taxlots_PUBLIC/MapServer/0` | Taxlots (reference) |
| `hazards_flood_oregon_city` | `HazardsAndFloodInfo_PUBLIC/MapServer/3` | 100yr floodplain. Same service: floodway (2), 500yr (4), landslides (5-8), geologic hazards (9-11), slopes (12), riparian buffer (16, 20) |
| `urban_renewal_oregon_city` | `LandUseAndPlanning_PUBLIC/MapServer/33` | Urban Renewal District boundary |

### Gladstone (`maps.orcity.org/arcgis/rest/services/GLADSTONE/`)

Hosted on Oregon City's ArcGIS Enterprise in the GLADSTONE folder.

| Slug | Service / Layer | Purpose |
|---|---|---|
| `zoning_gladstone` | `Gladstone_LandUseAndPlanning/MapServer/7` | Zoning. Same service: comp plan (6), urban renewal (5), analysis centers (4), multifamily housing (3), vacant lands (2) |
| `city_limits_gladstone` | `Gladstone_CityLimits/MapServer/0` | Jurisdiction boundary |
| `taxlots_gladstone` | `Gladstone_Taxlots/MapServer/0` | Taxlots (reference) |
| `hazards_flood_gladstone` | `Gladstone_HazardsAndFloodInfo/MapServer/0` | FEMA floodplain, landslide, geologic hazard layers |
| `natural_resources_gladstone` | `Gladstone_WaterAndNaturalResources/MapServer/0` | Natural resources / water features |

### Lake Oswego (`maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/`)

ArcGIS Enterprise v12. All layers in the `Layers_Geocortex` MapServer service.

| Slug | Layer | Purpose |
|---|---|---|
| `zoning_lake_oswego` | MapServer/68 | Zoning. Same service: comp plan (69), design districts (58), lake grove village center (59), neighborhood overlays (60), SW overlay (61), Willamette River Greenway mgmt district (62) |
| `city_limits_lake_oswego` | MapServer/1 | Jurisdiction boundary |
| `sensitive_lands_lake_oswego` | MapServer/57 | Sensitive Lands polygons. Same service: streams (55), delineations (56), wetland (200), 50ft riparian protection area (308) |

### West Linn (`geo.westlinnoregon.gov/server/rest/services/Operational/`)

ArcGIS Enterprise v10.9.

| Slug | Service / Layer | Purpose |
|---|---|---|
| `zoning_west_linn` | `ZoningComPlan/MapServer/8` | Zoning polygon. Layer 10 = Comprehensive Plan. Max 2,000 records |
| `city_limits_west_linn` | `ZoningComPlan/MapServer/0` | Jurisdiction boundary |
| `wetlands_west_linn` | `WetlandInventory/MapServer/1` | Wetland inventory |

### Tualatin (`tualgis.ci.tualatin.or.us/server/rest/services/`)

ArcGIS Enterprise v10.91. Straddles Clackamas + Washington County.

| Slug | Service / Layer | Purpose |
|---|---|---|
| `zoning_tualatin` | `LandusePlanningExplorer/MapServer/6` | Planning Districts — zone code field: `PLANDIST.CZONE` (5-char, e.g. CO, RH, IN). Zone name: `PLANDIST.ZONE_NAME`. Max 1,000 records |
| `city_limits_tualatin` | `TualatinBoundaries/MapServer/0` | Jurisdiction boundary |
| `environmental_tualatin` | `EnvironmentalExplorer/MapServer/24` | Wetlands. Same service: 100yr floodplain (9), floodway (11), natural resources protection overlay (23), wetlands protection district (25), 50ft stream buffer (26), streams (18), slopes ≥25% (3) |

### Wilsonville (`gis.wilsonvillemaps.com/server/rest/services/`)

ArcGIS Enterprise v11.5. Straddles Clackamas + Washington County.

| Slug | Service / Layer | Purpose |
|---|---|---|
| `zoning_wilsonville` | `Map___WilsonvilleMaps_MIL1/FeatureServer/40` | Zoning — `ZONE_CODE` field (OTR, PDC, PDI, R, V, Future Development categories) |
| `city_limits_wilsonville` | `Map___WilsonvilleMaps_MIL1/FeatureServer/2` | Jurisdiction boundary |
| `taxlots_wilsonville` | `Map___WilsonvilleMaps_MIL1/FeatureServer/11` | Taxlots covering both Clackamas and Washington County portions |
| `environmental_wilsonville` | `Map___NaturalResources/FeatureServer/1099` | Significant Wetlands. Same service: upland wildlife habitat (1080), non-significant wetlands (1090), FEMA 100yr floodplain (1107), rivers (1040), streams (1050-1060) |
| `sroz_wilsonville` | `Map___WilsonvilleMaps_MIL1/FeatureServer/60` | SROZ — Significant Resource Overlay Zone. Layer 70 = SROZ Impact Area |

### Canby / Johnson City
- **Status:** Planned — no queryable GIS confirmed as of April 2026
- **Canby contact:** Planning Dept 503-266-7001 for direct shapefile/REST endpoint access
- **Johnson City:** Small jurisdiction, likely covered by Clackamas County data

---

## On-Demand County Enrichment Scrapers

Not cached as GeoJSON. Called per-parcel by the enrichment queue for Prime/Target parcels only. These are HTTP scrapers against county assessor websites — they require no proxy (direct county servers).

| Scraper | Coverage | What it retrieves |
|---|---|---|
| `vicinitideals/scrapers/clackamas.py` | Clackamas County | Owner name, mailing address, assessed values, zoning, legal description |
| `vicinitideals/scrapers/portlandmaps.py` | Multnomah County / Portland | Owner name, mailing address, assessed values, zoning, permit history |
| `vicinitideals/scrapers/oregoncity.py` | Oregon City | Owner name, mailing address, assessed values, zoning |

- **Schedule:** Celery beat every 10 minutes, 20 parcels/run (`enrich_prime_target_parcels`)
- **Scope:** Prime and Target priority bucket parcels only — not Contextual/Out of Market
- **File:** `vicinitideals/tasks/parcel_seed.py`

---

## Utilities

### Oregon Address Geocoder (Navigator)
- **URL:** `https://navigator.state.or.us/arcgis/rest/services/Locators/OregonAddress/GeocodeServer`
- **Why:** State-maintained, no API key required, handles Oregon address formats including range addresses. Used for listings that arrive without lat/lng coordinates.
- **Files:** `vicinitideals/utils/geocoder.py` (`geocode_oregon_address()`)

---

## Caching Infrastructure

### How Caches Are Refreshed

All GIS layers are cached as GeoJSON files at `/app/data/gis_cache/{group}/{slug}.geojson`.

| Scenario | Tool | Command |
|---|---|---|
| City GIS layers (all groups) | `tools/gis_cache/cache_layers.py` | `python cache_layers.py` or `--group gresham` etc. |
| RLIS taxlots (quarterly delta) | `tools/gis_cache/rlis_delta.py` | `python rlis_delta.py` |
| RLIS stats only (no write) | `tools/gis_cache/rlis_delta.py` | `python rlis_delta.py --stats-only` |
| Inspect RLIS ZIP contents | `tools/gis_cache/inspect_rlis_delta.py` | `python inspect_rlis_delta.py` |

All downloads are direct (no proxy). Proxy is only used for Crexi scraping.

### Refresh Schedule

Everything is quarterly, aligned to Jan/Apr/Jul/Oct. Cron on VM 114 (`docker exec re-modeling-api`):

```
# RLIS delta (1st of each quarter, 02:00 UTC)
0 2 1 1,4,7,10 * docker exec re-modeling-api python /tmp/rlis_delta.py >> /var/log/rlis_delta.log 2>&1

# City GIS layers (same day, 03:00 UTC — after RLIS)
0 3 1 1,4,7,10 * docker exec re-modeling-api python /app/tools/gis_cache/cache_layers.py >> /var/log/cache_layers.log 2>&1
```

After `rlis_delta.py` completes, it automatically dispatches `rlis_quarterly_refresh_task` to Celery (via Redis broker) which purges deleted parcels, re-seeds from the refreshed GeoJSON, and classifies new parcels.

### Admin Endpoints (manual trigger)

All require settings-owner auth cookie.

| Endpoint | What it does |
|---|---|
| `POST /ui/admin/rlis-refresh` | Dispatch full quarterly RLIS DB refresh task (assumes cache already refreshed) |
| `POST /ui/admin/seed-rlis` | Re-seed parcels from cached taxlot GeoJSON |
| `POST /ui/admin/classify-parcels` | Classify unclassified parcels |

### Manifest

`/app/data/gis_cache/manifest.json` — per-layer record of `cached_at`, `feature_count`, `size_bytes`, `sha256`, `next_refresh_due_at`. The Data Sources settings page reads this to show Last Pull timestamps and the ⚠ Review flag.
