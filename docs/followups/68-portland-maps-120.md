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
stricter reading, shipped as is unless Steph says the streets may be summed. 2026-11-03: Steph asked for the source -- sent PCC 33.120.206.C.1, page 120-11 of https://www.portland.gov/sites/default/files/code/120-md-zones_3.pdf; RULED 2026-11-04 ONE STREET (2026-11-04-pdx-site-frontage-one-street) -- as shipped.
BOUND 2026-11-02 (137 /root/pdx_map_120, bundle /root/bundle_pdx_map_120): 1,245 moves. Expected: green->red
272, green->yellow 271, yellow->red 33. NOT expected: red->yellow 663 (RULE_AMBIGUOUS; lots that failed fit,
coverage or fire access) and yellow->green 4 (1N2E20BB -00900, 1N2E25BA -00600, 1N2E28AD -01600,
1N2E35DC -00200). Sent back to the encoder to fix on the branch; re-bound after. Do not release this bound.
RE-BOUND 2026-11-02 at 5e072374 (/root/pdx_map_120b, bundle /root/bundle_pdx_map_120b): 582 moves, the red->yellow
group is gone. green->red 272, green->yellow 271, yellow->red 33, yellow->green 4 (same four; each lost only
SLOPE-GRADE -- likely the deeper rear yard moves the building onto flatter ground; confirm in the read).
NEXT: move read (flats-move-reader), then release. Not started: after the 2026-11-03 reset.
READ 2026-11-04 (flats-move-reader, scratch /root/pdx_map_120b_rd/ on 137): DO NOT MERGE. No false GREEN; the 4 gains are right
(flatter ground). Wrong: (A) 60+ false REDs -- the 25% EPA rear setback taken from every rear-labelled edge (notch steps),
not only the line most distant from the front (PCC 33.910), e.g. 1N2E23DA -00700, 1S2E20DB -04000, 1N2E20BA -00500;
(B) 14 corner lots held yellow by a depth band on the corner variant (corners exempt at any depth; list mv12.csv);
(C) 3 lots RED on an assumed "not a corner" (1N2E22AD -03701, 1S2E01CD -01800, 1S2E04DC -03600) -- standing rule: hold YELLOW;
(D) cosmetic frontage flag on exempt <=160 ft lots. Watch 1N2E35DC -00200 (0.25 ft fit margin, 4.88% grade) in the re-read.
ROUND 3 building by Copilot in the worktree (brief docs/copilot/briefs/pdx-map-120-r3.txt), then re-bound + re-read.
QUESTION for Steph 2026-11-04 (open): "No more than 50 percent of the Eastern Pattern Area rear setback can be vehicle area"
(33.120.220.txt#L24) -- read today as half the yard's DEPTH across the whole lot (strict; turns some lots red). The text says
half the setback, which reads as half its AREA (parking could fill the full depth over half the width). RULED 2026-11-04 (2026-11-04-pdx-epa-rear-parking-half-area): half the AREA -- build after round 3 (round 4).
