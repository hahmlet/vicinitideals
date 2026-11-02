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


SCOUT 2026-11-01 (Copilot gpt-6-luna, 3.4 AI units; searched the ArcGIS catalog only, not city code
pages): statewide sources confirmed live -- SHPO public GIS
https://maps.prd.state.or.us/arcgis/rest/services/Cultural/HistSites_GIS_FeaturesOnly/FeatureServer/0
(72,269 points, city/address fields; an INVENTORY, not designation-only -- needs a designation field
or the ORS 197.772 filter) and NPS National Register
https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer
(National Register only). City layer found: Tigard Historic Sites
https://services1.arcgis.com/d9Fl2w84c4Vbf9kI/arcgis/rest/services/City_of_Tigard_Historic_Sites/FeatureServer/0
(11 points). No ArcGIS layer for the other 24 cities / two counties; their local landmark lists
are probably in code text or PDFs (not searched).

LOCAL LISTS SCOUT 2026-11-01 (Copilot gpt-6-luna, 4.6 AI units; code section numbers mostly INFERRED
from search results, check the stored code): lists found -- Lake Oswego Landmark List
https://www.ci.oswego.or.us/planning/landmark-designation-list (72, by address; city switched off);
West Linn https://westlinnoregon.gov/planning/historic-landmarks (25, by address, CDC 25); Gresham
https://www.greshamoregon.gov/Historic-and-Cultural-Landmarks-List/ (two inventory PDFs, 2017; CDC
5.0300); Hillsboro Cultural Resource Inventory https://apps.hillsboro-oregon.gov/Historical_Landmarks/Documents/57.pdf
(12.27.300 overlay); Tualatin https://old.tualatinoregon.gov/planning/historic-preservation (Ch. 68,
22 left, 1992-93); Forest Grove https://www.forestgrove-or.gov/567/Historic-Properties (1993 survey
of 300+, NOT the designated count); Milwaukie (MMC 19.403, inventory linked from the historic
resources page); Wilsonville Old Town Overlay (4.138, an area); Canby Ord. 1584; Happy Valley memo
(Pleasant Valley / North Carver only). Unknown: WashCo CDC 373 list, Beaverton (60.45 maybe
repealed), Cornelius, Sherwood, King City, Durham, Clackamas ZDO 707, Gladstone, Sandy, Estacada,
Molalla, Troutdale, Fairview, Wood Village -- check the stored code text for a landmark section
before calling any of them none. Next: Claude reads the stored code per city (is listing
protective by itself? ORS 197.772 owner consent), then address/taxlot match, bound, read losses.
