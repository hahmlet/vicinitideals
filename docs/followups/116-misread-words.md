# 116. Mend the misread words the squiggles show, worst city first.

**Status (2026-11-08): DONE on branch `flats/misread-words`; remove the file and index line on merge.**

History: Gresham f048be68 (1,112 ligatures, underlines 723 -> 172); Canby + King City 3046b980, e89f914c (King City 89 -> 12).

Final batch (flats/misread-words): Tualatin's capitals kerned off their words, which the readable cut leaves because the city prints the whole word fewer than three times ("T avern", "T onquin" x3, "T ownship" x5, "T onka" x2, and the unflagged "T ax" x4, "T own" x2), plus "dup lexes"; King City's "decision-mak-ing" (a margin hyphen the cut kept). Each is a `JOIN_MENDS` entry on its proof copy, so a re-fetch and the page map make the same mend; proved by `mend.check_document` (fresh extraction equal, pdfplumber letters equal; 71.wetlands-protection differs only by its undecoded "½" glyph, as before), then re-cut with `flats.encode.recut --write`: 0 citations moved, 0 refused, 0 readings, 0 signatures, no carry file. Every encoded value identical before and after. Underlines: King City 12 -> 11, Tualatin 36 -> 24.

**Left, on purpose (store as printed):** the PDF itself prints `feetto` (Tualatin 71.900, no gap between the glyphs), `orvanpool`, `fity`, `eigths` (King City). `Dia-` and `pav-` break across a page, which the readable cut never joins. `Ficher` is a name as printed; `degbrees`, `ofeas`, `llis`, `fhc` are figure-label fragments in the 16.24 solar diagram; `supp.` is an abbreviation. Tualatin's rest are real words or names no list holds (minimart, fenestrations, Atfalati, Quatoma).
