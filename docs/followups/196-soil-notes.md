# 196. Soil type per lot, as a note only

[Claude] [scan: NO -- note only, no colour]

Steph 2026-11-17: "Do we have data on the soil types for all of our lots?" No. Steph said yes to pulling
the USDA soil survey (SSURGO; free, public) and attaching it to each lot as a NOTE ONLY (no colour, no
reason code, no severity that can hold a lot), "start with green lots and let me know when those are
done. Then continue on the rest."

Built on branch flats/soil-notes (hand-off ../vicinitideals-worktrees/soil-notes.handoff.md):
`flats/ingest/soil.py`, `scripts/flats_lot_soil.py` (extract / sda / build / load), migration 0151
(`flats.soil_map_units`, `flats.soil_components`, `flats.lot_soil`), the lot page's "Soil (USDA
survey)" block and the lot report's `soil` key. Runbook: docs/ops/flats-county-refresh.md, steps S1-S4.

Source: NRCS state GeoPackage `SQLite_SSURGO_OR` (published 2026-10-01; OR051, OR610, OR067 at
saverest 09/08/2026, plus OR608, OR657, OR674 at the county edges). Soil Data Access was down
(502) on 2026-11-18.

Fields kept (Steph 2026-11-17, via the coordinator):
- every map unit touching a lot, square feet (EPSG:2913) and share; the uncovered part as its own row;
  rows sum to the lot area; dominant (most ground) and worst-rated (dwellings, then small commercial)
  as the headline;
- map units stored once by `mukey`: areasymbol, areaname, saverest, musym, nationalmusym, muname,
  mukind, muaggatt drainage / hydrologic group / hydric percent / shallowest water table / bedrock /
  dwellings rating, both building ratings by dominant condition;
- components by `cokey`: name, percent, kind, major flag, taxclname, order, suborder, great group,
  subgroup, particle size, drainage, hydric rating, hydrologic group, shallowest wet layer and month,
  highest linear extensibility (class from NSSH Part 618), shallowest restrictive layer and kind,
  both ratings and their limiting reasons;
- winter groundwater: each component's monthly wet-layer depth with flooding and ponding class, the
  shallowest November-April depth and its months per component and per map unit, "none recorded"
  kept apart from "no data";
- the source named plainly as USDA NRCS soil survey (SSURGO) with survey area and date.

Open:
- The state download has no limiting reasons (cointerp ruledepth 1) and no `nationalmusym`: run
  `flats_lot_soil.py sda` when Soil Data Access answers, then `load --tables-only`.
- Lot rows are per snapshot: reload after each new county copy.
- Optional second layer if cheap: DOGAMI landslide susceptibility and liquefaction.
- Feeds the crane check's "firm ground: not checked" (145) later.
