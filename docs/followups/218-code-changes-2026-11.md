# 218. Code changes found by the 2026-11-27 sweep (item 217 tier 1b): Wilsonville amended, Gladstone moved to eCode360

218. [Claude] [scan: maybe -- Wilsonville Village path looser (toward green); Gladstone unknown]
   Free sweep `fetch --all --check` 11-27: 657/770 current, 9 changed, ~90 refused (429s,
   mostly ecode360/Milwaukie -- re-run those later; free). Credit worker read the 9 ($2.77;
   full report data/flats/credit/out/t1b-code-changes.md, fresh copies in
   data/flats/credit/tmp/t1b/docs/ -- both gitignored, this PC only):
   (a) OAR 660-046-0010/-0020/-0220, OAR 340-071-0160, ORS 197A.420: em dash -> en dash in
       the public.law footer only. Accept with `--refresh --repoint`. Caution stands:
       public.law still serves the May 2025 Division 46, not LCDD 11-2026 (operative
       2027-01-01, _state.yaml#L150-154).
   (b) Wilsonville 4.planning.txt: new supplement (Supp. No. 7, Ord. 903 of 2026-06-15,
       dlcd_read.yaml#L856 read it as no_effect). No cited number changed; every citation
       only shifts lines (table in the report). To do: `--refresh --repoint`, re-cut the
       section files, fix the definition numbers quoted at wilsonville.yaml#L3337/#L3366
       (4.001(96)->(97), (181)->(182), (266)->(269)), re-read the 4.118 routing entry
       (#L633; waivers moved to new 4.119). JUDGEMENT: the Village vacant-lot reasoning
       (#L3080-3096, #L3328-3345) cites a DRB review and a deleted "not inflexible
       requirements" sentence in 4.421; residential SAP/PDP is now a Class II staff review
       against set standards -- looser for the building; value stays held on
       no_existing_dwelling; decide whether the note/route changes.
   (c) Gladstone: codepublishing now serves only a "moved to eCode360
       (https://ecode360.com/GL4459)" stub for all 17 chapters. Re-point the `code:` URLs
       (gladstone.yaml#L584-L699) to ecode360 print/guid URLs like Milwaukie's, re-fetch,
       compare the ten cited passages (17.06 x7, 17.26 x3). Steph's local export through
       Ord. 1544 is at data/flats/books/steph-drop-2026-11-18/gladstone/.
