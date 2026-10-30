# 2. Neighbour zoning per lot line -- loose ends after the measurement (4b25df09 + the carve fix cfc8c033; run 12 PROMOTED 2026-09-22; Wood Village TC 28850154 and the whole-block answer 86b06340 in run 16; the nine `AHEAD_OF_QUADFIT` zones 0504ef84 in run 14).

2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement
   (4b25df09 + the carve fix cfc8c033; run 12 PROMOTED 2026-09-22; Wood
   Village TC 28850154 and the whole-block answer 86b06340 in run 16;
   the nine `AHEAD_OF_QUADFIT` zones 0504ef84 in run 14).** s4 reads the
   zone across every non-street line; FLATS answers
   `abuts_nonresidential_zone` in Portland / Troutdale / Fairview and
   `abuts_residential_zone` in Oregon City (ANY line tightens, EVERY line
   relaxes; anything unresolved stays UNKNOWN). Still owed, most lots first:
   (a) `abuts_lower_density_zone` is declared in Clackamas `_unincorporated`
   only (ZDO Table 315-4 note 14 = the 10-ft variant on MR1/MR2
   `setback_side_ft`). An observed fact lifts a caps.json cap and the base
   number would certify with the footnote's other number never encoded
   (`test_no_declared_condition_caps_a_value_on_that_layer`), so the city
   still capped stays undeclared: Oregon City R-2 (twelve fields; the note
   narrowed to `zones: [R-2]` 2026-09-22) is a dead end until
   `utility_easement` is read, because every OC R zone is capped on THAT
   fact on every field too (no easement layer in RLIS -- a measurement
   question, not an encoding one). Unchecked: whether item 43's PUE
   street-yard rule (a9106379, Oregon City since 2026-10-05) changes this.
   (c) 1,938 lots in the turning zones still lean on the fact: 813 a blank
   point across a line (park / ROW / fabric gap), 802 no non-street line
   at all (ANSWERED 86b06340 where s4 traced the lot and it is not
   irregular: 1,565 lots; the tier-C and untraced ones stay unanswered),
   272 a split-zone neighbour, 46 both, 5 a neighbour in another city.
   `abuts_park` BUILT a89a3b9b from RLIS ORCA (live in run 42; only
   Troutdale conditions on a park in the corpus). ORCA was never acquired
   into snapshot 2026-09-18 -- acquire it at the next county refresh
   (`rlis_orca` is registered in pipeline.yaml).
   (d) Portland CI1/CI2: 33.150 gives a CI lot 10 ft against OS, so the
   shared Portland list is wrong for CI home lots -- safe only while CI
   stays capped on `site_specific_limitation` (guard test); a per-zone list
   and the across-the-street reading (33.910) when that cap lifts. Note:
   RICAP 11 opens CI1 on 2026-11-01 (item 86) -- check this guard then.
   (e) Troutdale's 5 ft side against HDR is unread -- SIZED 2026-09-23: at
   most 13 MU lots see an HDR neighbour, the unread half only relaxes
   (7.5/15 -> 5), and reading it needs a fourth neighbour fact ("every line
   non-residential OR HDR"); recommend leaving it unless those lots come up.
