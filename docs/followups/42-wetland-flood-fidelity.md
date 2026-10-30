# 42. Water, wetland and flood ground at slope's fidelity -- DONE and live.

42. [Claude] [scan: NO new code, check after the weekly run] **Water, wetland and flood ground at slope's fidelity -- DONE and live.**
   Steph asked 2026-10-04 "are we treating wetland/flood zones with as much
   fidelity as we now treat slopes?". Shipped: Portland z RED e55c22ee
   (PCC 33.418.040.B; Steph RULED "red, way in noted", register
   `2026-10-04-portland-constrained-sites-red`); quadfit `flag` overlays +
   FEMA fringe a YELLOW closer look 25d26ce6/2c5b461b; Milwaukie greenway
   RED; DSL wetlands 1c6da420; no-build carves 587b02d1; residue
   5b4ba52e + 799ef7a9 (Portland ezone p/c/v carved, PCC 33.430 -- the 25 ft
   transition area inside p+c stays buildable; Wood Village WVDC 430.170.A;
   Hillsboro CDC 12.27 own map). TRAP for the weekly: it must re-run quadfit
   s5o on this code and acquire `overlay_hillsboro_snro` (pipeline.yaml
   registers it). RULED, never re-offer (register
   `2026-10-06-fema-fringe-stays-yellow`, `-hca-allowance-declined`,
   `-maybe-list-declined`, `-west-linn-fish-bearing-streams`,
   `2026-10-05-landslide-slopes-declined`): FEMA fringe stays YELLOW ("we
   aren't customizing for flood zones"); landslide slopes, the "maybe list"
   (probable wetlands, hydric soils), the HCA disturbance allowance (Steph
   2026-10-06 "Leave it") and West Linn fish-bearing streams (ODFW 65 vs
   100 ft, Steph 2026-10-06 "ignore") all DECLINED. Still open:
   - washington_habitat stays a flag for WashCo uninc, Beaverton, Sherwood,
     King City, Durham (each needs a map or a determination the city holds).
   - Known under-carve: Portland's city-limit transition-area exception
     (33.430.050.A) is not drawn.
   - Left as they were, read: Clackamas WQRA, Happy Valley, Tualatin.
