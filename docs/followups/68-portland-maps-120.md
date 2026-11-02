# 68. Portland Maps 120-2 and 120-3 are not held (found 2026-10-10 by item 64's sample, 1 can't-tell).

68. [Claude] [scan: YES, after Steph or the agent supplies the maps] **Portland Maps 120-2 and 120-3 are not
   held (found 2026-10-10 by item 64's sample, 1 can't-tell).** 33.120.206 bars new homes on a site
   deeper than 160 ft with under 90 ft of frontage, but only on the sites shown on Map 120-2
   (Eastern Portland centres); 33.120.220.C adds a rear-setback rule for Map 120-3 (Eastern Pattern
   Area). Neither map is in the store (portland.yaml ~724), so both are left out and the lots stay
   green. Upper-bound reach: 902 Portland multi-dwelling greens are deeper than 160 ft with under
   90 ft of frontage (RM1 647, RM2 208, RM3 47); how many sit on the map is unknown. Sample lot:
   1N2E21AD  -06200 (RM1, 50 x 200 ft). PROPOSAL: fetch the two maps from the City's open-data
   portal as polygons (or get them from Steph), then add a frontage check and the rear setback with
   a corner exemption. Until then, consider marking these 902 yellow.

MAPS FOUND 2026-11-01 (Copilot scout gpt-6-luna, checked by Claude): both are polygons on
https://www.portlandmaps.com/od/rest/services/COP_OpenData_ZoningCode/MapServer --
layer 1278 "Minimum Required Site Frontage Areas" (its own description: "Zone code map 120-2") and
layer 1279 "Pattern Areas" (TYPE 'Eastern Neighborhoods' = Map 120-3's Eastern Pattern Area; also
some sliver polygons to ignore). No longer waits on anyone: encoder job (fetch both, frontage check
33.120.206, rear setback 33.120.220.C with corner exemption), bound, read losses.

FETCHED 2026-11-01 (Copilot 86aa8ac5, scripts/flats_fetch_area.py): flats/config/areas/or/multnomah/portland/
map-120-2-site-frontage-areas.geojson (4) and map-120-3-pattern-areas.geojson (12). Not wired in yet.

ENCODED 2026-11-01 on flats/pdx-map-120 (37c245ff; hand-off ../vicinitideals-worktrees/pdx-map-120.handoff.md):
90 ft frontage inside the 4 centres (neighbour exception unread = yellow), Eastern rear yard 25% of depth
with parking in half of it. Bound running on 137 (base run 111). QUESTION for Steph, open: "at least 90
feet of frontage on a street" read as ONE street (a corner or through lot cannot add its streets) -- the
stricter reading, shipped as is unless Steph says the streets may be summed.
