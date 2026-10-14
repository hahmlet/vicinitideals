# False-GREEN sample, round 2 (FOLLOWUPS 64) -- run 74, 2026-10-14

## The number

- 108 green lots drawn at random from the 50,956 greens on the live map (run 74), spread
  across all 22 places that have greens. Each was read blind against the city's own code text,
  by the round 1 method (same reading protocol, same weighting).
- **97 right, 7 wrong, 4 can't tell.**
- Weighted up to all greens, about **5.5 % are wrong** (roughly 2,800 lots). With 7 wrong lots
  found, the honest 95 % range is **about 1.7 % to 14.6 %**. If all 4 can't-tells turn out
  wrong, the best guess becomes 8.0 %.
- Portland (54 % of all greens): 1 wrong and 1 can't tell out of 30.
- **Both rounds pooled** (207 lots, 9 wrong, round 1's Hillsboro lots left out because those
  zones are now red): **3.9 %, range 1.5 % to 8.9 %.** This is the steadier number to quote.

| | Round 1 (run 70, 2026-10-10) | Round 2 (run 74, 2026-10-14) |
|---|---|---|
| Greens on the map | 49,960 | 50,956 |
| Lots read | 102 | 108 |
| Right / wrong / can't tell | 97 / 4 / 1 | 97 / 7 / 4 |
| Weighted wrong rate | 3.4 % | 5.5 % |
| 95 % range (same method both rounds) | 0.3 % to 9.6 % | 1.7 % to 14.6 % |
| Places with a wrong | WashCo uninc., Hillsboro | WashCo uninc., Oregon City, Sherwood, King City, Portland |
| New kinds found | 1 (road land, WashCo) | 1 (Portland overlay zones) |

**The two rounds agree within their ranges; the rate has not moved.** Round 1's Hillsboro
wrongs were fixed (run 73), and round 2 found the same two rule gaps again, plus the road-land
gap in three more cities. Counting only the places round 1 sampled, round 2's rate is 5.6 %.
The three cities new since round 1 (Tigard, Cornelius, Estacada; 18 lots read, oversampled)
had **no wrong lot**.

Seed `fgs-2026-10-14-seed2`; query in `work/draw.sql` (lots ranked by `md5(tlid || seed)`
within each city; quotas Portland 30, WashCo unincorporated 15, Tigard 8, Clackamas
unincorporated 6, Cornelius 6, Hillsboro 6, Beaverton 4, Estacada 4, Oregon City 3, Gresham 3,
every other city 2 or all it has). The 108 lots with their city totals: `work/sample.psv`.
Weights and ranges: `work/consolidate.py` (the range is an exact binomial range on the
weighted sample's effective size, about 67 lots; round 1 is recomputed the same way, which is
why its range reads 0.3 %-9.6 % here instead of the "about 1 %-10 %" in its own summary).
Every ruling with its reason: `false_green_round2.csv`. Each reader's evidence per lot:
`work/results/B*_notes.md`. Three lots were also drawn in round 1 (the two Happy Valley lots and
the one King City lot); they were read again blind.

## The seven wrong lots

| Lot | Place | What a careful reader finds | Kind |
|---|---|---|---|
| 1N223DA11500 | WashCo uninc., R-5 | NW Rock Creek Blvd is a collector: the owner must give land out to 37 ft from the centre line. The road is about 60 ft wide, so about 7 ft comes off the front. The pod has about 5 ft to spare, so it misses by about 2 ft. | KNOWN-67, same place |
| 2S116AA14200 | King City, R-9 (county zoning still applies) | A 46 ft street needs 25 ft from the centre line: the side yard grows 2 ft, and the pod had 1 ft to spare. King City's own code (16.80.060 A) says the same. Round 1 ruled this lot right; it missed the road rule. | KNOWN-67, new place |
| 2S132CD12600 | Sherwood, LDR | Sherwood adds a setback out to 32 ft from the centre line on a neighbourhood route (16.106.040 D). The road is 51.5 ft wide, so the front yard moves 6.25 ft; the pod was already 0.5 ft tight. | KNOWN-67, new place |
| 2S132AC01500 | Sherwood, LDR | Same Sherwood rule on a 41 ft road: the front yard moves about 11.7 ft, and steep ground behind leaves both designs short. | KNOWN-67, new place |
| 31E01DA00229 | Oregon City, R-10 | New middle housing must give the land the transport plan asks for (16.12.011.B). South End Rd is a minor arterial with a 100 ft plan width; it is about 59 ft today, so about 20 ft comes off the lot. The building misses by about 5 ft, and the lot drops under the 10,000 sq ft minimum. | KNOWN-67, new place |
| 1S103DA00200 | WashCo uninc., transit district TO:R18-24 | Middle housing gets the quick staff-only path only on a platted lot of at most 10,000 sq ft buildable area (375-7 30.c). This lot is about 21,400 sq ft, so its only path is a Type II review: the same kind of review Steph ruled red for Hillsboro. | KNOWN-53 (review-only path), new place |
| 1S1E22BA  -02300 | Portland, CM2 | The city map puts the lot in the "Main Street" overlay, which requires new buildings to have floor area of at least half the lot area (33.415.310.A). The pod's 4,032 sq ft on an 8,907 sq ft lot is 0.45, short by about 420 sq ft. FLATS holds none of Portland's overlay zones. | **NEW** |

