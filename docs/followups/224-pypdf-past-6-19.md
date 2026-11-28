# 224. pypdf held at 6.19 by the extraction hold -- 18 Dependabot alerts stay open until the corpus is re-extracted

224. [Claude] [scan: maybe -- only if re-extracted text differs]
   The 2026-11-28 security pass (item 217 tier 1) cleared every open alert it could. pypdf
   stopped at 6.19.0, and pyproject now caps it at `pypdf>=6.16.1,<6.20`.
   - **Why:** flats/provenance/pdf_hold.py#L44-L66 pins extraction to the rules the stored
     corpus was read under by rewriting three exact pypdf source lines. 6.20.1 removed the
     line in `recurse_to_target_op`, so the hold raises (#L84) and every PDF extraction fails.
     test_fetch and test_provenance_mend failed under 6.21.4.
   - **What stays open:** 18 pypdf alerts (GitHub count after the 11-28 push) (high/medium/low) with first fixes from 6.20.0 to
     6.21.4. Real exposure is small: pypdf reads only city/county code PDFs we fetch
     ourselves, and it runs in the FLATS provenance tools, not on user uploads.
   - **To lift the cap** (pdf_hold.py#L26-L29 says so):
     1. Re-extract the whole stored corpus under the newest pypdf, with the hold rewritten
        for its source.
     2. Diff the result against the stored text.
     3. If the text is unchanged, bump the lock. If it changed, the drift tools (`--repoint`)
        re-point citations before the bump.
   - **Also still open after the pass:** one PyJWT alert with no fixed version yet (watch
     for it). soupsieve went to 4.1.3, so its alerts should close; confirm on GitHub after
     the push.
