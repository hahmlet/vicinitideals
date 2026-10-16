# Quote-mismatch report, 2026-10-16

Report only; nothing under `flats/` changed.

## What the 409 actually is

`python -m flats.encode.gaps` prints "N citation(s) name a section their quoted text is not in" at `flats/encode/gaps.py:462`. It counts `misattributed` rows from `flats/encode/attribution.py::check`. It is **not** a text-not-found check. A "quote" in this corpus is a pointer (`path#L12-L18`), not quoted words, so every quote resolves. The check reads the section back off the document (heading or running header above the cited lines) and compares it with the section number named in the citation's `cite` string. Disagreement is reported, never repaired (module docstring).

The requested causes (a)-(e) are therefore re-framed around "the cite names section X; the lines read as section Y". Throwaway script (not committed) classifies each of the 409 rows from a fresh `gaps.json` snapshot, in this order:

- (a) a claimed section number is printed in the cited lines themselves (after normalising spaces, hyphens, quotes, section marks). The reader took the wrong running header or heading, or the cited lines merely cross-reference the claimed section.
- (b) the claimed section has a heading in the same stored file, outside the cited lines. Possibly the lines are wrong, possibly the cite is.
- (c) the claimed section has a heading only in a different stored file.
- (d) the claimed section number appears nowhere in the stored corpus.
- (e) other.

Heuristic: (a) cannot tell a real match from a cross-reference, and (b) cannot tell which of cite or lines is wrong. Hand review is needed before acting.

| cat | count | meaning |
|---|---|---|
| (a) | 286 | claimed section is printed in the cited lines (misread running header) |
| (b) | 113 | claimed section heading elsewhere in same file |
| (c) | 10 | claimed section heading only in another stored file |
| (d) | 0 | claimed section number nowhere in corpus |
| (e) | 0 | other (claimed section only mentioned, never a heading / no claim) |
| total | 409 | |

| jurisdiction | a | b | c | d | e | total |
|---|---|---|---|---|---|---|
| or/clackamas/estacada | 0 | 2 | 0 | 0 | 0 | 2 |
| or/clackamas/gladstone | 0 | 3 | 0 | 0 | 0 | 3 |
| or/clackamas/oregon-city | 0 | 5 | 0 | 0 | 0 | 5 |
| or/clackamas/west-linn | 0 | 9 | 0 | 0 | 0 | 9 |
| or/multnomah/_unincorporated | 1 | 0 | 0 | 0 | 0 | 1 |
| or/multnomah/fairview | 0 | 12 | 0 | 0 | 0 | 12 |
| or/multnomah/gresham | 1 | 1 | 0 | 0 | 0 | 2 |
| or/multnomah/troutdale | 0 | 7 | 0 | 0 | 0 | 7 |
| or/multnomah/wood-village | 0 | 0 | 10 | 0 | 0 | 10 |
| or/washington/beaverton | 71 | 12 | 0 | 0 | 0 | 83 |
| or/washington/hillsboro | 123 | 0 | 0 | 0 | 0 | 123 |
| or/washington/king-city | 0 | 1 | 0 | 0 | 0 | 1 |
| or/washington/sherwood | 1 | 43 | 0 | 0 | 0 | 44 |
| or/washington/tigard | 89 | 18 | 0 | 0 | 0 | 107 |

### (a)
- `or/multnomah/_unincorporated/39.cfu.txt#L85-L86,L92-L93,L115-L116,L130-L137,L386` (or/multnomah/_unincorporated CFU.quadplex_allowed) cites 39.4065 39.4060 39.4070, text read as 39.4060 39.4065 39.4075; first cited line: "Heritage Tract Dwelling - A type of single"
- `or/multnomah/gresham/9.0800.parking.txt#L66-L70,L302,L319-L327,L340-L343,L355-L357` (or/multnomah/gresham (defaults).parking_alley_backout_ft) cites 9.0825 9.0825, text read as 9.0802 9.0825; first cited line: "F.                               By definition, parking lot design standards (Sections 9.0822 to 9.0840) do no"
- `or/washington/beaverton/bdc.20.10.commercial.txt#L38,L41-L49,L186,L188,L195-L198` (or/washington/beaverton CC.max_far) cites 20.10.16, text read as 20.10.15; first cited line: "20.10.15 Commercial Site Development Standards"
### (b)
- `or/clackamas/estacada/emc.16.116.txt#L31` (or/clackamas/estacada (defaults).corner_access_street) cites 16.116.020, text read as 16.116.010; first cited line: "3 When a lot or parcel abuts two or more streets of different classifications under EMC 16.116.030, the lot or"
- `or/clackamas/gladstone/17.06.definitions.txt#L881,L921` (or/clackamas/gladstone (defaults).front_lot_line_through) cites 17.06.290, text read as 17.06.290 17.06.310; first cited line: "“Front lot line” means a lot line separating a lot from a street other than an alley. In the case of a corner "
- `or/clackamas/oregon-city/17.zoning.txt#L4184-L4186` (or/clackamas/oregon-city R-10.min_density_du_per_acre) cites 17.08.020 17.08.040 17.16.060, text read as 17.08.050; first cited line: "Table 17.08.050"
### (c)
- `or/multnomah/wood-village/230.310.txt#L64-L65,L70,L86` (or/multnomah/wood-village NC.max_height_ft) cites 230.200 710.100, text read as 230.310; first cited line: "Table 230-2. Development Standards in Commercial Zones"
- `or/multnomah/wood-village/230.310.txt#L64-L65,L78,L88` (or/multnomah/wood-village NC.min_landscaped_pct) cites 230.200 710.100, text read as 230.310; first cited line: "Table 230-2. Development Standards in Commercial Zones"
- `or/multnomah/wood-village/230.310.txt#L60,L64-L65,L69,L84` (or/multnomah/wood-village NC.min_lot_depth_ft) cites 230.200 710.100, text read as 230.310; first cited line: "A. Minimum Lot Size and Dimension. There is no minimum lot size or dimension for development of land or creati"
### (d)
### (e)


## Is 409 a known baseline?

No. `docs/` has no "409" about this and no note accepting the corpus total. `docs/flats/handoff/washington.md` records per-jurisdiction hand checks (Sherwood 44 of 109, all hand-checked, none a wrong cite, L2877; Beaverton 80 of 341, L4323; Tigard 107, L4503) and a running `gaps.json` "corpus total" (290 to 291 at the King City commit, L4150). Current per-layer counts are Sherwood 44, Beaverton 83 (was 80), Tigard 107, so the total has grown since. The Estacada, Gladstone, Oregon City, West Linn, Fairview, Troutdale and Wood Village rows have no recorded review.

## Mechanical fix with flats/provenance/repoint.py?

No, for (a) and (b), and I did not run it. Its docstring: it follows a citation when the document underneath shifts, re-pointing line numbers by matching surviving line text between an old and a new version of the same document. These rows have no document change, and the quote's lines still resolve. The disagreement is between the cite string and the lines, which the tool has no input for. Fixing means a human choosing whether to edit the cite text or the lines, and a line edit would be a quote change that needs review.
