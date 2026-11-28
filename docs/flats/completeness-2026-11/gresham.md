# Completeness check, gresham (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I answered all three questions for Gresham, though not exhaustively: the full ±12-line scan in B was blocked, so B rests on targeted greps (see "Not done"). Two findings could make GREENs wrong now; most of the rest can't be judged because the code text isn't held. I edited nothing and made no rulings. One side effect: running the two ledgers rewrote `data/flats/crossrefs.csv` and `data/flats/uncited.csv`. Both files were already modified before I started, so check the diff before committing anything.

## Could make a GREEN wrong: likely

**1. Section 9.0100 is the city's Buffering and Screening section, it isn't held, and the config files it as fences.**
- `gresham.yaml#L1690-1694` rules 9.0100 `other_building` as "Fences", based only on the definition sentence in 3.0103 ("For purposes of Section 9.0100, walls are a type of fence").
- The code itself calls it buffering, and applies it to the quadplex:
  - Table 4.0130 row M, "Buffers / All other uses: See Section 9.0100", in all seven residential districts (`4/4.0130.txt#L122-L126`).
  - Table 4.0430 row M, "Screening and Buffering Required (Section 9.0100)" (`4/4.0430.txt#L100-L104`). It reads Yes in CMF and CMU, and in RTC/SC/SC-RJ "except where abutting LDR-5, LDR-7, TR, TLDR, CMF or CMU", with a buffer per Table 9.0111(A). Note 9 lifts it only for townhouses (`#L141`).
  - Pleasant Valley: "All Uses See Buffer Matrix, Section 9.0100" (`4/4.1415.txt#L78-L79`).
  - Springwater: "The standards of Section 9.0100 … apply" (`4/4.1535.txt#L2`).
- The crossrefs ledger missed the 4.0130 row because the section number sits on the line below "See Section". Its sources list for 9.0100 doesn't include 4.0130.
- Question: how wide is the Table 9.0111(A) buffer for a quadplex next to LDR or commercial land, and is it wider than the encoded setbacks? 9.0100 needs fetching.

**2. Floor area ratio isn't encoded in LDR-5, LDR-7 or TR, and the lot-of-record relief removes the reason given for leaving it out.**
- Row J sets "1.0 / 0.7 / 1.0" for a quadplex (`4/4.0130.txt#L106-L107`). The LDR-5 (L2452–2717), LDR-7 (L2718–2965) and TR (L3202–3458) blocks have no `max_far`. Only OFR cites row J (`#L5155-5158`).
- The LDR-7 note (`#L2871`) says FAR "does not bind this pod" because of the minimum lot size. But `lot_of_record_relief` (`#L2791-2800`) waives minimum lot size for every existing taxlot "when in compliance with the other requirements of the district", and FAR is one of those requirements.
- The screen takes floor area as ground area × stories (`flats/score/screen.py#L2331-2337`). Assuming pod80x25 has an 80 × 25 ft ground floor (I took that from the file name; the file shows only 2 stories, `pods/pod80x25.yaml#L21`), that is about 4,000 sq ft. FAR then fails on LDR-7 lots under about 5,714 sq ft and on LDR-5 or TR lots under 4,000 sq ft.

## Could make a GREEN wrong: can't tell (the text isn't held)

**A1. Article 5 is missing apart from 5.0300.** The whole-document grep finds Section 5.0100 Floodplain, 5.0214 (hillside mapping), 5.0700 Natural Resource Overlay and "Highly Sloped Subareas" (`10.1700.affordable.txt#L54-55`). The config handles these only through quadfit `overlays.yaml` carves, whose citations point at text we don't hold:
- **Flood:** Gresham's "Flood Areas" includes "all lands that were inundated in the February 1996 flood" (`3/3.0120.txt#L37-L40`). Gresham is screened on FEMA only (`overlays.yaml#L1419-1452`), and `metro_title3` excludes Gresham (`#L338`). Question: does the 5.0100 overlay map reach 1996-only land? If so, those lots would get the same flag as the FEMA flood fringe.
- **Natural Resource Overlay:** "Potential Resource Area … subject to the development standards of the NRO district for Potential Resource Areas" (`3/3.0120.txt#L61`). There is no carve or flag for these areas; only Resource Areas and wetlands are covered (`overlays.yaml#L222-258`).
- **Hillside overlay:** the whole overlay is carved, at `needs_verification` (`#L259-267`). Any 5.0200 standards that reach the rest of the lot are unread.

