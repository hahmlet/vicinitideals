# 21. Post-2027 world (Steph 2026-09-29: "design the system for a post-2027 world... retroactively apply that throughout our corpus").

21. [Claude] [Steph: worktree go; HUMAN_TODO 26] [scan: YES for (a)-(c); NO for (d)-(e)] **Post-2027 world (Steph 2026-09-29: "design the system for a post-2027
   world... retroactively apply that throughout our corpus").** Sources
   STORED 2026-09-30 (declared in `_state.yaml`):
   `or/hb.2138.2025.txt` (enrolled); `or/oar.660-046.adopted-2026-08.txt`
   (Division 46 AS ADOPTED 2026-08-27, DLCD's copy; OARD's filed text LCDD
   11-2026 is WRONG, correction hearing 2026-10-22 -- re-fetch after);
   `or/oar.660-047.draft-v5.txt` (Oregon Homes draft v5, 2026-09-22; re-fetch
   after LCDC's October meeting). Worktree, confirm with Steph first.
   (a) OPEN -- STATE LAYER TO ADOPTED DIV 46: quadplex min lot <= the zone's
   detached-house min lot (0220(2)(a)(B)), townhouse likewise (0220(3)(a)) --
   needs a per-zone detached-house minimum lot field read from every zone
   table and a preemption shape "cap at another field's value"; "zoned for
   residential use" (ORS 197A.420(1)(j)) as the scope limit the state layer
   has flagged NOT ENCODED since August; 0205(3) percentage option deleted --
   check whether any corpus city used it. Height floor (2)(d) unchanged; see
   the 2026-09-29 note in _state.yaml (SCR-OTC 20 ft not lifted).
   (b) OUT-OF-COMPLIANCE ZONES -- BUILT (relief `state_middle_housing`,
   discretionary, never GREEN), runs 46 and 49. DECIDED A 2026-09-30
   (Steph: "the 'larger cities' is important"; register
   `2026-09-30-state-middle-housing-path`). Size cutoff: inside Metro every
   city over 1,000 people (all ours but Johnson City, Rivergrove, Maywood
   Park); outside Metro 25,000+ for every type, 2,500-25,000 duplexes only;
   county land only where "urban unincorporated" (ORS 197A.015(12): UGB,
   urban zoning, sewer district, water provider, not a holding zone).
   OPENED 5: Portland RF, Multnomah uninc RF, LR5, LR10, Happy Valley FU10.
   REFUSED 8: Multnomah UF20 + Clackamas FU10 (holding zones, (12)(e));
   RRFF5/RA1/RA2 (rural, (12)(b)); Gresham LDR/GB (Goal 7 hazard,
   0010(3)(c)); Wilsonville RN + FDAHR (pre-2021 master plan,
   0205(2)(b)(B)); Wilsonville RN as townhouses CHECKED shut. Ambiguous 9,
   unruled: Clackamas FF10; Multnomah MUA20, RR, OR, GGR2 (mostly outside
   the UGB); Fairview VTH; Portland RMP; Milwaukie R-MD (unit-lot + flag
   variant); Wilsonville FDAHV. Happy Valley's child-lot refusals look
   allowed by the state rule. Traps from the audit: Clackamas FU10's note
   leaned on an "interim zoning" exemption (0010(2)(c)) that the ADOPTED
   text no longer has; ORS 197A.015 is not stored. CHECK on the weekly run (not recorded
   done): LR10 (MCC 39.4878) and Happy Valley FU10 dimensions were coded
   2026-10-01, and `in_sewer_district` is answered on unincorporated
   Multnomah (`DISTRICT_ONLY`); only Dunthorpe-Riverdale and Clean Water
   Services are sewer districts there and no RF/LR5/LR10 lot is inside
   either -- so those lots should read refused (red): not "urban
   unincorporated" under ORS 197A.015(12)(c). From 2027-01-01 the Div 46
   model code applies directly (0040(4), "completely replaces"): audit the
   corpus, switch them to allowed under the city's middle-housing
   standards or the model code (2020 Exhibit B: front/rear setbacks > 10 ft
   invalid, height < 35 ft / 3 stories invalid, coverage limits invalid).
   (c) OREGON HOMES PATH (HB 2258, OAR 660-047, DRAFT until LCDC's October
   2026 meeting): lots 1,500-20,000 sq ft, residential zone, slope <= 15%,
   outside mapped resource/hazard areas, vacant (teardown < 5 years only with
   DCBS-approved plans); ministerial; 5 ft setbacks, no height cap, parking
   none/<=1 per unit, garage/parking <= 50% frontage, 15% outdoor area, 10%
   slack, min density still applies, <= 2,200 sq ft a unit. A second screen
   path beside the zone path once adopted. Steph's side: HUMAN_TODO 26.
   (d) ELECTIVE LEVERS, recorded not screened: bonus units (+2 on a quadplex
   with one Type A accessible or <=120% AMI for-sale unit; they stay middle
   housing, ORS 197A.420(1)(e)(B); commensurate floor area/height/density, not
   setbacks); keeping an existing house (197A.420(4)); covenants banning
   middle housing void 2027-01-01 (ORS 93.277, 94.776); no traffic study or
   traffic exaction for <= 12 units (197A.420(6)).
   (e) WATCH: Housing Choices rulemaking (HB 2138 §22: siting/design of
   prefabricated middle housing; RAC 1 on 2026-10-07, adoption ~2027-12-02)
   -- item 20's catalog is the baseline; January 2027 drift run (17g).
