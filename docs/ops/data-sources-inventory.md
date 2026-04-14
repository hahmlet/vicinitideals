# Data Sources Inventory

Last updated: 2026-04-11

Full historical record of every source evaluated. Status: **active**, **downloaded-limited**, **rejected**, or **planned**.

For currently active sources and their field mappings, see [data-sources-active.md](data-sources-active.md).

---

## Metro RLIS Taxlots
- **Status:** Active — primary parcel seed
- **URL:** `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/0`
- **Why active:** Only single public FeatureServer covering all of Multnomah + Clackamas with polygon geometry AND assessed values. 645k tri-county; 430k after M+C filter. Full county coverage confirmed (Sandy, Molalla, Estacada, Canby all present in Clackamas records). Monthly refresh.
- **What it lacks:** Owner name/mailing address (privacy-stripped).

## Oregon Address Points (services8.arcgis.com)
- **Status:** Downloaded — limited use
- **URL:** `https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Address_Points/FeatureServer/0`
- **Why limited:** PARCEL_ID field is 0% populated by Multnomah and Clackamas 911 agencies. Field exists in the NENA NG911 schema but submission is voluntary — Portland and Clackamas did not submit parcel linkage data. Cannot be used for parcel seeding (every record skips with no APN). Retained for potential address enrichment against existing records matched by street address.
- **Downloaded:** 462,110 features, 497 MB at `data/gis_cache/oregon/address_points_or.geojson`

## services8.arcgis.com (Oregon DLCD / GEO)
- **Status:** Partially active — framework layers only
- **Server:** Oregon Department of Land Conservation and Development / Oregon GEO
- **Active layers:** Building footprints, ZIP reference, Census blocks/tracts, City limits (via ODOT), County boundaries, UGB, Enterprise zones, Wetlands (3 layers)
- **Rejected layers:**
  - `zoning_or_statewide` — QA'd against Gresham: `localZCode` completely empty for all Gresham features. `orZCode` only produces 2 coarse values (MURMH, Res.) across 302 features. Designed for statewide comparative analysis, not local zoning decisions. Disabled.
  - `comp_plan_designations_or` — Same DLCD source, not independently evaluated. Disabled alongside zoning layer.

## Oregon Navigator (navigator.state.or.us)
- **Status:** Rejected as data source; geocoder retained
- **Assessment:** [navigator_services_catalog.md](../../data/gis_cache/_raw/oregon/navigator_services_catalog.md)
- **Finding:** 19 services across 4 folders. Every service is MapServer, GeocodeServer, ImageServer, or GeometryServer — zero FeatureServers. Nothing bulk-queryable. `Cadastral_PLSS` is the township/range/section survey grid, not taxlots.
- **Retained:** `Locators/OregonAddress` GeocodeServer — state-maintained address locator, no API key. Wired into `vicinitideals/utils/geocoder.py`.
- **Registered for future tooling (enabled=False):** Bio_Wetlands (23 layers), Haz_GeneralMap (4 layers), Hydro_GeneralMap (13 layers) — all MapServer visualization-only pending export tooling.

## ODF TaxlotsDisplay (gis.odf.oregon.gov)
- **Status:** Rejected
- **URL:** `https://gis.odf.oregon.gov/ags1/rest/services/WebMercator/TaxlotsDisplay/MapServer`
- **Finding:** 36 county layers (layer 2 = Clackamas, layer 25 = Multnomah). Has polygon geometry + owner name + mailing address. Returns HTTP 200. However: MapServer query endpoint returns "Requested operation is not supported by this service" — bulk export not possible. Visualization-only.

## OR_Cadastral_WFL1 (services8.arcgis.com)
- **Status:** Rejected
- **Finding:** Not actual parcel data. This layer is a county participation tracker for Oregon's cadastral data submission program — it shows which counties have submitted data to the state, not the parcel polygons themselves.

## Oregon ORMAP (ormap.net / data.oregon.gov)
- **Status:** Rejected
- **Finding:** ORMAP is a statewide parcel map viewer. The actual assessed values, owner data, and zoning stay with individual county assessors and are not centrally aggregated in any queryable public layer. The statewide taxlot geometry in ORMAP is the same data as ODF TaxlotsDisplay.

## Oregon GEOHub (geohub.oregon.gov)
- **Status:** Searched — nothing better than RLIS found
- **Finding:** Replaced the Oregon Spatial Data Library. Searched for taxlot, parcel, cadastral, ORMAP. Found RLIS taxlots as the best result. No statewide layer combines polygon + owner + assessed value + zoning.

## Oregon Explorer (ims.oregonexplorer.info / maps.oregonexplorer.info)
- **Status:** Inaccessible
- **Finding:** Both servers return authentication errors (ERR_INVALID_AUTH_CREDENTIALS). Likely requires institutional credentials.