**A2. Gresham Butte boundary.** "The boundaries … are shown on the Gresham Butte Overlay Map in Appendix 41" (`4.1300.gresham-butte.txt#L17-19`), and quadplexes and townhouses are prohibited there (`4/4.1310.txt`). The config keys this on the zoning label `LDR/GB` (`gresham.yaml#L9718ff`). Question: does that label match the Appendix 41 map? If not, LDR-5 lots inside the overlay would show GREEN.

**A3. Springwater park overlays are unread.** The Neighborhood and Community Park overlays (`4.1500.springwater.txt#L843-885`) put the community park on VLDR-SW, an encoded quadplex zone. Land-use reviews must determine "potential acquisition or dedication of the park site". The only config reading near them is the tree note at `#L1451`, and the Plan Map isn't held.

**C1. Setbacks are measured after dedication.** "The point or line of reference will be the lot line following any required dedication, future street widening or a special or reservation line" (`3/3.0103.txt#L893-894`). This line isn't cited, Gresham isn't among the seven codes `flats/geom/dedication.py` handles, and Appendix 5 (A5.408, `4/4.0136.txt#L47`) isn't held.

**C2. Sidewalk easements move the setback line.** "Where sidewalk access is provided by easement, the setback shall be measured from the easement line" (`4/4.0130.txt#L173`). Not cited.

**C3. The rear roof height plane may use a different ground level.** The plane is encoded from `7/7.0420.txt#L132-134`. The next line, "measured from the final finished grade to the top of the roof" (`#L135`), isn't cited. It differs from Building Height, "average elevation of the finished grade to the highest point" (`3.0103#L100`), and from Grade, "the lowest point of elevation" (`#L455`). This only matters on sloped lots.

**C4. A basement can count as a story** when it is more than 6 ft above grade for half the perimeter, or more than 12 ft at any point (`3.0103#L1087-1089`). This only matters where the cap is in stories rather than feet.

## Not a GREEN risk (these only loosen, or are inert)

- **Double frontage lots** have a third statement: Table 4.0131 note 2 makes a frontage on "an alley or private accessway" the rear (`4/4.0130.txt#L174`). That loosens.
- **"Alley" is never defined** in the stored code; a whole-corpus grep found only table labels. Question: which meaning do the alley variants use?
- **"Frontage"** means abutting a "transportation facility" (`3.0103#L443, L1152`), which is broader than a street. That loosens.
- **Building Footprint** has a second definition that applies only inside overlays (`3/3.0120.txt#L8`).
- **A stale config note:** `gresham.yaml#L157` says "There is no clear-vision field". `flags.yaml#L382-390` shows one now exists, and Gresham, having no value in it, is screened at the largest plausible size.
- **Well Field Protection** applies to industrial and commercial development only (`4.0300.industrial.txt#L299-300`).
- **Handled already:** Historic landmarks (`historic/protection.yaml#L28`) and corner lots (the definitions ledger reports `own`).
- **Crossrefs ledger:** every Gresham row it marks binding already has an outcome. Its unheld state-law references (ORS 197, 456.270, 458.610, 174.109) aren't geometric.

## Not done
- **B is not exhaustive.** Inline Python was blocked, so I couldn't scan every cited line ±12. Instead I grepped the 15 most-cited files by hand.
- **The past overlay findings weren't read.** `../vicinitideals-worktrees/overlay-inventory*` is outside the sandbox, so I couldn't remove items they already cover. Some of A1–A3 may already be there.
- **`words.py --audit` timed out** at 240 s.
- **The uncited ledger may still be running** in the background; I relied on the CSV already on disk.

