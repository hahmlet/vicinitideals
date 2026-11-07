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

## Lists wired to the screen

Paths are under `flats/provenance/docs/or/`.

| List | Reading | What the code says |
|---|---|---|
| `gresham` | protected; 5 objects doubtful | Type III hearing, approve, deny or delay: `multnomah/gresham/5.0300.historic-cultural-landmarks.txt#L319-L326`. Owner objection keeps a resource off the list: `#L141-L143`. Only the owner at designation who objected may have it removed: `#L157-L162`. Objects: `#L368-L371`. |
| `west-linn` | protected | Permit only with approval, on value to the community: `clackamas/west-linn/25.willamette-historic.txt#L518-L526`. Owner consented in writing: `#L218`. The 25 addresses come from the city's web page, which is not stored. |
| `troutdale` | doubtful | Standards apply to listed landmarks (`multnomah/troutdale/4.200-4.230.historic-landmark-protection.txt#L13-L15`), but no demolition standard is in the stored text. |
| `tigard` | doubtful | Chapter 18.755 is named (`washington/tigard/18.660/18.660.030.txt#L34`) and not stored. The list is the city's Historic Sites map. |
| `washington-county` | doubtful | Demolition is Type III (`washington/_unincorporated/cdc.373.historic-cultural-resource-overlay.txt#L235-L236`), but an owner may be exempted by a Type I (`#L287-L291`) and the inventory saying which buildings count (`#L169-L171`) is not held. |

## Protective code, no list held

These lots are NOT screened for a listed building, so a false GREEN is still possible.
Nothing is wired until a list is held. The reading is a first pass, for whoever brings
the list in.

| Place | Section | Demolition | Cite |
|---|---|---|---|
| Milwaukie | 19.403 | Hearing, but a stay only: after it the permit issues | `clackamas/milwaukie/19.400.overlays.txt#L2782-L2786` |
| Sandy | 17.62 | Type IV, City Council decides | `clackamas/sandy/17.62/17.62.80.txt#L27` |
| Wilsonville | 4.171(.09)-(.10) | Prohibited unless found harmless or no reasonable use | `clackamas/wilsonville/4/4.171.txt#L105-L109` |
| Estacada | 16.48 | Committee hearing; may not prevent removal of an uneconomic building | `clackamas/estacada/16.48/16.48.060.txt#L3-L15` |
| Clackamas County | ZDO 707 | Type II; may be suspended | `clackamas/_unincorporated/zdo.707.txt#L334` |
| Hillsboro | 12.27.300 | Type III; owner may refuse at designation | `washington/hillsboro/12.27/12.27.370.txt#L6` |
| Oregon City | 17.40.070 | Board hearing. The overlay districts are already held; single landmarks outside them are not | `clackamas/oregon-city/17.zoning.txt#L9232` |
| Happy Valley | 16.25.005 | Names Goal 5 inventories; thin | `clackamas/happy-valley/16.25/16.25.005.txt#L528` |
| Beaverton | 70.15.10 | Chapter 40 governs, not stored; 60.45 is repealed | `washington/beaverton/bdc.70.downtown.txt#L480-L484` |
| Sherwood | 16.10.020 | Landmarks Register defined; the landmark chapter is not stored | `washington/sherwood/16.10/16.10.020.txt#L76-L77` |
| Tualatin | 31.060, 52.100 | Chapter 68 not stored | `clackamas/tualatin/31/31.060.txt#L119` |

Thin, a passing mention only: Durham 7.9.4.1, Gladstone 17.10.070, and the flood
chapters' definitions in Fairview and Cornelius. Lake Oswego is switched off.
