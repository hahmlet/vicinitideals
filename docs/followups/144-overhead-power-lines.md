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
