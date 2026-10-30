# 23. Page check -- SHIPPED 2026-09-30 (a203e9f1).

23. [Copilot] [scan: NO] **Page check -- SHIPPED 2026-09-30 (a203e9f1).** `/flats/check`: the
   printed page with a box on the number, signed numbers first, then one card
   per footnote on it; "no" answers form the problems list
   (`/flats/check/problems.txt`, stamps `bundled_at`). (a) DONE -- web
   codes show the stored text with the number tinted (3267d23a on main;
   answers go to the same table with page NULL and placed = "web").
   Still open: (b) nothing reads the problems list yet -- wire a "differs"
   into the signing disputes so the number reopens there.
   [Copilot brief for (b)] Files: app/api/routers/ui_flats_check.py (the page-check answers;
   `flats_check_problems` serves /flats/check/problems.txt), flats/encode/dispute.py (the
   dispute log the signing pages read; read it first). Do: a page-check answer of "differs"
   on a number also lands as a dispute on that number, so the signing pages show it reopened.
   Must not change: any answer, colour or rule value; the problems.txt output; existing
   disputes. Test: in tests/api/test_ui_flats_check.py, answer "differs" on a number and
   assert the number shows as disputed; answer "yes" and assert it does not. If the dispute
   log has no place for a page-check answer, stop and report rather than invent one.
