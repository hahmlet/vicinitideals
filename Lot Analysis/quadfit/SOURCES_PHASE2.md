# Phase 2 data sources — overlays, slope, utilities (audited 2026-07-27)

Endpoint audit for the phase 2 overlay/slope/utility build. All endpoints
verified responding on audit date; all ArcGIS layers maxRecordCount=2000 →
paged fetch. Grades: A city-maintained parcel-grade · B regional/federal
fallback adequate · C coarse/partial · X nothing usable locally.

## Availability matrix

| Jurisdiction | Wetlands / Riparian | Flood | Slope / Elevation | Utilities (mains) |
|---|---|---|---|---|
| Portland | **A** Ezone geometry (BPS_Zoning_Code_Layers/117 p, /118 c, /116 v) + wetland inventory (PPD_Flood_and_Natural_Resources/189), streams /187 | **A** PPD /30 SFHA 100-yr, /31 500-yr | **A** PPD /69 steep slopes ≥20% + regional DEM | **A** BES Utilities_Sewer/3; PWB Utilities_Water/8 |
| Gresham | **A** GME/Environmental: streams /0, Title 3 wetlands /15, NRO /11–/14 | **A** GME/Environmental/2 (DFIRM fields) | **A** /7–/9 hillside + geologic risk overlay; contours /3 | **A(geom)** GME/Wastewater/5; GME/Water/1 (no diameter) |
| Troutdale | **B+** Public_Web/City_GIS/57 + /77 Title 3 VECO (RLIS derivative); streams /54 | **B** panels index only → FEMA NFHL | **B** contours only → regional DEM | **A** City_GIS/11 sewer; /135 water |
| Fairview | **A** Natural_Resource_Layer/FeatureServer/0 (TYPE = 35/40/55/80 ft riparian buffers, wetlands, upland) + Fairview_Lake buffers. NOTE: LUWIP layer is land-use, NOT wetlands | **A-** fragmented across 7 misnamed services → prefer NFHL as source of record | **B** contour services → regional DEM | **A** Sewer_Main_Public/7; Water_Lines/2 |
| Wood Village | **X → B** zero local env layers → Metro Title 3/13 + NWI | **X → B** NFHL only | **X → B** regional DEM | **A** Sanitary_Sewer_Main/19; Water_Line/0 |
| MultCo uninc | **B** Metro Title_13_HCA (HCA_VALUE classes), Title_3_Land, Metro Wetlands (aggregates city LWIs) | **B** FEMA NFHL DFIRM_ID='41051C' (eff. 2009-12-18) or Metro Flood_Plains_FEMA | **B** regional DEM; Metro Slope_25/Slope_10 (2009, coarse pre-filter only) | **C** no county layer; Portland/Gresham main proximity proxy; septic indistinguishable |

Key endpoint roots:
- Portland: `https://www.portlandmaps.com/arcgis/rest/services/Public/`
- Gresham: `https://gis.greshamoregon.gov/ext/rest/services/GME/` (root /Utilities token-gated; Wastewater/Water/Stormwater public)
- Troutdale: `https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/`
- Fairview: `https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/`
- Wood Village: `https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/`
- Metro: `https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/<name>/FeatureServer/0`
- FEMA NFHL: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28` (`DFIRM_ID='41051C'`, fields FLD_ZONE, ZONE_SUBTY, SFHA_TF, STATIC_BFE)
- NWI: federal REST unstable (HTTP 500) → AGOL mirror `services8.arcgis.com/8PAo5HGmvRMlF2eU/.../Oregon_Wetlands_NWI/FeatureServer/1` or FWS OR geodatabase zip (965 MB)

## Clackamas County — endpoint audit (2026-09-01)

**This matrix did not exist until 2026-09-01, and its absence was the bug.**
The Clackamas phase-1 build shipped with the line "no overlays for Clackamas"
and nobody went back. The consequence measured on the 2026-09-01 run: across
**70,196 Clackamas lots there is exactly one overlay touch of any kind**, and
2,820 green verdicts — 28% of every green in the corpus — were graded with no
environmental screen at all. A missing overlay does not raise. It grades as
clear land.

The audit below says the data was there the whole time. **Every Clackamas
jurisdiction that produces a green publishes its own environmental geometry**,
most of it parcel-grade and city-maintained. Nothing had to be settled for or
approximated; the layers were simply never wired in.

| Jurisdiction | Greens today | Natural resource / habitat | Flood | Slope |
|---|---|---|---|---|
| Oregon City | 882 | **A** `WaterAndNaturalResources` /2 NROD, /0–1 NROD-HCA, /9 Title 3 WQR overlay, /5 wetlands, /6 riparian, /7–8 vegetated corridor, /10 Willamette Greenway | **A** `HazardsAndFloodInfo_PUBLIC` /3 100-yr, /2 floodway, /4 500-yr | **A** /9 geologic hazard slopes, /12 slope categories, SLIDO landslides /5–8 |
| Milwaukie | 845 | **A** `Habitat_Conservation_Areas`/7 (n=1), `Wetlands`/5 (n=26), `Vegetated_Corridors`/6 (n=61), `Willamette_Greenway`/8 | **A** `Floodplain`/9 (n=173), `COM_FEMA_Hazards`, `Flood_1996` | — regional DEM |
| Clackamas uninc. | 598 | *county-level; `GeoHazard` FeatureServer found, resource layer not yet located* | NFHL 41005C | regional DEM |
| West Linn | 355 | **A** `RiparianCI`/1 (n=10) + /2 water resource area streams (n=585), `WetlandInventory`/1 (n=91) | **A** `FloodManagement`/1 flood management area, /0 1996 flood line | **A** `SteepSlope2014`/0 (n=28) |
| Wilsonville | 140 | **B** `LandUseDataset/Map___NaturalResources` (service confirmed, layer ids not yet enumerated) | NFHL 41005C | regional DEM |
| Happy Valley | 0 (731 review) | **A** `NaturalResourceOZ` | **A** `100yr_Floodplain_FEMA__local_`, `Floodway_FEMA__local_` | **A** `SteepSlopesOZ`, `Slope` |
| Tualatin | 0 (20 review) | **B** `Public/EnvironmentalExplorer` (service confirmed, layers not enumerated) | NFHL 41005C | regional DEM |
| Gladstone | 0 (145 review) | not audited — no greens at stake | NFHL 41005C | regional DEM |

Endpoint roots (all verified responding 2026-09-01):
- Oregon City: `https://maps.orcity.org/arcgis/rest/services/` (93 services; also hosts the `GLADSTONE/` folder)
- Milwaukie: `https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/`
- West Linn: `https://geo.westlinnoregon.gov/server/rest/services/Operational/`
- Wilsonville: `https://gis.wilsonvillemaps.com/server/rest/services/LandUseDataset/`
- Happy Valley: `https://services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/`
- Tualatin: `https://tualgis.ci.tualatin.or.us/server/rest/services/Public/`
- Clackamas County: `https://services3.arcgis.com/I2eWXOndpF9m8oKC/ArcGIS/rest/services/`