## Portland BDS_Property (portlandmaps.com)
- **Status:** Found — not yet added to registry
- **URL:** `https://www.portlandmaps.com/arcgis/rest/services/Public/BDS_Property/FeatureServer/0`
- **Finding:** 345,353 records, Portland city limits only. Has polygon geometry, PROPERTY_ID_MULTNOMAH_COUNTY (APN), OWNER_NAME, ZONE (zoning code), LEGAL_DESCRIPTION, AREA_SQ_FT. FeatureServer with advanced query support. Covers Portland city only — not full Multnomah County.
- **Next step:** Candidate for supplemental zoning layer for Portland city parcels (RLIS has no zoning). Not yet registered.

## Clackamas County Taxlots (services3.arcgis.com/CCGISWebService)
- **Status:** Superseded by RLIS
- **URL:** `https://services3.arcgis.com/I2eWXOndpF9m8oKC/arcgis/rest/services/Taxlots/FeatureServer/0`
- **Finding:** 163,507 records, FeatureServer, advanced query supported. But only 7 fields: PARCEL_NUMBER, TLNO, SITUS_CITY, SITUS_ZIP, SITUS, TAXCODE, OBJECTID. No owner, no assessed value, no geometry details beyond polygon. RLIS provides strictly more data for the same geography. Registered as superseded.

## Metro RLIS Taxlots with Right of Way
- **Status:** Not used
- **URL:** `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_with_Right_of_Way_Public/FeatureServer`
- **Finding:** Same as RLIS taxlots but includes ROW features (roads, rivers, rail). Not useful for parcel seeding — ROW parcels are not developable.

## Oregon Department of Revenue — SLIS Public (maps.dsl.state.or.us)
- **Status:** Rejected
- **Finding:** State Land Inventory System tracks Oregon state agency land ownership specifically. Not a comprehensive county assessor dataset. Described as "not normalized" with known gaps. Does not include public rights-of-way. Not useful for our parcel universe.

## gis.clackamas.us / mapcenter.clackamas.us
- **Status:** Inaccessible
- **Finding:** Both Clackamas County GIS server addresses returned 404 or connection failure. Superseded by RLIS anyway.

## Gresham GIS (gis.greshamoregon.gov)
- **Status:** Active — full suite cached
- **Notable finding:** `tax_lots_east_county` (Base_Data/MapServer/9) is the full RLIS dataset with ZONE and owner fields intact — richer than the public RLIS FeatureServer. Covers Portland, Troutdale, Fairview, Wood Village, and unincorporated Multnomah. Does NOT cover Gresham city parcels.
- **Gresham City Zoning** (Planning/MapServer layer 4, "City Zoning") — 284 features, 44 distinct local zone codes. QA confirms this is the authoritative local zoning source for Gresham. Not yet added to registry.

## Oregon Statewide Zoning QA
- **Finding:** `localZCode` completely empty for all Gresham features in the state layer. `orZCode` has only 2 values (MURMH, Res.) for all of Gresham — coarse generalized classification. Gresham's own Planning/MapServer layer 4 has 44 distinct zone codes. State layer confirmed as a DLCD comparative overlay, not suitable for local zoning decisions.

---

## ODOT Federal Functional Classification (gis.odot.state.or.us)
- **Status:** Active — primary street classification for all of Mult + Clack
- **State roads (layer 171):** `https://gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/MapServer/171`
- **Non-state roads (layer 173):** `https://gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/MapServer/173`
- **Why:** Together these two layers cover every classified public road in Oregon including all of Multnomah + Clackamas — ODOT-owned (state highways) plus county/city/other. `NEW_FC_TYP` field: Interstate / Other Freeway and Expressway / Other Principal Arterial / Minor Arterial / Major Collector / Minor Collector / Local. `NEW_FC_CD` is the single-char FHWA code. `JRSDCT` is road owner/jurisdiction.
- **Coverage:** Statewide — no county filter needed for two-county scope.
- **Note:** Both are MapServer with query support, not FeatureServer. `source_type="arcgis-mapserver"` in registry.

