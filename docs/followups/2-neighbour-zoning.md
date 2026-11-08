# 2. Neighbour zoning per lot line -- loose ends after the measurement (4b25df09 + the carve fix cfc8c033; run 12 PROMOTED 2026-09-22; Wood Village TC 28850154 and the whole-block answer 86b06340 in run 16; the nine `AHEAD_OF_QUADFIT` zones 0504ef84 in run 14).

2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement
   (4b25df09 + the carve fix cfc8c033; run 12 PROMOTED 2026-09-22; Wood
   Village TC 28850154 and the whole-block answer 86b06340 in run 16;
   the nine `AHEAD_OF_QUADFIT` zones 0504ef84 in run 14).** s4 reads the
   zone across every non-street line; FLATS answers
   `abuts_nonresidential_zone` in Portland / Troutdale / Fairview and
   `abuts_residential_zone` + `abuts_lower_density_zone` in Oregon City (ANY
   line tightens, EVERY line relaxes; anything unresolved stays UNKNOWN).
   2026-11-08 branch `flats/neighbour-zoning` (off rescreen-1110 0f2620b3):
   (a) DONE on the branch, AWAITS ITS BOUND: Oregon City R-2 Table 17.12.040
   note 1 encoded (side 10 + parking strip 10 when `abuts_lower_density_zone`,
   both plats; OC declares the fact, true_for R-10/R-8/R-6). Item 43's
   easement ruling was what changed it: note 2's `utility_easement` cap is
   answered by the bridge since 2026-10-05, so note 1's cap had become the
   only thing holding every R-2 lot. quadfit rules.yaml left at side 5 (FLATS
   cuts its own envelope; see the hand-off). (d) CHECKED: from RICAP 11
   (2026-11-01) a CI1 home takes RM1's setbacks, which carry no neighbour
   lever, so the OS problem is CI2's alone; the old guard read the codified
   block's caps and passed vacuously after Nov 1 -- a second guard now
   resolves CI1/CI2 on the law in force. Still owed, most lots first:
   (c) 1,938 lots in the turning zones still lean on the fact (September
   count; re-count on 137): 813 a blank point across a line (park / ROW /
   fabric gap), 802 no non-street line at all (ANSWERED 86b06340 where s4
   traced the lot and it is not irregular: 1,565 lots; the tier-C and
   untraced ones stay unanswered), 272 a split-zone neighbour, 46 both, 5 a
   neighbour in another city. `abuts_park` BUILT a89a3b9b from RLIS ORCA
   (live in run 42; only Troutdale conditions on a park in the corpus). ORCA
   was never acquired into snapshot 2026-09-18 -- check whether the run-111
   county refresh acquired it (`rlis_orca` is registered in pipeline.yaml).
   (d) CI2 still needs its own list and the across-the-street reading
   (33.910) if its `site_specific_limitation` cap ever lifts (guard tests).
   (e) Troutdale's 5 ft side against HDR is unread -- SIZED 2026-09-23: at
   most 13 MU lots see an HDR neighbour, the unread half only relaxes
   (7.5/15 -> 5), and reading it needs a fourth neighbour fact ("every line
   non-residential OR HDR"); recommend leaving it unless those lots come up.
