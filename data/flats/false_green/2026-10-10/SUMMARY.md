# False-GREEN sample, round 1 (FOLLOWUPS 64) -- run 70, 2026-10-10

## The number

- 102 green lots drawn at random from the 49,960 greens on the live map (run 70), spread
  across all 19 places that have greens. Each was read blind against the city's own code text.
- **97 right, 4 wrong, 1 can't tell.**
- Weighted up to all greens, about **3.4 % are wrong** (roughly 1,700 lots). With only 4 wrong
  lots found, the honest range is **about 1 % to 10 %** (best single guess 1 in 30).
  If the one can't-tell turns out wrong, the best guess becomes 4.8 %.
- Portland (55 % of all greens): 0 wrong out of 38, one can't tell.
- All 4 wrong lots sit in two places: unincorporated Washington County (2 of 11) and
  Hillsboro (2 of 3). Both are rules the screen does not hold yet, not random misses.

Seed `fgs-2026-10-10-seed1`; query in `work/draw.sql` (lots ranked by
`md5(tlid || seed)` within each city; quotas Portland 38, WashCo unincorporated 11,
Clackamas unincorporated 7, Beaverton 4, Oregon City 3, Gresham 3, every other city 3 or all
it has). The 102 lots with their city totals: `work/sample.psv`. Weights and bands:
`work/consolidate.py`. Every ruling with its reason: `false_green_round1.csv`.
Each reader's evidence per lot: `work/results/A*_notes.md`.

## The four wrong lots

| Lot | Place | What a careful reader finds | Kind |
|---|---|---|---|
| 1S201CC12500 | Washington County (unincorporated), R-5 | The county makes the owner give up land along a "neighborhood route" road, out to 30 ft from the road's centre line. About 3.6 ft must be handed over. The pod has 0 ft to spare, so it no longer fits. | NEW |
| 1N120AD09600 | Washington County (unincorporated), R-6 | Same rule on a local street (25 ft from centre): about 4 ft off the front. Pod has 0 ft to spare and is about 2.5 ft short after the strip comes off. | NEW |
| 1N234AA01800 | Hillsboro, SCR-V | New building here needs a "Type II Development Review", a staff decision with a hearing option, so it is not by-right. Our Hillsboro file has no such gate. | KNOWN (by-right ruling, item 53) in a new city |
| 1S204AB02201 | Hillsboro, MR-2 | Same Development Review requirement. | KNOWN (item 53) in a new city |

Hillsboro is already being fixed on its own lane (branch `flats/hillsboro-review-red`), so no
new item is filed for it.

## How many lots each kind reaches

- **Washington County dedication (new).** Of the 7,711 Washington County unincorporated greens,
  778 (10.1 %) face a road that is at least 2 ft short of the width the code wants. 206 (2.7 %)
  might lose some of their fit once the strip comes off, and 180 (2.3 %) would go red-grade.
  For roads 4 ft or more short: 504, 144 and 134. These are bounds, not a re-screen: the road
  width is measured across the gap between lots, the same way alley width is.
- **Hillsboro Development Review.** 152 of 427 Hillsboro greens are in zones without the
  exemption (MR-2 84, SCR-HD 46, SCR-V 11, MR-3 5, MU-N 3, SCC-MM 2, UC-RM 1). SCR-HD is
  uncertain because of the South Hillsboro plan district.
- **Portland minimum frontage on Map 120-2 (not held).** 902 Portland multi-dwelling greens are
  deeper than 160 ft with less than 90 ft of frontage (RM1 647, RM2 208, RM3 47). The rule only
  bites on lots shown on a map we do not have, so this is an upper bound.

## Existing buildings (policy, counted apart from the real rate)

FLATS ignores buildings already on a lot by design. In the sample 17 of 102 greens carry such a
building (11 commercial or apartment buildings, 6 ordinary houses on lots in Beaverton and
Hillsboro). None is counted as wrong. Across the whole run, about 6 % of greens (about 3,000)
carry a non-house building of 5,000 sq ft or more, and about 1.8 % (about 900) one of 20,000 sq
ft or more. The standout, 1S2E02BB  -01100, is a closed single-tenant Fabric Depot big box
(75,050 sq ft on 6.66 acres): ruled right, not a shopping centre. This feeds Steph's price check
(item 66).

## Open questions and things noticed

- **Can't tell (1):** 1N2E21AD  -06200 (Portland RM1, 50 ft wide, 200 ft deep). Red if the lot
  is on Map 120-2 (needs 90 ft). The map is not in the store. Likely stays can't-tell until it is.
- **59 PUB greens** (public-code zones): not read here; they may belong to item 59's rule for
  public and zero-value land. Treat as a separate question.
- **Judgement call worth confirming:** 1S103DA00700, a single 87 ft frontage on a county
  collector road. Washington County's access-spacing rule (501-8.5 B(3)) lists only commercial
  uses for direct collector access, but the preamble and B(4)(c)(ii) appear to reach housing only
  on lots with more than one frontage. Ruled right; Steph may want to confirm that reading.
- **Gaps in what we hold (not wrong lots, but the places a future wrong green would come from):**
  Portland frontage on maintained streets (33.110.265.E) and Maps 120-2/120-3; Portland
  environmental overlays (33.430) not stored; Wood Village's code is partial (Section 220.330
  townhouse standards missing); Gladstone 17.80 not stored; Tualatin access spacing (TDC 75) not
  stored; Portland's corner flag is unreliable on through lots (harmless in this sample).
- **Thin greens:** several greens pass by 2.5 ft or less (Portland 2.5 ft, Tualatin 0.0 ft,
  Troutdale 0.5 ft, Clackamas 0.5 ft). They are correct under the rules, but any new rule that
  takes even a foot off the envelope will move them.
- **Minimum-density-only greens** (Gresham, Oregon City, Portland commercial zones): green by
  Steph's 2026-10-02 ruling, listed for the record.

## Stopping signal

Round 1 found two new-or-known-in-a-new-place kinds, so this is not yet the "switch to
maintenance" week. Repeat after the dedication and Hillsboro fixes ship.
