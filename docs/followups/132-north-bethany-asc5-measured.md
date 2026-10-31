# 132. North Bethany ASC 5 (Park Blocks): screen its two parking rules instead of holding every lot

132. [Claude] [scan: YES] **North Bethany ASC 5 -- measure items 4 and 5, stop holding the area yellow** -- OFFERED 2026-10-30, after 129.

129 (branch flats/nb-maps, 4b80f4ef) traced ASC 5 and holds every lot inside it yellow (FACT-NORTH-BETHANY-PARK-BLOCKS, about 176 lots across R-15 NB, R-24 NB, R-9 NB). The ASC's lot-level requirements (community-plan.north-bethany-subarea.txt#L1995-L2045) are mostly street and block layout (items 1-3, 6), which a pod on an existing lot does not change. Two bind a lot:
- item 4 (L2041-L2043): lots adjacent to the Park Blocks take no vehicle access from the Park Blocks -- an access-line restriction for those lots only;
- item 5 (L2045): "Parking lots between the street and the adjacent buildings are prohibited" -- it sits under "The following requirements apply in the Park Blocks ASC" (L1995), so it binds every lot in the ASC, any street (plain reading; the encoder's question whether it binds only lots facing the Park Blocks is answered by the text, not asked of Steph).

Change: encode item 5 as `parking_front_prohibited` (and side, if a street side counts) behind the ASC 5 drawn area, and item 4 as a no-access line along the Park Blocks couplet (P11/P12) strokes; then the ASC 5 fact no longer holds a lot by itself. Never a false GREEN: a lot the outline cuts stays unanswered. Bound + read the moves (expected yellow -> green or red inside ASC 5 only).
