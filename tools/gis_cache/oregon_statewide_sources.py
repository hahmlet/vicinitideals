from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerSpec:
    slug: str
    label: str
    layer_url: str
    group: str
    where: str = "1=1"
    authority: str = "screening"
    refresh_policy: str = "manual"
    source_type: str = "arcgis"
    enabled: bool = True
    notes: str | None = None
    fetch_geometry: bool = True   # Set False for point layers where lat/lon attrs are sufficient


GRESHAM_LAYERS: list[LayerSpec] = [
    LayerSpec("city_limits", "City Limits", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/0", "gresham", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("neighborhoods", "Neighborhoods", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/2", "gresham", refresh_policy="quarterly"),
    LayerSpec("waste_haulers", "Waste Haulers", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/3", "gresham", refresh_policy="quarterly"),
    LayerSpec("county_boundaries", "County Boundaries", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/5", "gresham", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("zip_codes", "ZIP Codes", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/7", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("places", "Places", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/8", "gresham", refresh_policy="quarterly"),
    LayerSpec("tax_lots_east_county", "Tax Lots (East County)", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/9", "gresham", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("addresses_all", "Addresses - All", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/10", "gresham", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("other_cities", "Other Cities", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/6", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("multifamily_housing", "Multifamily Housing", "https://gis.greshamoregon.gov/ext/rest/services/GME/Base_Data/MapServer/12", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("pleasant_valley_plan_area", "Pleasant Valley Plan Area", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/0", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("kelley_creek_headwaters_plan_area", "Kelley Creek Headwaters Plan Area", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/1", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("springwater_plan_area", "Springwater Plan Area", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/2", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("rockwood_plan_district", "Rockwood Plan District", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/12", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("design_districts", "Design Districts", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/11", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("street_classifications", "Street Classifications", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/8", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("streams", "Streams", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/0", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("other_waters", "Other Waters", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/1", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("open_space_planning_overlay", "Open Space Planning Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/4", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("historic_cultural_overlay", "Historic and Cultural Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/5", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("gresham_butte_overlay", "Gresham Butte Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/6", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("natural_resource_overlay", "Natural Resource Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/12", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("high_value_resource_area_overlay", "High Value Resource Area Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/11", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("potential_resource_area_overlay", "Potential Resource Area Overlay", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/13", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("uplands", "Uplands", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/14", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("title3_wetlands", "Title 3 Wetlands", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/15", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("significant_trees", "Significant Trees", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/19", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("soils", "Soils", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/17", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("usgs_depth_to_seasonal_high_groundwater", "USGS Depth to Seasonal High Groundwater", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/18", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("downstream_conditions", "Downstream Conditions", "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer/16", "gresham", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("bike_routes", "Bike Routes", "https://gis.greshamoregon.gov/ext/rest/services/GME/Transportation/MapServer/0", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("max_stops", "MAX Stops", "https://gis.greshamoregon.gov/ext/rest/services/GME/Transportation/MapServer/1", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("bus_stops", "Bus Stops", "https://gis.greshamoregon.gov/ext/rest/services/GME/Transportation/MapServer/2", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("bus_lines", "Bus Lines", "https://gis.greshamoregon.gov/ext/rest/services/GME/Transportation/MapServer/3", "gresham", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("enterprise_zone", "Enterprise Zone", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/1", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("new_industries_grant", "New Industries Grant", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/2", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("rockwood_urban_renewal_area", "Rockwood Urban Renewal Area", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/3", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("strategic_investment_zone", "Strategic Investment Zone", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/4", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("vertical_housing_development_zone", "Vertical Housing Development Zone", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/5", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("garage_to_storefront_incentive", "Garage-to-Storefront Incentive", "https://gis.greshamoregon.gov/ext/rest/services/GME/Incentives/MapServer/6", "gresham", authority="screening-regulatory", refresh_policy="quarterly"),
    # Street classifications — Gresham Planning/MapServer/8
    # Already registered above under slug "street_classifications"
    # Base zoning polygons — used for bulk parcel zoning assignment
    LayerSpec("city_zoning", "City Zoning", "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/4", "gresham", authority="authoritative-routing", refresh_policy="quarterly"),
]

FAIRVIEW_LAYERS: list[LayerSpec] = [
    # City of Fairview — ArcGIS Online, org ID 3DoY8p7EnUTzaIE7
    # Zoning PDF only — no FeatureServer; see ZONING_PDF_JURISDICTIONS
    LayerSpec(
        "natural_resources_fairview",
        "Natural Resource Protection Areas (Fairview)",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Natural_Resource_Layer/FeatureServer/0",
        "fairview",
        authority="screening-environmental",
        refresh_policy="quarterly",
        notes="TYPE field contains protection area category: 35'/40'/55'/80' riparian buffers, Fairview Lake 50' riparian buffer, platted protected areas, upland habitat, wetlands. Equivalent to flood/wetland layers — intersect against parcels at seed time.",
    ),
    LayerSpec(
        "fairview_lake_35ft_buffer",
        "Fairview Lake 35ft Natural Resource Buffer",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Fairview_Lake_35ft/FeatureServer/1",
        "fairview",
        authority="screening-environmental",
        refresh_policy="quarterly",
        notes="35' riparian buffer around Fairview Lake specifically. May overlap with natural_resources_fairview — treat as additive evidence.",
    ),
    LayerSpec(
        "fairview_lake_50ft_buffer",
        "Fairview Lake 50ft Riparian Buffer",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Fairview_Lake_50ft/FeatureServer/1",
        "fairview",
        authority="screening-environmental",
        refresh_policy="quarterly",
        notes="50' riparian buffer around Fairview Lake. Additive to natural_resources_fairview.",
    ),
    LayerSpec(
        "enterprise_zone_fairview",
        "Enterprise Zone (Fairview — Columbia Cascade)",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Enterprise_Zones_201806_FVR/FeatureServer/6",
        "fairview",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        notes="Fairview's portion of the Columbia Cascade Enterprise Zone. 34 parcels per city records. Use alongside enterprise_zones_or statewide layer — statewide may already cover this boundary.",
    ),
    LayerSpec(
        "streets_jurisdiction_fairview",
        "Streets by Jurisdiction (Fairview)",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Streets___Jurisdiction/FeatureServer/28",
        "fairview",
        authority="reference-only",
        refresh_policy="quarterly",
        notes="OWNER field: City of Fairview / City of Gresham / Multnomah County / ODOT / Private. Jurisdiction routing for street maintenance. Supplement to ODOT functional class layers.",
    ),
    LayerSpec(
        "overlay_districts_fairview",
        "Overlay Districts (Fairview)",
        "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services/Overlay_Districts20230406/FeatureServer/20",
        "fairview",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        notes="Zoning overlay districts including Airport Overlay, Storefront District (TCC), Four Corners Area (VMU), Res/South Fairview Lake Design Overlay (R/SFLD).",
    ),
]

WOOD_VILLAGE_LAYERS: list[LayerSpec] = [
    # City of Wood Village — ArcGIS Online, org ID 5Loh3xXKWLd2M7xA
    LayerSpec(
        "zoning_wood_village",
        "Zoning Districts (Wood Village)",
        "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/Zoning/FeatureServer/9",
        "wood_village",
        authority="authoritative-zoning",
        refresh_policy="quarterly",
        notes="Fields: Labeling (zoning code), Name (description). Authoritative local zoning for Wood Village.",
    ),
    LayerSpec(
        "taxlots_wood_village",
        "Tax Lots 2024 (Wood Village)",
        "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/WV_Taxlots24/FeatureServer/0",
        "wood_village",
        authority="authoritative-routing",
        refresh_policy="quarterly",
        notes="RLIS-compatible fields: TLID, LANDVAL, BLDGVAL, ASSESSVAL, LANDUSE, STATECLASS, YEARBUILT, BLDGSQFT, SITEADDR. Polygon geometry.",
    ),
    LayerSpec(
        "city_limits_wood_village",
        "City Limits (Wood Village)",
        "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/Wood_Village_City_Limits_Boundary/FeatureServer/34",
        "wood_village",
        authority="authoritative-routing",
        refresh_policy="quarterly",
    ),
]

TROUTDALE_LAYERS: list[LayerSpec] = [
    # City of Troutdale — self-hosted ArcGIS Enterprise at maps.troutdaleoregon.gov
    # MapServer with query support (capabilities: Map,Query,Data; supports JSON/geoJSON/PBF)
    LayerSpec(
        "zoning_troutdale",
        "Zoning Districts (Troutdale)",
        "https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer/74",
        "troutdale",
        authority="authoritative-zoning",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        notes="Layer 69 'Urban Planning Area' — ZONE field contains local zoning codes (R10, GI, etc.). MapServer with query support confirmed.",
    ),
    LayerSpec(
        "streets_troutdale",
        "Streets (Troutdale)",
        "https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer/43",
        "troutdale",
        authority="screening-routing",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        notes="Street centerlines with CLASS field (street designation/classification), OWNER (jurisdiction), CONDTN. Supplement to ODOT functional class for local Troutdale streets.",
    ),
]

HAPPY_VALLEY_LAYERS: list[LayerSpec] = [
    # City of Happy Valley — ArcGIS Online, org ID fuVQ9NIPGnPhCBXp (services5.arcgis.com)
    LayerSpec("zoning_happy_valley", "Zoning (Happy Valley)", "https://services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/Zoning_public_view/FeatureServer/0", "happy_valley", authority="authoritative-zoning", refresh_policy="quarterly", notes="Authoritative 2024 zoning. Fields: ZONE (code, e.g. R-1, C-1), ZOVER (overlay zone), ORDINANCE, DATE_."),
    LayerSpec("city_limits_happy_valley", "City Limits (Happy Valley)", "https://services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/CityBoundaryHVNov2025/FeatureServer/0", "happy_valley", authority="authoritative-routing", refresh_policy="quarterly", notes="Nov 2025 city boundary. Previous versions: CityBoundaryNov2024, CHVNov2024Boundary, City_Limits_1021."),
    LayerSpec("natural_resources_happy_valley", "Natural Resource Overlay (Happy Valley)", "https://services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/NaturalResourceOZ/FeatureServer/1", "happy_valley", authority="screening-environmental", refresh_policy="quarterly", notes="Maximum extent of vegetated corridors — 200ft riparian buffer. Service NROZ contains 3 habitat layers (High/Moderate/Low Value HCA at IDs 0-2); NaturalResourceOZ layer 1 is the primary riparian corridor polygon."),
    LayerSpec("fema_floodplain_happy_valley", "FEMA Floodplain (Happy Valley)", "https://services5.arcgis.com/fuVQ9NIPGnPhCBXp/arcgis/rest/services/LocalFEMAFloodLayer/FeatureServer/0", "happy_valley", authority="screening-environmental", refresh_policy="quarterly", notes="Local FEMA flood zone polygons. Also: 100yr_Floodplain_FEMA__local_, Floodway_FEMA__local_ available as separate services."),
]

MILWAUKIE_LAYERS: list[LayerSpec] = [
    # City of Milwaukie — ArcGIS Online, org ID 8e6aYcxt8yhvXvO9 (services6.arcgis.com)
    # All layers are in the COM_Zoning_SDE FeatureServer service.
    LayerSpec("zoning_milwaukie", "Zoning (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/FeatureServer/11", "milwaukie", authority="authoritative-zoning", refresh_policy="quarterly", notes="Zone code field: ZONE. Values include MUTSA, BI, GMU, C-CS, DMU, C-G, NMU, SMU, OS, M, NME, R-MD, R-HD."),
    LayerSpec("city_limits_milwaukie", "City Limits (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/FeatureServer/0", "milwaukie", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("taxlots_milwaukie", "Taxlots (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/FeatureServer/1", "milwaukie", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("wetlands_milwaukie", "Wetlands (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/FeatureServer/5", "milwaukie", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("vegetated_corridors_milwaukie", "Vegetated Corridors (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_Zoning_SDE/FeatureServer/6", "milwaukie", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("floodplain_milwaukie", "FEMA Floodplain (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_FEMA_Hazards/FeatureServer/0", "milwaukie", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("urban_renewal_milwaukie", "Urban Renewal Area (Milwaukie)", "https://services6.arcgis.com/8e6aYcxt8yhvXvO9/ArcGIS/rest/services/COM_URA/FeatureServer/0", "milwaukie", authority="screening-regulatory", refresh_policy="quarterly"),
]

OREGON_CITY_LAYERS: list[LayerSpec] = [
    # City of Oregon City — ArcGIS Enterprise at maps.orcity.org (v11.5)
    # All services are MapServer with Map,Query,Data capabilities.
    LayerSpec("zoning_oregon_city", "Zoning (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/LandUseAndPlanning_PUBLIC/MapServer/62", "oregon_city", authority="authoritative-zoning", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 62 = Zoning polygons. LandUseAndPlanning_PUBLIC MapServer also contains comp plan (57), enterprise zones (3, 85), opportunity zones (73), urban renewal district (33), historic districts (31-32), parking overlays."),
    LayerSpec("city_limits_oregon_city", "City Limits (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/Annexations/MapServer/0", "oregon_city", authority="authoritative-routing", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("taxlots_oregon_city", "Taxlots (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/Taxlots_PUBLIC/MapServer/0", "oregon_city", authority="reference-only", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("hazards_flood_oregon_city", "Hazards & Flood (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/HazardsAndFloodInfo_PUBLIC/MapServer/3", "oregon_city", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 3 = 100yr Floodplain. Same service contains: floodway (2), 500yr (4), landslides (5-8), geologic hazards (9-11), slope categories (12), riparian buffer zone (16, 20)."),
    LayerSpec("urban_renewal_oregon_city", "Urban Renewal District (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/LandUseAndPlanning_PUBLIC/MapServer/33", "oregon_city", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("enterprise_zone_oregon_city", "Enterprise Zones (Oregon City)", "https://maps.orcity.org/arcgis/rest/services/LandUseAndPlanning_PUBLIC/MapServer/3", "oregon_city", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver"),
]

GLADSTONE_LAYERS: list[LayerSpec] = [
    # City of Gladstone — hosted on Oregon City's ArcGIS Enterprise (maps.orcity.org/GLADSTONE folder)
    LayerSpec("zoning_gladstone", "Zoning (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_LandUseAndPlanning/MapServer/7", "gladstone", authority="authoritative-zoning", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 7 = Zoning. Same service: comp plan (6), urban renewal district (5), analysis centers (4), multifamily housing (3), vacant lands (2)."),
    LayerSpec("city_limits_gladstone", "City Limits (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_CityLimits/MapServer/0", "gladstone", authority="authoritative-routing", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("taxlots_gladstone", "Taxlots (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_Taxlots/MapServer/0", "gladstone", authority="reference-only", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("hazards_flood_gladstone", "Hazards & Flood (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_HazardsAndFloodInfo/MapServer/0", "gladstone", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="FEMA floodplain, landslide, and geologic hazard layers. Same structure as Oregon City hazard service."),
    LayerSpec("natural_resources_gladstone", "Natural Resources (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_WaterAndNaturalResources/MapServer/0", "gladstone", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("urban_renewal_gladstone", "Urban Renewal District (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_LandUseAndPlanning/MapServer/5", "gladstone", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("multifamily_housing_gladstone", "Multifamily Housing (Gladstone)", "https://maps.orcity.org/arcgis/rest/services/GLADSTONE/Gladstone_LandUseAndPlanning/MapServer/3", "gladstone", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver"),
]

LAKE_OSWEGO_LAYERS: list[LayerSpec] = [
    # City of Lake Oswego — ArcGIS Enterprise at maps.ci.oswego.or.us (v12)
    # Primary layer service: Layers_Geocortex/MapServer (comprehensive, all layers in one service)
    LayerSpec("zoning_lake_oswego", "Zoning (Lake Oswego)", "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/68", "lake_oswego", authority="authoritative-zoning", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 68 = Zoning. Also in same service: comp plan (69), design districts (58), lake grove village center (59), neighborhood overlays (60), SW overlay (61), Willamette River Greenway mgmt district (62)."),
    LayerSpec("city_limits_lake_oswego", "City Limits (Lake Oswego)", "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/1", "lake_oswego", authority="authoritative-routing", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("sensitive_lands_lake_oswego", "Sensitive Lands (Lake Oswego)", "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/57", "lake_oswego", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 57 = Sensitive Lands polygons. Also: streams (55), delineations (56), wetland (200), 50ft riparian protection area (308)."),
    LayerSpec("fema_flood_lake_oswego", "FEMA Floodplain (Lake Oswego)", "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/17", "lake_oswego", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 17 = FEMA. Also: 1996 flood level (18), soils (19), fault (20), shallow landslide susceptibility (22), deep landslide susceptibility (23)."),
    LayerSpec("urban_renewal_lake_oswego", "Urban Renewal Districts (Lake Oswego)", "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/10", "lake_oswego", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 10 = East End URA, layer 11 = Lake Grove URA."),
]

WEST_LINN_LAYERS: list[LayerSpec] = [
    # City of West Linn — ArcGIS Enterprise at geo.westlinnoregon.gov (v10.9)
    # All services in Operational folder; capabilities: Map,Query,Data.
    LayerSpec("zoning_west_linn", "Zoning (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/ZoningComPlan/MapServer/8", "west_linn", authority="authoritative-zoning", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 8 = Zoning polygon. Layer 10 = Comprehensive Plan. Max 2,000 records."),
    LayerSpec("city_limits_west_linn", "City Limits (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/ZoningComPlan/MapServer/0", "west_linn", authority="authoritative-routing", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("wetlands_west_linn", "Wetland Inventory (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/WetlandInventory/MapServer/1", "west_linn", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("fema_flood_west_linn", "FEMA Flood Hazard (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/FEMA/MapServer/1", "west_linn", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 1 = FEMA Flood Hazard Zones (2020). Layer 0 = cross-section elevations."),
    LayerSpec("habitat_conservation_west_linn", "Habitat Conservation Area (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/HCA/MapServer/1", "west_linn", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("riparian_corridor_west_linn", "Riparian Corridor (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/RiparianCI/MapServer/0", "west_linn", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("flood_management_west_linn", "Flood Management Area (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/FloodManagement/MapServer/1", "west_linn", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("regulatory_zones_west_linn", "Regulatory Overlay Zones (West Linn)", "https://geo.westlinnoregon.gov/server/rest/services/Operational/RegulatoryZones/MapServer/0", "west_linn", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 0 = Willamette Falls Drive Commercial Design District, 1 = Willamette Historic District (local), 2 = Willamette Historic District (National Register)."),
]

TUALATIN_LAYERS: list[LayerSpec] = [
    # City of Tualatin — ArcGIS Enterprise at tualgis.ci.tualatin.or.us (v10.91)
    # Straddles Clackamas + Washington County. All services in Public folder.
    LayerSpec("zoning_tualatin", "Zoning / Planning Districts (Tualatin)", "https://tualgis.ci.tualatin.or.us/server/rest/services/LandusePlanningExplorer/MapServer/6", "tualatin", authority="authoritative-zoning", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 6-7 = Planning Districts polygon. Zone code field: PLANDIST.CZONE (5-char, e.g. CO, RH, IN). Zone name field: PLANDIST.ZONE_NAME. Max 1,000 records."),
    LayerSpec("city_limits_tualatin", "City Limits (Tualatin)", "https://tualgis.ci.tualatin.or.us/server/rest/services/TualatinBoundaries/MapServer/0", "tualatin", authority="authoritative-routing", refresh_policy="quarterly", source_type="arcgis-mapserver"),
    LayerSpec("environmental_tualatin", "Environmental Overlays (Tualatin)", "https://tualgis.ci.tualatin.or.us/server/rest/services/EnvironmentalExplorer/MapServer/24", "tualatin", authority="screening-environmental", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 24 = Wetlands. Same service: 100yr floodplain (9), floodway (11), natural resources protection overlay (23), wetlands protection district (25), 50ft stream buffer (26), streams (18), slope ≥25% (3)."),
    LayerSpec("urban_renewal_tualatin", "Urban Renewal Areas (Tualatin)", "https://tualgis.ci.tualatin.or.us/server/rest/services/LandusePlanningExplorer/MapServer/3", "tualatin", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layer 3 = current URAs (Core Opportunity and Reinvestment Area, Leveton TID, SW & Basalt Creek). Layer 32 = Leveton TID."),
]

WILSONVILLE_LAYERS: list[LayerSpec] = [
    # City of Wilsonville — ArcGIS Enterprise at gis.wilsonvillemaps.com (v11.5)
    # Straddles Clackamas + Washington County. Primary public service: Map___WilsonvilleMaps_MIL1.
    LayerSpec("zoning_wilsonville", "Zoning (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___WilsonvilleMaps_MIL1/FeatureServer/40", "wilsonville", authority="authoritative-zoning", refresh_policy="quarterly", notes="Zone code field: ZONE_CODE. Values include OTR, PDC, PDI, R, V, Future Development categories."),
    LayerSpec("city_limits_wilsonville", "City Limits (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___WilsonvilleMaps_MIL1/FeatureServer/2", "wilsonville", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("taxlots_wilsonville", "Taxlots (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___WilsonvilleMaps_MIL1/FeatureServer/11", "wilsonville", authority="reference-only", refresh_policy="quarterly", notes="County assessor taxlots covering both Clackamas and Washington County portions."),
    LayerSpec("environmental_wilsonville", "Natural Resources / Environmental (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___NaturalResources/FeatureServer/1099", "wilsonville", authority="screening-environmental", refresh_policy="quarterly", notes="Layer 1099 = Significant Wetlands. Same service: upland wildlife habitat (1080), non-significant wetlands (1090), FEMA 100yr floodplain (1107), 1996 flood inundation (1030), rivers (1040), streams (1050-1060)."),
    LayerSpec("sroz_wilsonville", "SROZ — Significant Resource Overlay Zone (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___WilsonvilleMaps_MIL1/FeatureServer/60", "wilsonville", authority="screening-environmental", refresh_policy="quarterly", notes="Layer 60 = SROZ polygon; layer 70 = SROZ Impact Area. Primary environmental overlay for significant natural resource areas."),
    LayerSpec("urban_renewal_wilsonville", "Urban Renewal Areas (Wilsonville)", "https://gis.wilsonvillemaps.com/server/rest/services/Map___URA/MapServer/0", "wilsonville", authority="screening-regulatory", refresh_policy="quarterly", source_type="arcgis-mapserver", notes="Layers: URA_Coffee (0), URA_East (1), URA_TWIST (3), URA_West (4), URA_WIN (5). Also FeatureServer version available at same path."),
]

OREGON_STATEWIDE_LAYERS: list[LayerSpec] = [
    LayerSpec(
        "tax_lots_metro_rlis",
        "Taxlots — Portland Metro (Multnomah + Clackamas)",
        "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/3",
        "oregon",
        where="COUNTY IN ('M', 'C')",
        authority="authoritative-routing",
        refresh_policy="quarterly",
        notes="Metro RLIS public taxlots. Updated via rlis_delta.py (quarterly delta ZIP). Full replace only on first cache or --full-replace flag. 645k total; ~430k after M+C filter. Fields: TLID, ASSESSVAL, LANDVAL, BLDGVAL, LANDUSE, YEARBUILT, BLDGSQFT, SITEADDR, JURIS_CITY, STATECLASS. No owner name (privacy-restricted). Layer excludes ROW features by definition query.",
    ),
    LayerSpec("building_footprints_or", "Building Footprints (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Building_Footprints/FeatureServer/0", "oregon", authority="screening-routing", refresh_policy="quarterly"),
    LayerSpec("address_points_or", "Address Points (Oregon — Multnomah + Clackamas)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Address_Points/FeatureServer/0", "oregon", where="County IN ('Multnomah County', 'Clackamas County')", authority="authoritative-routing", refresh_policy="quarterly", fetch_geometry=False),
    LayerSpec("oregon_zip_reference", "Oregon ZIP Reference", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/OregonZIPCodes/FeatureServer/0", "oregon", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("census_block_groups_2020_or", "Census Block Groups 2020 (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/CensusBlockGroups/FeatureServer/0", "oregon", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("census_tracts_2020_or", "Census Tracts 2020 (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/CensusTracts/FeatureServer/0", "oregon", authority="reference-only", refresh_policy="quarterly"),
    LayerSpec("city_limits_or", "City Limits (Oregon)", "https://gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/MapServer/220", "oregon", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("county_boundaries_or", "County Boundaries (Oregon)", "https://services1.arcgis.com/KbxwQRRfWyEYLgp4/arcgis/rest/services/BLM_OR_County_Boundaries_Polygon_Hub/FeatureServer/1", "oregon", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("urban_growth_boundaries_or", "Urban Growth Boundaries (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/UGB_2022/FeatureServer/0", "oregon", authority="authoritative-routing", refresh_policy="quarterly"),
    LayerSpec("enterprise_zones_or", "Enterprise Zones (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/EnterpriseZones2023/FeatureServer/0", "oregon", authority="screening-regulatory", refresh_policy="quarterly"),
    LayerSpec("wetlands_lwi_or", "Wetlands - LWI (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Wetlands_NWI/FeatureServer/0", "oregon", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("wetlands_nwi_or", "Wetlands - NWI (Oregon)", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Wetlands_NWI/FeatureServer/1", "oregon", authority="screening-environmental", refresh_policy="quarterly"),
    LayerSpec("wetlands_more_or", "Wetlands - More Oregon Wetlands", "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Oregon_Wetlands_NWI/FeatureServer/2", "oregon", authority="screening-environmental", refresh_policy="quarterly"),
    # ODOT Federal Functional Classification — two layers together cover every
    # public road in Multnomah + Clackamas (and all of Oregon).
    # NEW_FC_TYP values: Interstate, Other Freeway and Expressway, Other Principal
    # Arterial, Minor Arterial, Major Collector, Minor Collector, Local.
    # NEW_FC_CD: single character (1=Interstate … 7=Local).
    # JRSDCT = road owner (jurisdiction). No dedicated county field — filter by
    # spatial intersection or by JRSDCT for county/city roads.
    LayerSpec(
        "street_functional_class_state_or",
        "Federal Functional Classification — State Roads (Oregon)",
        "https://gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/MapServer/171",
        "oregon",
        authority="screening-routing",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        notes="ODOT-owned roads. Fields: NEW_FC_TYP (classification label), NEW_FC_CD (1-char code), JRSDCT (owner), ROAD_NAME. MapServer with query support.",
    ),
    LayerSpec(
        "street_functional_class_nonstate_or",
        "Federal Functional Classification — Non-State Roads (Oregon)",
        "https://gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/MapServer/173",
        "oregon",
        authority="screening-routing",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        notes="County, city, and other non-ODOT roads. Same schema as state layer (NEW_FC_TYP, NEW_FC_CD, JRSDCT, ROAD_NAME). Together with layer 171, covers every classified public road in Mult + Clack.",
    ),
]

EXTERNAL_LAYERS: list[LayerSpec] = [
    LayerSpec(
        "opportunity_zones_or",
        "Opportunity Zones (Oregon)",
        "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/Opportunity_Zones/FeatureServer/13",
        "external",
        where="STATE = '41'",
        authority="screening-regulatory",
        refresh_policy="quarterly",
    ),
    LayerSpec(
        "nmtc_qualified_tracts_or",
        "NMTC Qualified Tracts (Oregon)",
        "https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/ArcGIS/rest/services/NMTC_Qualified_Tracts_2020/FeatureServer/3",
        "external",
        where="STATE_FIPS = '41'",
        authority="screening-regulatory",
        refresh_policy="quarterly",
    ),
]

# Oregon Navigator server (navigator.state.or.us) — all MapServer, viz-only.
# Layers below are registered for future tooling; not bulk-queryable today.
NAVIGATOR_LAYERS: list[LayerSpec] = [
    LayerSpec(
        "bio_wetlands_or",
        "Biological Wetlands (Oregon Statewide — Navigator)",
        "https://navigator.state.or.us/arcgis/rest/services/Framework/Bio_Wetlands/MapServer",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        enabled=False,
        notes="23-layer wetlands service from Oregon Navigator. More comprehensive than NWI alone. MapServer only — needs export tooling, not FeatureServer /query.",
    ),
    LayerSpec(
        "haz_general_or",
        "General Hazards (Oregon Statewide — Navigator)",
        "https://navigator.state.or.us/arcgis/rest/services/Framework/Haz_GeneralMap/MapServer",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        enabled=False,
        notes="4-layer hazards overview from Oregon Navigator (landslide, earthquake, tsunami, volcano zones). MapServer only.",
    ),
    LayerSpec(
        "hydro_general_or",
        "Hydrology (Oregon Statewide — Navigator)",
        "https://navigator.state.or.us/arcgis/rest/services/Framework/Hydro_GeneralMap/MapServer",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        enabled=False,
        notes="13-layer hydrology service from Oregon Navigator (streams, lakes, watersheds). MapServer only.",
    ),
    LayerSpec(
        "admin_bounds_or_nav",
        "Administrative Boundaries (Oregon Statewide — Navigator)",
        "https://navigator.state.or.us/arcgis/rest/services/Framework/Admin_Bounds/MapServer",
        "oregon",
        authority="reference-only",
        refresh_policy="quarterly",
        source_type="arcgis-mapserver",
        enabled=False,
        notes="8-layer admin boundaries from Oregon Navigator. Redundant with county_boundaries_or + city_limits_or for our purposes. MapServer only.",
    ),
]

# Oregon Navigator geocoder — called on-demand, not cached as GeoJSON.
# Use vicinitideals.utils.geocoder.geocode_oregon_address() to resolve listing addresses.
NAVIGATOR_GEOCODER_URL = "https://navigator.state.or.us/arcgis/rest/services/Locators/OregonAddress/GeocodeServer"

PLANNED_SOURCES: list[LayerSpec] = [
    LayerSpec(
        "zoning_or_statewide",
        "Zoning (Oregon Statewide — DLCD)",
        "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/Zoning/FeatureServer/0",
        "oregon",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        enabled=False,
        notes="QA'd against Gresham: localZCode is empty for all Gresham features; orZCode only has 2 coarse values (MURMH, Res.) across 302 features. Layer is a generalized state overlay, not a replacement for local zoning. Use jurisdiction-specific GIS layers for authoritative zoning.",
    ),
    LayerSpec(
        "comp_plan_designations_or",
        "City and County Comprehensive Plan Designations (Oregon)",
        "https://services8.arcgis.com/8PAo5HGmvRMlF2eU/arcgis/rest/services/City_and_County_Comprehensive_Plan_Designations/FeatureServer/0",
        "oregon",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        enabled=False,
        notes="Same DLCD source as zoning_or_statewide. Not evaluated independently — disabled alongside zoning layer pending local-first zoning strategy.",
    ),
    LayerSpec(
        "usda_ruca_2020_or",
        "USDA RUCA 2020 (Oregon screening baseline)",
        "https://www.ers.usda.gov/data-products/rural-urban-commuting-area-codes/",
        "oregon",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        source_type="manual-download",
        enabled=False,
        notes="Use USDA ERS RUCA tract/ZIP releases as the reproducible rural screening layer until a better public GIS geometry is wired in.",
    ),
    LayerSpec(
        "public_transit_parking_relief_or",
        "Public Transit Parking Relief Areas (derived)",
        "https://www.oregon.gov/lcd/UP/Pages/Climate-Friendly-and-Equitable-Communities.aspx",
        "oregon",
        authority="screening-regulatory",
        refresh_policy="quarterly",
        source_type="derived",
        enabled=False,
        notes="Derive from GTFS routes/stops plus Oregon parking-relief rule geometry if no statewide authoritative polygon layer is published.",
    ),
    LayerSpec(
        "fema_flood_studies_or",
        "Oregon Statewide Flood Hazards - FEMA Flood Insurance Studies",
        "https://ftp.gis.oregon.gov/framework/hazards/Oregon_Statewide_Flood_Hazards.zip",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="manual-download",
        enabled=False,
        notes="One source in the additive flood evidence family; preserve provenance separately from observed inundation and other studies.",
    ),
    LayerSpec(
        "observed_inundation_or",
        "Oregon Statewide Flood Hazards - Observed Inundation",
        "https://ftp.gis.oregon.gov/framework/hazards/Oregon_Statewide_Flood_Hazards.zip",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="manual-download",
        enabled=False,
        notes="Historical evidence layer in the additive flood family.",
    ),
    LayerSpec(
        "other_flood_studies_or",
        "Oregon Statewide Flood Hazards - Other Flood Studies",
        "https://ftp.gis.oregon.gov/framework/hazards/Oregon_Statewide_Flood_Hazards.zip",
        "oregon",
        authority="screening-environmental",
        refresh_policy="quarterly",
        source_type="manual-download",
        enabled=False,
        notes="Supplemental study layer in the additive flood family.",
    ),
]

# Jurisdictions with no queryable GIS zoning layer — only PDF zoning maps available.
# Parcels assigned to these jurisdictions with no zoning_code should have
# zoning_lookup_url populated so the UI can link users to the authoritative map.
ZONING_PDF_JURISDICTIONS: dict[str, str] = {
    "fairview": "https://fairvieworegon.gov/DocumentCenter/View/3458/Zoning-Map-PDF",
}

ALL_LAYER_SPECS: list[LayerSpec] = [
    *GRESHAM_LAYERS,
    *FAIRVIEW_LAYERS,
    *WOOD_VILLAGE_LAYERS,
    *TROUTDALE_LAYERS,
    *HAPPY_VALLEY_LAYERS,
    *MILWAUKIE_LAYERS,
    *OREGON_CITY_LAYERS,
    *GLADSTONE_LAYERS,
    *LAKE_OSWEGO_LAYERS,
    *WEST_LINN_LAYERS,
    *TUALATIN_LAYERS,
    *WILSONVILLE_LAYERS,
    *OREGON_STATEWIDE_LAYERS,
    *EXTERNAL_LAYERS,
    *NAVIGATOR_LAYERS,
    *PLANNED_SOURCES,
]

ACTIVE_LAYERS: list[LayerSpec] = [
    spec
    for spec in ALL_LAYER_SPECS
    if spec.enabled and spec.source_type in ("arcgis", "arcgis-mapserver")
]

__all__ = [
    "ACTIVE_LAYERS",
    "ALL_LAYER_SPECS",
    "EXTERNAL_LAYERS",
    "FAIRVIEW_LAYERS",
    "GLADSTONE_LAYERS",
    "GRESHAM_LAYERS",
    "HAPPY_VALLEY_LAYERS",
    "LAKE_OSWEGO_LAYERS",
    "MILWAUKIE_LAYERS",
    "NAVIGATOR_GEOCODER_URL",
    "NAVIGATOR_LAYERS",
    "OREGON_CITY_LAYERS",
    "OREGON_STATEWIDE_LAYERS",
    "PLANNED_SOURCES",
    "TUALATIN_LAYERS",
    "TROUTDALE_LAYERS",
    "WEST_LINN_LAYERS",
    "WILSONVILLE_LAYERS",
    "WOOD_VILLAGE_LAYERS",
    "ZONING_PDF_JURISDICTIONS",
    "LayerSpec",
]
