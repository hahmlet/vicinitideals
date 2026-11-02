# 109 appendix: Portland plan districts part 2 -- inventory (Copilot scout, 2026-11-01)

Copilot (claude-sonnet-5.5, read-only template docs/copilot/briefs/common-readonly.txt). Spot-checked by
the coordinator: 33.563 title line, Map 521-n and 562-n lists, grep counts, subdistrict letters -- all right.
Map-to-layer matches are by layer NAME only (unverified). 33.505 has 0 dimension lines (Albina is a
short chapter).

SEEN = read in source. Map-to-layer matches are INFERRED from the layer name unless I say otherwise. Layer ids come from the MapServer listing, which returned HTTP 200. Both geojson files were read locally.

Titles are at L2 of each file. L1 of every file is only "Title 33, Planning and Zoning Chapter 33.5NN". Dims are grep counts of lines matching "feet|percent|units|stories".

33.505 | Albina Community Plan District (#L2) | AC | subdistricts: none | maps: 505-1 -> layer 0 "Plan Districts" | dims ~0
33.510 | Central City Plan District (#L2) | CC (and CCSA, see below) | subdistricts: Central Eastside, Downtown, Goose Hollow, Lloyd, Lower Albina, Old Town/Chinatown, Pearl, South Waterfront, University District/South Downtown, West End -> yes (10 held). The Pearl, Central Eastside and South Waterfront names are SEEN in the text; I did not read the text for the other seven. | maps: 510-1 -> layer 1 "Subdistricts"; 510-2 -> 50 "FAR boundary"; 510-3 -> 61; 510-4 -> 62; 510-5 -> 23 (weak match); 510-6 -> 81; 510-7 -> 71; 510-8 -> 14/15; 510-9 -> 14/15; 510-10 -> 67; 510-11 -> 63; 510-12 -> not held (no matching layer name); 510-13 to 510-23 -> captions not read, unknown | dims ~263
33.520 | Division Street Plan District (#L2) | DV | none | 520-1 -> layer 0 | ~3
33.521 | East Corridor Plan District (#L2) | EC | 122nd Avenue -> yes | 521-1 -> layer 0; 521-2 -> 61; 521-3 -> 50; 521-4 (exterior display and storage) -> not held | ~42
33.530 | Glendoveer Plan District (#L2) | GL | none | 530-1 -> layer 0 | ~13
33.532 | Hayden Island Plan District (#L2) | HI | Jantzen Beach (East, West) -> yes | 532-1 -> layers 0 and 1; 532-2 -> 61; 532-3 (island core access streets) -> not held | ~33
33.533 | Healy Heights Plan District (#L2) | HH | none | 533-1 -> layer 0 | ~1
33.534 | Hillsdale Plan District (#L2) | HD | none | 534-1 -> layer 0 | ~3
33.536 | Hollywood Plan District (#L2) | HW | Subdistricts A, B -> yes. The text refers to "Subdistrict" followed by a letter that my search did not capture; A and B are INFERRED. | 536-1 -> layers 0 and 1; 536-2 -> 61; 536-3 -> 32 | ~49
33.538 | Kenton Plan District (#L2) | KN | none | 538-1 -> layer 0; 538-2 -> 61; 538-3 -> 50; 538-4 -> 71; 538-5 -> 14/15; 538-6 -> 65 | ~10
33.545 | Lombard Street Plan District (#L2) | LB | text names "Subdistrict" followed by a letter; A and B held -> yes (INFERRED) | 545-1 -> layer 0 | ~16
33.550 | Macadam Plan District (#L2) | MA | none | 550-1 -> layer 0 | ~9
33.560 | North Cully Plan District (#L2) | CY | "subarea" mentioned; no names captured. None held (the held subareas belong to NH). | 560-1 -> layer 0 | ~0
33.561 | North Interstate Plan District (#L2) | NI | none | 561-1 -> layer 0; 561-2 -> 61; 561-3 -> 50; 561-4 -> 71 and 14/15 | ~18
33.562 | Northwest Plan District (#L2) | NP | none | 562-1 -> layer 0; 562-2 -> 54; 562-3 -> 28; 562-4 -> 61; 562-5 -> 50; 562-6 -> 23; 562-7 (special development standards) -> not held; 562-9 -> 73. The chapter cites no 562-8. | ~48
33.563 | Northwest Hills Plan District (title at L4; L2 is only the date) | NH | Forest Park (with Linnton and Miller Creek subareas), Skyline, Balch Creek -> held as NH features: Forest Park, Forest Park/Linnton, Forest Park/Miller Creek, Skyline, Balch Creek Watershed, Balch Creek/Skyline, Skyline/Forest Park. The text names a "Hillside subarea" that is not held -> partial. | 563-1 -> layers 0 and 1 | ~16
33.565 | Portland International Airport Plan District (#L2) | PA | Airport, Middle Columbia Slough -> yes | 565-1 -> layers 0 and 1; 565-2 -> 27. The chapter cites no 565-3. | ~35
33.570 | Rocky Butte Plan District (#L2) | RB | none | 570-1 -> layer 0 | ~9
33.580 | South Auditorium Plan District (#L2) | SA | none | 580-1 -> layer 0; 580-2 -> 50; 580-3 -> 68 | ~1
33.583 | St. Johns Plan District (#L2) | SJ | Riverfront -> yes | 583-1 -> layers 0 and 1; 583-2 -> 61 | ~10
33.595 | West Portland Multicultural Plan District (title at L3; L2 is only the date) | WP | Subdistricts A to D are held. The text names "Subdistrict" followed by a letter, and I did not confirm which letters it uses -> yes, INFERRED. | 595-1 -> layers 0 and 1; 595-2 (employment focus area) -> not held; 595-3 -> 141; 595-4 -> 50 | ~69

PLDIST notes (SEEN):
- plan-districts.geojson holds a PLDIST code for every chapter above.
- It also holds CCSA ("Central City & South Auditorium") alongside CC.
- It also holds JC, PB, PV, PR, SS, SD, SI, GS, LH, EM, CP and CY, which have no chapter in this batch, so their chapters are outside the 21 files.

GAPS (maps with no matching layer name and no copy in the repo):
- Map 510-12 (retail limited) and Maps 510-13 to 510-23 (captions unread)
- Map 521-4
- Map 532-3
- Map 562-7
- Map 595-2
- Hillside subarea of NH (33.563)
- Whether Lombard and Hollywood have a subdistrict C or later is unconfirmed.

The plan-districts and plan-subdistricts geojson cover the "-1" district maps only.

LOOKED:
- The 21 chapter files, grepped for "Map 5NN-n", "subdistrict", "subarea" and "feet|percent|units|stories".
- The geojson properties, read with the venv python -I.
- GET https://www.portlandmaps.com/arcgis/rest/services/Public/BPS_Zoning_Code_Layers/MapServer?f=json -> 200.
- I did not query individual layers, so the layer-to-map matches rest on layer names only.

MISSING MAPS SCOUT 2026-11-01 (Copilot gpt-6-luna, 5.6 AI units; layer matches mostly by NAME, so
check each layer's description before encoding -- "INFERRED" below = name only). All on
https://www.portlandmaps.com/od/rest/services/COP_OpenData_ZoningCode/MapServer unless noted:
510-12 layer 157 Limited Use Areas (Central City features); 510-13 Public/Transit/MapServer 5 Street
Car Lines (INFERRED); 510-14 192 Park Block Frontages; 510-15 139 South Waterfront Accessways
(INFERRED); 510-16 156 Height Opportunity Area; 510-17 BPS_Zoning_Code_Layers 96 Vehicle
Repair/Sales/Leasing Uses Restricted; 510-18 176 Special Building Height Corridors; 510-19 159
Required Master Plan Sites; 510-20 229 Scenic View Cone Area (INFERRED); 510-21 174 South Waterfront
Top of Bank; 510-22 166 Required Building Lines; 510-23 244 Floor Area Transfer Sectors; 521-4 157
Limited Use Areas (East Corridor feature); 532-3 177 Street Plan (Hayden Island, INFERRED);
540-1/540-2 172 Setbacks Plan Districts (one layer for both). NOT FOUND: 562-7 (Northwest; PDF only,
page unknown; BPS layer 49 NW FAR not confirmed), 595-2, Northwest Hills Hillside subarea (563).
Also found: Map 120-2 / 120-3 (item 68).

LAYER CHECK 2026-11-01 (Copilot gpt-6-luna, 3.1 AI units; each verdict from the layer's own
description/attributes): CONFIRMED 510-12 (157, PLDIST=CC), 510-13 (Transit/5 streetcar), 510-14 (192),
510-15 (139), 510-16 (156), 510-18 (176), 510-19 (159, NOTES "Zoning Code map 510-19"), 510-20 (229),
510-21 (174), 510-22 (166, PLDIST=CC rows), 510-23 (244), 521-4 (157, PLDIST=EC), 532-3 (177, PLAN=HAYDEN
ISLAND), 540-1/540-2 (172, PLDIST=LH/EM). WRONG: 510-17 (BPS 96 is vehicle sales/leasing + exterior
display, not repair -- read the map title before using), Northwest Hills Hillside (COP 137 has Forest
Park, Skyline, Balch Creek only). NAME ONLY: 562-7 (BPS 54, PLDIST=NP retail 3,000 sq ft -- likely the
NW retail-limit map, check the code text), 595-2 (COP 145 West Portland Multicultural, adopted area
plans layer -- probably not the map). Still to source: 595-2, Hillside subarea (from the PDF maps).

FETCHED 2026-11-01 (Copilot 86aa8ac5): all 15 layers above as area files in
flats/config/areas/or/multnomah/portland/ (limited-use-areas, streetcar-lines, park-block-frontages,
south-waterfront-accessways, height-opportunity-areas, special-building-height-corridors,
required-master-plan-sites, scenic-view-cones, south-waterfront-top-of-bank, required-building-lines,
floor-area-transfer-sectors, street-plans, setbacks-plan-districts). Not wired in. Re-fetch with
scripts/flats_fetch_area.py.
