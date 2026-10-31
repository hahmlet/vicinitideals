# 87. Protected historic buildings outside Portland (found 2026-10-15 by the register audit).

87. [Claude] [scan: YES -- greens only lose] **Protected historic buildings outside Portland (found
   2026-10-15 by the register audit).** Steph's 2026-10-14 ruling (protected historic building on
   the lot = RED) is built only from Portland's historic resource map (Portland + Multnomah uninc).
   Other cities' landmarks and districts (e.g. Oregon City McLoughlin, West Linn Willamette, Milwaukie,
   Lake Oswego when re-enabled) are not screened -> possible false GREEN. Next: find a statewide
   source (Oregon SHPO Historic Sites Database / National Register GIS; ORS 197.772 + OAR
   660-023-0200 decide which listings are "protected"), else per-city maps; apply the standing rule
   (no re-ask), bound, read losses. Standing rule, no question for Steph.

2026-10-31: Washington County also has a Historic Overlay (CDC 373) and it is not screened. Concrete case: taxlot 1S123AA00100 (6050 SW Old Scholls Ferry Rd, R-5), county case L9100610 (1991, approved) "CHANGE FROM INST. W/HISTORIC OVERLAY TO R-5 W/HISTORIC OVERLAY". Live GREEN in run 99 (chunk 7 holds it yellow for ASC U, FOLLOWUPS 136). The county casefile API (api.washingtoncountyor.gov/v1/services/casefiles/search, Referer header) can find historic-overlay cases by taxlot, but a county historic layer is the real source.
