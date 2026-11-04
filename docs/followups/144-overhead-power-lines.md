# 144. Overhead power lines: is there a map good enough to screen with? (Steph asked 2026-11-03)

144. [Claude] [Steph: whether to use it] [scan: YES if built (greens can only lose)] **Overhead power lines near the building and court.**

Steph 2026-11-03: "Are there reasonably accurate maps of where overhead power lines are in our districts?"

SCOUT 2026-11-03 (Copilot gpt-6-luna, brief docs/copilot/briefs/power-lines-scout.txt) + Claude check:
- PGE Public_Data FeatureServer (services6.arcgis.com/eqsXlDArbs19VWhn/arcgis/rest/services/Public_Data/FeatureServer):
  layer 17 "Overhead Primary Distribution", layer 19 "Overhead Transmission", separate underground layers.
  Last edited 2026-11-02 (weekly). Claude checked layer 17: ONE dissolved polyline feature, 28,272 parts,
  303,531 vertices, lon -123.68..-121.67, lat 44.77..46.17 (PGE territory only -- Pacific Power areas
  missing), median vertex spacing 48 m (about a pole span, so vertices may sit at poles). No attributes
  (no voltage, no per-span id). Primary only -- secondary/service drops to houses not shown. Accuracy
  unstated; "as is" disclaimer. Copy fetched to the session scratchpad for inspection only (pge17.json).
- BPA and HIFLD transmission layers: transmission only, accuracy unstated. Oregon GEOHub
  Electric_Transmission_Lines: last updated 2020, display/aviation use.
- Metro RLIS, county GIS, PortlandMaps, ODOE, PUC: no line geometry found. WashCo maps show large
  easements (BPA) only. OSM minor_line completeness not measured.

OPEN: (1) spot-check PGE positions against aerial imagery on ~20 lots; (2) find the clearance rule that
would apply (NESC / Oregon OAR 860-024 vertical + horizontal clearance from buildings; PGE's own
setback guidance) -- the screen needs a stated distance; (3) Pacific Power territory (parts of
Clackamas/Washington?) has no source yet; (4) Steph: use it as a YELLOW flag ("line within X ft of the
building") or not at all. Overlaps the utility easement rule (memory project_flats_utility_easement).

OSM 2026-11-03: another agent reports OpenStreetMap has some poles/lines. Completeness NOT measured: overpass-api.de answered 406 / empty, kumi.systems and private.coffee empty (3 tries, stopped). To measure: the Geofabrik Oregon extract (download.geofabrik.de/north-america/us/oregon-latest.osm.pbf, a few hundred MB -- needs Steph's OK to download), count power=pole / minor_line / line per city against street length, and compare with PGE layer 17 on the same city.

PACIFIC POWER FOUND 2026-11-03 (Steph sent https://experience.arcgis.com/experience/6f422654851e4d858852fa00d1905170, "PacifiCorp Transmission & Distribution Public Map", owner PacifiCorp_Admin). Behind it:
https://services1.arcgis.com/ePo6UhbBpZFy1wO2/arcgis/rest/services/Transmission_and_Distribution_Public/FeatureServer
-- 0 Poles (points; Pole_Type Distribution/Transmission, pole IDs), 1 Substations, 3 Transmission_Lines (Line_Name, Line_Type),
4 Distribution_Lines (per CIRCUIT_ID, Line_Type OH/UG), 5 Service_Territory. Last edited 2026-11-03. In the metro box
(lon -123.2..-122.3, lat 45.2..45.7): 15,686 distribution + 1,928 transmission poles, 141 distribution circuits (58 OH,
83 UG), 42 transmission lines; poles span lon -122.77..-122.40, lat 45.49..45.70 = Pacific Power's Portland
territory (N/NE/East Portland). With PGE layer 17/19 that covers the metro. Individual poles make an aerial
accuracy check easy (pole vs imagery).

PGE POLES 2026-11-03 (Steph sent the PGE "Pole Search Map", item 3a16ae0abcba4f62a03eca1ae7672def, owner PGE_PublicData): the same Public_Data FeatureServer also has every pole as a point -- layer 13 Distribution Pole (364,540; FACILITYID, HEIGHT ft, MATERIAL, CLASS, INSTALLATIONDATE, lat/lon), 14 Transmission Structure (26,009), 1 Streetlight (176,739), plus wireless/foreign-owned poles (2-5), EV chargers, substations, feeder extents. Claude's earlier "line runs about here" framing was wrong: both utilities publish each pole's position; the line layers join the poles (48 m median vertex spacing = pole spans). Accuracy still unstated -> the aerial spot-check stays, but on poles, not lines.
