# 140. Johnson Creek tree limits: clear lots with no big trees?

[Claude] Offered 2026-11-01 with the Portland plan districts part 1 build (FOLLOWUPS 109,
branch flats/districts-pdx-pd1, 2a899813). PCC 33.537 (Johnson Creek Basin plan district) limits
removing larger trees on lots in the South subarea, on flood ground and along the Springwater
corridor; nothing measures trees, so about 430 lots that were GREEN go YELLOW ("check first").
QUESTION for Steph: use the city's tree-canopy layer (Metro / Portland canopy data, free) to clear
the lots with no qualifying trees, or leave them yellow? If yes: a source scout for the canopy
layer and its date, then an encoder adds a measured fact (no canopy over the pod's footprint +
court) and a bound; never release a lot the canopy layer cannot see clearly.

STEPH 2026-11-01: "Let's build in the tree map" (rulings.yaml
2026-11-01-johnson-creek-trees-cleared-by-canopy-map). Plan: (a) source scout -- the canopy layer,
its date, resolution and licence, plus a Springwater Corridor boundary layer; (b) encoder on a
branch stacked after pd1's release -- measured canopy fact over pod + court, and corridor-abutting
lot lines for the 20 ft buffer; canopy or an unreadable patch keeps YELLOW; (c) bound, read every
gained green, release.
READ 2026-11-01: 33.537.125 C.3 lets any tree within 10 ft of the building or a proposed driveway
come out by right, so the canopy test is only over the court/stalls more than 10 ft from both
(conservative: the court is not a "driveway"). C.6 (6-12 in. trees replaced two-for-one) is also
by right but the canopy layer cannot size trunks, so it does not clear anything.
SCOUT 2026-11-01 (nothing held in repo or on 137): canopy = Metro RLIS "Canopy 2019" (LiDAR,
summer 2019, raster with canopy height; item b6da4ea243df4ba492d47860964cf2b5, 2.9 GB zip, RLIS
open licence; cell size to confirm on download) as primary, cross-checked with Metro C-CAP land
cover 2021 (1 m, Ecopia AI from 30 cm imagery, item 8b89f2c933894056a02fd3c2d8a48f31, 477 MB;
"not for litigation", no ML training -- neither touches us). Rule: canopy in EITHER layer keeps
yellow (catches post-2019 growth; LiDAR has no shadow problem, C-CAP may). Portland 2022 6 in
vegetation is tiles only, unusable. Corridor = Portland Parks_Misc/MapServer/2
NAME='Springwater Corridor' (PROPERTYID 679, one polygon, GeoJSON, no account).
DOWNLOADED 2026-11-01 (Steph OK): 137 /root/code/vicinitideals/data/flats/canopy/2026-11-01/
(Canopy2019.gdb 2.8 GB, one raster `Canopy2019`; LandCover_1meter.gdb 604 MB, rasters
CCAP_1m_canopy, _canopy_reclassified, _impervious, _water; both EPSG:2913, Esri file-GDB RASTER).
TRAP: the venv's rasterio (GDAL 3.12 wheel) has no OpenFileGDB driver and 137 has no gdalinfo, so
step one of the build is converting both to GeoTIFF (a GDAL build with OpenFileGDB raster, >= 3.7)
and reading the 2019 cell size, which is still unconfirmed. The 1 m layer also carries impervious
-- possibly useful for 33.537's 50% cap later.
WATCH (Steph 2026-11-01 asked "are we tracking the tree [map] for updates?" -- not yet): the build
registers both Metro items (and the Parks corridor layer) in the county source registry the monthly
probe reads (flats/ingest/probe.py: rlis_zip item -> new_release on a changed modified/size; arcgis
layer -> moved/count_drift), so a newer canopy release raises the County copy banner like the
county data does. Record each item's modified date + size in the manifest at acquire.

COPILOT RE-SCOUT 2026-11-01 (gpt-6-luna, A/B trial) found two more: DOGAMI Canopy Height Model
mosaic ImageServer https://gis.dogami.oregon.gov/arcgis/rest/services/lidar/CANOPY_HEIGHT_MODEL_MOSAIC/ImageServer
(3 ft cells, height above ground in ftUS, but outer-SE sources 2004-2014 -- too old alone) and USFS
Tree Canopy Cover 2025 (30 m, too coarse). Canopy 2019 cell size still UNKNOWN (both runs inferred,
~0.5 m and ~1 m); read it from the raster at conversion.

STEPH 2026-11-01 asked: do the height maps give species / can we size the trees from the old height?
No species in DOGAMI CHM or Metro Canopy 2019 (height only); Portland's street- and park-tree
inventories carry species + trunk size but not yard trees. Sizing matters at 12 in: 33.537.125 C.6
lets a 6-12 in tree go by right if replaced two-for-one, so only a tree over 12 in in the court
ground truly holds a lot. Height -> trunk is species-dependent and the trees have grown since the
flight, so 'under 12 in now' is NOT safe for a GREEN. PROPOSED (waits on Steph): use height only to
inform -- print 'tallest tree cover in the parking area: ~N ft (2019 laser scan)' on the yellow lot's
reason, so whoever checks the lot knows at a glance whether it is a hedge or a big tree.

STEPH 2026-11-01: can the old (DOGAMI 2004-14) and 2019 scans be matched tree by tree? No tree IDs:
both are height GRIDS, so the link is position. Plan option for the build: find tree tops (local
height peaks) in each grid over the court ground, pair peaks within a few feet, and read each pair's
height gain (alive in both + growth rate); a peak only in the old scan = probably removed, only in
2019 = newer tree. C-CAP 2021 adds a third date (cover, no height). Limits: grid cell size (DOGAMI 3
ft; Metro to confirm) and scan alignment. Copilot tree-growth scout running (docs/copilot/briefs/tree-growth.txt).
GROWTH ANSWER 2026-11-01 (Copilot gpt-6-luna, 3.3 AI units; main source USFS Urban Tree Database
PSW-GTR-253, 14,000+ street trees, 17 cities -- per-species coefficients not extractable): NO, a tree
seen in the 2019 or older scan is not safely over 12 in. now. Unknowns: the scan's minimum height,
species, trunk size at the scan. A 1-2 in. planting needs ~1.5 in./yr to reach 12 in. by 2026;
typical urban rates are well under that (general forestry knowledge, not from the scout), and
hedges / Japanese maple / dogwood may never reach it. So canopy stays a reason to check (YELLOW),
never proof either way; the ruling as written is unchanged.
