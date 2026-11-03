# Historic resource lists

These are source inventories matched to lots for later review; they are not connected to the FLATS screen and do not change any lot result. Matching used the locally available `data/quadfit/s1_lots.parquet` taxlot fabric and situs addresses. That fabric contains Multnomah County lots only, so unmatched resources in other counties remain unmatched.

| File | Listed | address-exact | address-fuzzy | point-in-lot | none | Uncertainty |
|---|---:|---:|---:|---:|---:|---|
| `gresham.csv` | 37 | 25 | 4 | 0 | 8 | Fuzzy rows include two situs address ranges and one street-suffix difference; 1420 SE Roberts has multiple candidate TLIDs, and the NE/NW Overlook direction conflict is left unmatched. |
| `tigard.csv` | 11 | 0 | 0 | 0 | 11 | The named layer's points could not be tested against a Tigard-area lot fabric; the available lots are Multnomah County only. |
| `troutdale.csv` | 11 | 6 | 2 | 0 | 3 | Fuzzy rows are an address range and a listed street-suffix difference; the remaining locations are intersections or cemetery descriptions. |
| `washington-county.csv` | 1 | 0 | 0 | 0 | 1 | Case L9100610 and TLID 1S123AA00100 are documented, but that TLID is absent from the available lot fabric; `tlid` stays blank to preserve the lot-ID validation. |
| `west-linn.csv` | 25 | 0 | 0 | 0 | 25 | The list is the 25 local landmarks only; West Linn lots are outside the available Multnomah County fabric. |
