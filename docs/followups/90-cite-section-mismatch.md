# 90. Cites that name a section the cited lines do not sit in (found 2026-10-16, docs/ops/quote-mismatch-2026-10-16.md).

90. [Claude] [CHECKER FIXED 726bb7e1 2026-10-22, LIVE: 367 -> 84 disagreements, 0 agreements lost; 68 to review = Sherwood 43 (16.12.030 heading missing from stored text, hand-checked), Gresham 24 (cite 7.0420 but lines in 7.0431 / Rockwood 7.0512 -- likely real, add the section to the cite), Beaverton 8 (cite names 20.x.16 only, quote also uses Table 20.x.15), Hillsboro 5 + King City 1 (lagging page header); NOT TO BUILD (2026-10-23: item 73 rebuilds the text as a tree of sections, so section membership becomes structural and this heading-reader is retired; use the list as 73's conversion checklist instead -- every one of these must land in the section its cite names, or be flagged): 1,533 values cite a section but the reader finds NO heading above the lines, so they agree unchecked -- Gresham 309, Beaverton 299, Happy Valley 219, Tualatin 122, Lake Oswego 120, Portland 104; teach the reader each city's heading shape, measured corpus-wide as above] [scan: NO (citations move, answers must not)] **Cites that name a section
   the cited lines do not sit in (found 2026-10-16, docs/ops/quote-mismatch-2026-10-16.md).** (b)+(c) DONE
   8775562a 2026-10-21: 63 cites fixed in Estacada, Gladstone, Oregon City, Fairview, Troutdale, Wood
   Village, Tigard -- the quoted lines were right, the cite named a neighbouring section; no value,
   condition or quote moved. Counts now (a) header_or_xref 283, (b) 48, (c) 0, (d) unlocated 9. The 57
   left are the CHECK's errors, not cites: lagging page headers beat a real heading (Sherwood 16.94, King
   City 16.114.130 -- a fix added 89 false cases, reverted); Sherwood's 16.12.030 heading missing from
   the stored text (43, hand-checked correct); Beaverton cells "18.511" / "see 20.25.15" read as
   headings; the cite reader takes "Table 18.805.1" as a section and cannot read "19.65.030 through
   19.65.060". Next: teach the check to ignore (a). Also: Gresham NC-PV quadplex_allowed cites Tables
   4.1413/4.1415A/B but its quote is Table 4.1423 ("Quadplex NP") -- DONE 751bc5d5.
