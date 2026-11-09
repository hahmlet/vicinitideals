# 52. Lots dropped before a fit -- the last zone gap (Clackamas SCMU) closed on flats/dropped-lots-fairview 2026-11-08; the rest is parked with a trigger.

52. [Claude] [scan: YES for SCMU (34 lots, none can go green); NO for the parked rest]
   **Lots dropped before a fit.** History: POD_CANNOT_FIT red by arithmetic 2cfd13d6 (run 65);
   zone codes read 2026-10-09, LIVE runs 69/70 (ef4b272f, b9ced2fe, 9eb9f618); design-review rulings
   in the register (`2026-10-09-*`, `2026-10-14-review-tiers`, `2026-10-16-design-review-default-red`).
   GEOM-UNREADABLE (complex-shape cap) left as is. TRAP: the splice cannot retire lots a re-run drops
   from s3 (assign keeps a measured lot's old row): a bound/splice scope must list them explicitly.

   2026-11-08 (flats/dropped-lots-fairview): a whole-corpus audit found ONE zone FLATS opens that
   quadfit did not hold -- Clackamas SCMU (re-ruled yellow 2026-10-14, after the 2026-10-08 gaps
   were ported), 34 lots, 30 of them yellow NOT_MEASURED in rel4. Ported with its front yard a
   PLACEHOLDER (ZDO 1005.09 keys it to Map 1005-1's street types); FLATS answers it UNKNOWN, so
   none can go green. Lake Oswego's six are ineligible by decision. Separately, Fairview FLX
   (item 84) was the one alias quadfit lacked. Mirror counts left for the coordinator:
   UNEXPRESSIBLE entrance_faces_street 55->56, min_building_height_ft 17->18,
   review_discretion 47->48.

   PARKED, each 0 greens and 0 moves on rel4 (re-checked 2026-11-08); the trigger is when a lot
   is held by that standard ALONE:
   - Milwaukie DMU/GMU street yards across a right-of-way (faces_residential_zone_across_street
     per line, as Portland's street_lines_clear does): DMU 117 / GMU 45 lots, all red -- 69 on
     the minimum density, ~50 on fit, the rest institutional/roll/arithmetic. Building it moves none.
   - Milwaukie Figure 19.304-2 (DMU townhouse area, held behind inside_mapped_use_area) and the
     50 ft Main Street parking ban (no field measures distance to Main St): same DMU lots.
     19.505.5.E.1/G is read (card `19.505.5`, never).
   - Tualatin: Basalt Creek Parkway 50 ft yard (re-measure when the extension is mapped or on
     annexation); RH-HR 45 ft minimum height scope and the 100 ft Wetland Protected Area yard
     (both Table 44-3, RH-HR only: 6 lots, all red on density/roll/arithmetic); Central Tualatin
     Overlay lot sizes for Blocks 26/31/33. Building separation is moot (one building). MUC 57.400
     CLOSED: repealed by Ord. 1438-20 (tualatin.yaml card "57.400"); Figure 57-1 is a 100 ft height
     figure that can only loosen.
   - Fairview TCC: DONE on this branch 2026-11-08 (coordinator extra 2), all three together.
     Figure 19.65.030(B) traced as its complement (flats/config/areas/or/multnomah/fairview/
     outside-storefront-district.geojson, figure held beside it), condition
     `fairview_outside_storefront_district` opens row h's P outside the shading; the TCC block
     carries parking_front_prohibited true (19.65.040(A)(2)(c)(iii) + 19.65.100(A)(2)) and
     parking_side_prohibited false. Of 45 TCC lots: 3 outside (tiny, 208th Pl), 5 cut (held open,
     FACT-FAIRVIEW-OUTSIDE-STOREFRONT-DISTRICT), 37 inside or beyond the frame (refusal stands).
   - SCMU's front yard: Map 1005-1 street types and frontage types (1005.09(G), Table 1005-1),
     and with it 1005.09's minimum building depth and ground-floor height, which do not apply in
     Sectors 1-2 (1005.09(A)) -- also a map. SCMU's density is DONE (min 20, FOLLOWUPS 95).
     2026-11-08 (coordinator extra 1): Map 1005-1 is NOT stored anywhere in the repo (whole-tree
     find; 1005.09.txt L5, L43-L44 name it). NEEDS A DOWNLOAD: the ZDO Section 1005 PDF that
     carries Maps 1005-1 and 1005-2, from https://www.clackamas.us/planning/zdo1005 (the HTML
     page there is text only). Skipped; the 15 ft PLACEHOLDER and FLATS' UNKNOWN stand.
