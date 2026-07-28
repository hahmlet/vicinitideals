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