Both Sherwood rulings take the road's class from the county's road-class map, because Sherwood's
own map is not stored. If either road is really a local street, that lot may flip back.

## How many greens each kind reaches (weighted from the sample, then measured where we can)

- **Road land to the centre line (item 67's kind), now in four places.** About 2.7 % of all
  greens (about 1,360 lots) by the sample's weights. Item 67's built-but-unshipped fix covers
  only unincorporated Washington County (its bound: 1,491 red + 98 yellow of 7,728 there).
  Sherwood, King City and Oregon City are outside it, and readers saw the same kind of rule,
  not encoded, in Tigard (18.210.030.A.1, setbacks from the future street edge), Milwaukie
  (extra street yards from the centre line, Table 19.501.2.A) and Beaverton (dedication left to
  the decision-maker). Not measured outside WashCo: there is no road-width or road-class fact
  per lot in the database.
- **Portland overlay zones (new).** About 1.8 % of greens (about 920 lots) by the sample's
  weights, but that rests on one lot. Upper bound for the Main Street floor-area rule alone:
  of Portland's commercial-zone greens, 3,690 are over 8,064 sq ft (where the pod falls below
  half the lot area); how many sit in the overlay and in the Inner area is not known, because
  the overlay map is not held. The same readers found other overlays and plan districts unheld
  that changed no lot here: Glendoveer (30/10/15 ft setbacks), Macadam (wall-plane setbacks),
  the design overlay, and conservation districts.
- **Washington County Type II-only lots (review-only kind, new place).** The county's
  quick path stops at a lot size in every zone: 16,500 sq ft (R-5) and 13,100 sq ft (R-6), then
  allowed only if four homes meet the minimum density; 10,000 sq ft in R-9, R-15, R-24, R-25+
  and the transit districts, which also need the lot to come from a standard subdivision or
  partition plat. By lot size alone (buildable area not subtracted), **405 of the 7,708 WashCo
  greens** have only the Type II path: R-24 158, R-15 86, R-9 45, R-5 39, R-6 34, R-25+ 21,
  transit districts 22. Lots not created by a standard plat add more (not measurable here). Our
  file allows Type II on purpose and notes it as a doubt (_unincorporated.yaml ~566-571,
  ~1538-1544); Steph's Hillsboro ruling (item 69) says a Type II review is red.

## Existing buildings (policy, counted apart from the real rate)

Steph ruled 2026-10-14 that a lot with an existing building stays green. 13 of 108 greens carry
a note: an occupied Tigard apartment complex ($14.3M across two tax lots), commercial buildings in
Portland (up to 16,056 sq ft), Estacada and Wood Village, small plexes in Portland and Gresham,
and a probable apartment tax lot in Hillsboro. None is counted wrong. Across the whole run,
2,801 greens (5.5 %) carry a non-house building of 5,000 sq ft or more, and 914 (1.8 %) one of
20,000 sq ft or more, much as in round 1.

**One policy lot needs Steph's ruling:** 1N1E22CB  -01200 (Portland RM1). Its 1910 house is a
*protected* ("contributing") building in the Mississippi Conservation District. Removing it needs
a demolition review, and that also closes the by-right design-standards path. Ruled right under
the existing-building policy; red if a protected building is not treated like an ordinary one.

## Can't tell (4)

- 1N2E24CD  -09200 (Portland RM1, 126.8 ft deep). Red or yellow if it is on the Eastern Pattern
  Area map (rear setback 31.7 ft, at most half of it parking; the drawn court covers 54.5 %).
  The map is not held (item 68).
- 31W15DC05351 and 31W22DC01400 (Wilsonville PDR-2 and PDR-4). Every number passes and the
  permit is staff-only, but parking and turning areas may cover at most half of any street
  frontage (4.113(.14)D.3). The rear courts are about 70 and 50 ft wide against caps of 43 and
  34.5 ft. The words do not say whether a court behind the building counts. **Steph to rule.**
