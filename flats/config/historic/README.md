# Historic resource lists (FOLLOWUPS 87)

Each CSV holds one city's or county's listed resources and the taxlot each is on.
`protection.yaml` says what that code does with a listing, quoting the stored lines
(`flats/tests/test_historic_lists.py` holds the quotes to them).
`flats/geom/historic_lists.py` puts the answer on the screen:

- **RED** (`historic_listed`): the code clearly makes demolition wait on a hearing
  that can refuse it, the listing is a building, and the address fixes the lot.
- **YELLOW** (`HISTORIC-LISTING-UNSETTLED`): any of those is in doubt.
- A row that names no lot is written to `historic_lists.csv` in every bridge's output
  and counted in the test. It is never dropped.

Run `scripts/flats_match_historic.py <s1_lots.parquet> --write` to fill in taxlots.
Match methods, surest first: `taxlot` (the source names it), `point-in-lot`,
`address-exact`, `address-range` (the number falls in the lot's range, same side of the
street) go red on a protected list. `address-fuzzy` (the suffix or the direction
disagrees) and `address-ambiguous` (several lots; `;` between taxlots) only ever go
yellow.

`point-only` (a state list's point falls in the lot, the address does not agree) also
only ever goes yellow.

## Lists wired to the screen

Paths are under `flats/provenance/docs/or/`.

| List | Reading | What the code says |
|---|---|---|
| `gresham` | protected; 5 objects doubtful | Type III hearing, approve, deny or delay: `multnomah/gresham/5.0300.historic-cultural-landmarks.txt#L319-L326`. Owner objection keeps a resource off the list: `#L141-L143`. Only the owner at designation who objected may have it removed: `#L157-L162`. Objects: `#L368-L371`. |
| `west-linn` | protected | Permit only with approval, on value to the community: `clackamas/west-linn/25.willamette-historic.txt#L518-L526`. Owner consented in writing: `#L218`. The 25 addresses are on the city's page: `clackamas/west-linn/historic-landmarks.city-page.txt`. |
| `troutdale` | protected; 2 trees and 2 cemeteries doubtful | Type III before the Historic Landmarks Commission, on findings: `multnomah/troutdale/6.500.historic-landmarks.txt#L195-L204`. |
| `tigard` | doubtful | Demolition in the overlay zone needs approval (`washington/tigard/tdc.18.755.historic-resources.txt#L81`), but nothing held shows each row of the Historic Sites map carries that zone. |
| `washington-county` | doubtful | Demolition is Type III (`washington/_unincorporated/cdc.373.historic-cultural-resource-overlay.txt#L235-L236`). The owner exemption (`#L287-L291`) rests on ORS 197.772(3), which `oar.660-023-0200.txt#L125-L128` limits to the owner at designation. What remains is that the inventory saying which buildings count (`#L169-L171`) is not held. |

## The state's lists

`state/shpo-<date>/` is the State Historic Preservation Office's Historic Sites layer, and
`state/nps-<date>/` the National Park Service's National Register points, each with a
`SOURCE.json` saying where it came from, the date, what was kept and what was left out.
`scripts/flats_historic_state_build.py` builds them. `protection.yaml`'s `state` section
reads them by class:

| Class | What the layer says | Answer |
|---|---|---|
| `nr-individual` | listed itself, and a building | RED on a sure match |
| `nr-district-contributing` | in a listed district, contributing | RED on a sure match |
| `nr-object` | listed itself, not clearly a building | YELLOW |
| `nr-district-noncontributing` | in a listed district, not contributing | YELLOW |
| `determined-eligible` | found eligible, not listed | YELLOW |
| `surveyed-eligible`, `surveyed-undetermined` | an inventory entry only | YELLOW |

The red rests on OAR 660-023-0200(8): a National Register Resource gets a hearing that can
deny demolition, "regardless of whether the resources are designated", and that applies
directly until the city's code does (`oar.660-023-0200.txt#L113`, `#L119`).

Where a city's list is held it is the authority (Gresham, West Linn, Troutdale, Tigard): a
surveyed entry adds nothing, and a National Register building the list does not carry is
YELLOW. Troutdale's own code reaches National Register resources (`6.500`), so there it
stays RED. Portland has its map, so nothing from the state lands there.

Left out when the file is built, and counted in `SOURCE.json`: an entry found not eligible,
one marked demolished or delisted, a district's single point, cities FLATS does not screen.

## What each local code does

No local list is held for these, so these readings move no lot: the state's lists answer
there, and the `why` travels on the YELLOW. They wait for whoever brings the local list in.
`protection.yaml` holds the cites and quotes.

| Place | Reading | Demolition |
|---|---|---|
| Milwaukie | doubtful | Hearing, but a stay only: after it the permit issues |
| Sandy | protected | Type IV, City Council decides |
| Wilsonville | protected | Prohibited unless its criteria are met |
| Estacada | doubtful | Committee review; may not prevent removal of an uneconomic building |
| Clackamas County | doubtful | Type II; may only suspend |
| Hillsboro | protected | Type III on findings |
| Oregon City | protected | Board may approve or deny. The overlay districts are already held; single landmarks outside them are not |
| Happy Valley | doubtful | Names Goal 5 inventories; no demolition rule stored |
| Beaverton | doubtful | Chapter 40 governs; its landmark sections are not stored |
| Sherwood | doubtful | Landmarks Register defined; the landmark chapter is not stored |
| Tualatin | doubtful | Definition only; the landmark chapter is not stored |

Thin, a passing mention only: Durham 7.9.4.1, Gladstone 17.10.070, and the flood
chapters' definitions in Fairview and Cornelius. Lake Oswego is switched off.
