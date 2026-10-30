# 62. Roof shape: teach the screen gable vs flat (offered 2026-10-09 after Steph asked what a gable costs in height; nothing signed).

62. [Steph] [scan: YES] **Roof shape: teach the screen gable vs flat (offered 2026-10-09
   after Steph asked what a gable costs in height; nothing signed).** The
   design holds ONE height (26 ft) compared straight to every cap, so it
   cannot tell a gable from a flat roof. Corpus read 2026-10-09: a gable is
   measured at its MIDPOINT (eave-to-ridge average) in Portland, Beaverton,
   Tigard, Hillsboro, Cornelius, Sherwood, WashCo, MultCo, Fairview, Oregon
   City, Gladstone, Wilsonville, Troutdale (IBC "average height of highest
   roof surface"), Milwaukie (<=12:12; steeper = peak), ClackCo (defers to
   the state building code, text not stored); at the PEAK in Gresham
   (3.0100 "highest point of the structure"), West Linn 41.005, Happy
   Valley 16.12, King City 16.24; no stored definition for Tualatin, Wood
   Village, Durham, Rivergrove. Shed roofs steeper than flat (2:12 PDX/
   Tigard, 4:12 Beaverton) = highest point. Build: Design gets eave_ft +
   ridge_ft + roof form; a per-layer `height_measured_to` (midpoint / peak
   / unknown -> peak); max/min height checks read the measured figure;
   Gresham 7.0420(G) and Milwaukie side planes read the roof profile
   facing the line. Then `flats.encode.height` prices each roof option.
   Current curve (426,106 lots): only exactly 25 ft keeps everything; 26
   loses Hillsboro's 2-1/2-storey zones (~23,500); >30 loses Portland
   R5/R7/R10/R20 (~148,700 total); >35 loses ~371,600. Wait for a drawing
   with real eave/ridge figures before building.