- 1N3E34B   -00807 (Wood Village TC). Clears every number, but building in the Town Center goes
  through a "Town Center Development Plan", which the code says replaced the old "Master Plan".
  The approval type is in sections 235.400/235.490, which are not stored and refuse every fetch
  (403). Red if that approval is a discretionary review (would reach all 10 TC greens).

## Things noticed (no lot changed colour on them)

- **The same "half of the street frontage" parking cap appears in four cities** (Wilsonville
  4.113(.14)D.3, Hillsboro 12.50.715 C.1, Clackamas ZDO 845.02(D), Beaverton). The screen applies
  it only to parking beside the building, never to a rear court facing a second street or one
  seen behind the building. It decides the two Wilsonville can't-tells, and drawn courts break it
  on several right lots where a smaller legal court fits.
- **Hillsboro SCR-MD / SCR-HD 5 ft maximum side setback** (12.22 table, ~L1132 and ~L1424) is not
  held. Read as "one wall within 5 ft" (12.50.130.C.3.a) every lot passes; read as "both side
  walls within 5 ft" nearly every SCR-MD and SCR-HD green turns red. **Steph to rule.**
- **Estacada is charged too few parking stalls.** It is under 25,000 people and outside Metro, so
  the state cap of one stall per home does not apply; its own code wants 1.5 per home, 6 stalls
  (emc.16.76.txt:77-78). Every Estacada green still seats 6 or more except 34E17D 00700, which
  seats 5 with room for more. A wrong number that has not yet made a wrong green.
- **Drawings that break a rule while another layout passes:** a court between the building and
  a side street (Portland 1S2E11DB  -03505), a building drawn 37 ft back where the code wants it
  within 10 ft of the busiest transit street (Portland 1N2E32DD  -11000), a cul-de-sac court with
  no lane (Beaverton 1N131BD01100). The colour stands; the picture is not a legal plan.
- **Corner and street gaps seen again:** side-street parking caps and maximum front setbacks are
  not checked; Troutdale's code says access from the lowest-class street but our file says it
  names none; Hillsboro corners carry no street ranking; one spurious corner (KNOWN-63).
- **Split-zoned lot (cross-check with item 76(b)).** Estacada 34E17  02000 is only 47 % NCR. The
  drawn building sits mostly in the CMU part, but a pod placed inside the NCR band fits, so the
  reader ruled it right. Item 76(b) holds the open ruling on split-zoned lots; that ruling could
  move this lot.
- **Thin passes:** a WashCo court at 4.95 % grade against a 5 % cap; a Cornelius minimum density
  met by 0.02 homes per acre; a Wilsonville fit at 0.5 ft tight.
- **The flag table is stale.** `flats.flag_instances` was last refreshed at run 70 (no row seen
  after run 70), so Tigard lots still carry a JURISDICTION-OFF flag there. The run 74 results
  themselves carry the right flags; the lot page or anything else reading the table may not.

## Fixes between the rounds: share of greens moved (the log item 64 asks for)

Run 70 (49,960 greens) to run 74 (50,956), same county map copy, lot by lot:

| Fix | Greens lost | Share of run-70 greens | Greens gained | Kind |
|---|---|---|---|---|
| Hillsboro Development Review red (item 69, run 73) | 152 | 0.30 % | 0 | Known kind (53) in a new place, found by round 1 |
| Unranked corner street yellow (item 60, run 73) | 3 | 0.006 % | 0 | Known kind |
| West Linn water / resource site flag (item 50, run 73) | 1 | 0.002 % | 0 | Known kind |
| Portland flag severity 0 (run 73) | 0 | 0 | 1 | -- |
| Tigard switched on (item 51, run 73) | 0 | 0 | 829 | New territory |
| Cornelius switched on (item 51) + elevation restored (item 75, run 74) | 0 | 0 | 308 | New territory |
| Estacada by-right (item 53, run 73) | 0 | 0 | 14 | New territory |
| Placement cache (item 74) | 0 | 0 | 0 | -- |
| **All hunting fixes** | **156** | **0.31 %** | | |

Not shipped yet, so not in the log: item 67 (WashCo road land) moves about 1,589 WashCo greens
(3.2 % of all greens) by its own bound.

## Stopping signal

**Not met.** The fixes that shipped this week moved 0.31 % of greens, under the 0.5 % line. But
the sample found one new kind (Portland overlay zones) and two known kinds in five new places,
and the shipping of item 67 alone will move about 3 % of greens. Repeat after item 67 ships and
after Portland's overlays and the road-land rule in the other cities are decided.
