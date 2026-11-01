# 140. Trees: ignored by the screen, entered per lot

[Claude][Steph] STEPH 2026-11-01 (rulings.yaml 2026-11-01-trees-ignored-entered-per-lot, superseding
2026-11-01-johnson-creek-trees-cleared-by-canopy-map): "I'm thinking we ignore trees entirely and let
users put it in per lot. Unless we find a reputable commercial solution in the future (not looking for
it now)". The canopy-map build is CANCELLED and nothing watches the canopy layers.

Why the canopy map was dropped: no public layer gives species or trunk size; the Copilot growth scout
(gpt-6-luna, USFS Urban Tree Database PSW-GTR-253) could not show a tree seen in the 2019 or 2004-14
scans is now over or under 12 in., and 33.537.125 C.6 makes 12 in. the line that matters.

TO BUILD (next week, after the Tue reset):
(a) Encoder: Johnson Creek (PCC 33.537) holds lots in flats/config/areas/or/multnomah/portland/
    johnson-creek-unmeasured-lots.geojson for four reasons -- tree removal (.125), the Springwater 20 ft
    strip (.130), South subdistrict density (.140.E), Flood Risk Area (.160). Re-trace it without
    .125: lots held ONLY for trees (tree reach: South + the 1996 flood / FEMA flood area + 20 ft of
    the corridor; count which lots no other reason reaches) drop out; the rest stay. Bound, read every gained
    green, release. The reason text on lots still held stops naming trees.
(b) Per-lot entry (new feature, shape WAITS ON STEPH): proposed -- any signed-in teammate can mark a
    lot "trees that may need a tree permit" with a note; the lot shows YELLOW for everyone with the
    note, who entered it and when; anyone can clear it (kept in history, like flag instances).
    Playwright E2E on prod for the lot page.

Left on 137: data/flats/canopy/2026-11-01/ (Metro Canopy 2019 + C-CAP 2021, 3.4 GB, Esri file GDB
rasters; the venv's rasterio cannot open them). Not used; delete when disk is wanted. Leads if a
commercial source is ever wanted: none gathered (Steph: not looking now).