**What is NOT settled by this audit, and must not be skipped.** Finding a layer
is not deciding what it does. Every Multnomah overlay in `overlays.yaml` carries
a citation to *how that jurisdiction adopts it* — Wood Village takes Metro
Title 3 by reference in WVDC 430; Troutdale applies the habitat overlay only to
public parks, so it is excluded there rather than carved. The same reading is
owed to each layer above before it becomes a `kill`, a `carve` or a `flag`:
Oregon City's NROD is named in OCMC 17.04.810 as a net-area deduction, which
proves it constrains density but not that it forbids a building on the part it
covers. **Carving a layer nobody has read would be the mirror of the bug this
audit found** — a verdict moved by geometry with no clause behind it.

Two things are already known and cheap:
1. FEMA flood is fixed (2026-09-01). The NFHL filter now names `41005C`
   alongside `41051C`; `jurisdictions: all` finally means what it said, and
   three tests in `tests/test_overlay_coverage.py` pin it against
   `KEEP_COUNTIES`.
2. The regional Metro Title 3 / Title 13 / wetland layers already on disk cover
   the Clackamas UGB and could serve as a fallback — but only where a city has
   nothing of its own, which the matrix above says is **nowhere**. Prefer the
   city layer every time; the regional one is a Wood Village answer.

## Slope/DEM decision

1. DOGAMI pre-computed slope mosaic (3-ft, EPSG:6557): `https://gis.dogami.oregon.gov/arcgis/rest/services/lidar/DIGITAL_TERRAIN_SLOPE_MODEL_MOSAIC/ImageServer` — exportImage/getSamples only, no bulk.
2. **Chosen: USGS 3DEP 1m GeoTIFF tiles** (bulk, scriptable): `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/<proj>/TIFF/USGS_1M_10_x50y503_<proj>.tif`, projects `OR_OLCMetro_2019_A19` / `OR_PortlandMetro_B24`; county ≈ 15–20 tiles ≈ 5–7 GB. Zonal slope stats per lot envelope via rasterio.
3. Metro Slope_10/Slope_25 vector classes: 2009 vintage, pre-filter only.

## Hard gaps (must appear as caveats in every report)

1. Wood Village: no environmental GIS at all — everything regional fallback.
2. Troutdale flood: NFHL 2009 FIRM predates modern lidar; Sandy River edges low-confidence.
3. Unincorporated sewer availability indeterminate from public GIS (septic vs served).
4. Metro Title 13 HCA = 2005-era regional model — coarse wherever it is the operative habitat layer (Troutdale/Fairview upland/Wood Village/uninc).
5. Gresham water mains: geometry only — proximity yes, capacity no.
6. Portland OVRLY letters on zoning polygons ≠ overlay geometry — use BPS 117/118/116 for real ezone boundaries.