## Fairview (services5.arcgis.com / fairvieworegon.maps.arcgis.com)
- **Status:** Active — full GIS confirmed (previously assumed PDF-only)
- **Org ID:** `3DoY8p7EnUTzaIE7`
- **Zoning:** PDF only — `https://fairvieworegon.gov/DocumentCenter/View/3458`. See `ZONING_PDF_JURISDICTIONS`. Zone painter tool at `tools/zone_painter/` for manual assignment.
- **Natural Resource Protection Areas:** `Natural_Resource_Layer/FeatureServer/0` — `TYPE` field contains all 8 protection area categories (35'/40'/55'/80' riparian buffers, Fairview Lake 50' riparian buffer, platted protected areas, upland habitat, wetlands). Treated identically to statewide wetland layers — spatial intersection at seed time.
- **Fairview Lake buffers:** `Fairview_Lake_35ft/FeatureServer` + `Fairview_Lake_50ft/FeatureServer` — additive to natural resource layer.
- **Enterprise Zone:** `Enterprise_Zones_201806_FVR/FeatureServer/6` — Columbia Cascade Enterprise Zone, ~34 parcels. Supplement to statewide `enterprise_zones_or` layer.
- **Streets:** `Streets___Jurisdiction/FeatureServer/28` — `OWNER` field: City of Fairview / Gresham / Multnomah County / ODOT / Private. Jurisdiction routing layer.
- **Overlay Districts:** `Overlay_Districts20230406/FeatureServer/0` — Airport Overlay, Storefront District (TCC), Four Corners Area (VMU), R/SFLD.
- **Zone codes (20):** AH, CC, GI, LI, R/SFLD, RM/TOZ, R-6, R-7.5, R-10, R/CSP, RM, R/MH, TCC, VA, VC, FLX, VMU, VO, VSF, VTH. Parks have no zone.

## Wood Village (services7.arcgis.com / cowv.maps.arcgis.com)
- **Status:** Active — full GIS confirmed
- **Org ID:** `5Loh3xXKWLd2M7xA` (City of Wood Village ArcGIS Online)
- **Zoning:** `https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/Zoning/FeatureServer/9` — Fields: `Labeling` (zoning code), `Name` (description). Supports advanced queries.
- **Taxlots:** `https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/WV_Taxlots24/FeatureServer/0` — RLIS-compatible fields (TLID, LANDVAL, ASSESSVAL, LANDUSE, STATECLASS, YEARBUILT, BLDGSQFT, SITEADDR). Polygon geometry.
- **City Limits:** `Wood_Village_City_Limits_Boundary/FeatureServer/34`
- **Discovery:** Web app viewer at `cowv.maps.arcgis.com` (app ID `c46aa7527a98431c9110c6b059c647c6`) revealed underlying FeatureServer layer inventory. Previously assumed PDF-only.

## Troutdale (maps.troutdaleoregon.gov)
- **Status:** Active — MapServer with query support
- **Server:** Self-hosted ArcGIS Enterprise at `maps.troutdaleoregon.gov/server`
- **Zoning:** `https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer/69` — Layer: "Urban Planning Area", Field: `ZONE` (R10, GI, etc.). `supportsAdvancedQueries: true`, capabilities: Map,Query,Data.
- **Note:** MapServer (not FeatureServer) but confirmed queryable. Registered with `source_type="arcgis-mapserver"` in registry.
- **Discovery:** Web app at `maps.troutdaleoregon.gov/portal` (app ID `5aa691fdfb9145e2b79902ab7adcfbce`) — service URL found in app config.

## Fairview
- **Status:** PDF only — no queryable GIS
- **Zoning PDF:** `https://fairvieworegon.gov/DocumentCenter/View/3458/Zoning-Map-PDF`
- **Finding:** Fairview has no ArcGIS portal or queryable zoning layer. Only a static PDF zoning map. Parcels in Fairview receive `zoning_lookup_url` pointing to the PDF at seed time. Only jurisdiction in Multnomah + Clackamas without any GIS zoning coverage.

---

## Planned / Registered (enabled=False)

| Slug | Source | Notes |
|---|---|---|
| `zoning_or_statewide` | DLCD (services8.arcgis.com) | Disabled — localZCode unpopulated, orZCode too coarse. See QA above. |
| `comp_plan_designations_or` | DLCD (services8.arcgis.com) | Disabled alongside zoning layer. |
| `usda_ruca_2020_or` | USDA ERS | Manual download — rural designation baseline |
| `public_transit_parking_relief_or` | Derived from GTFS | Climate-Friendly Communities parking relief areas |
| `fema_flood_studies_or` | Oregon FTP | Additive flood evidence — FEMA studies |
| `observed_inundation_or` | Oregon FTP | Additive flood evidence — observed inundation |
| `other_flood_studies_or` | Oregon FTP | Additive flood evidence — other studies |
| `bio_wetlands_or` | Navigator (MapServer) | 23 layers; MapServer only — needs export tooling |
| `haz_general_or` | Navigator (MapServer) | 4 hazard layers; MapServer only |
| `hydro_general_or` | Navigator (MapServer) | 13 hydrology layers; MapServer only |
| `admin_bounds_or_nav` | Navigator (MapServer) | Redundant with active boundary layers |
