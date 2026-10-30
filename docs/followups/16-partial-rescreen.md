# 16. Partial re-screen -- SHIPPED 50a0ecc2 2026-09-25 (runbook §4c).

16. [Copilot] [PARKED: Steph called it "for later" -- ask before firing] [scan: NO] **Partial re-screen -- SHIPPED 50a0ecc2 2026-09-25 (runbook §4c).**
   Nothing left to build. Kept for one remark: showing the `splice audit`
   on /flats/refresh -- Steph 2026-09-25 "an enhancement for later" -- not
   queued.
   [Copilot brief] Files: app/api/routers/ui_flats.py (`/flats/refresh` handler),
   app/templates/flats_refresh.html, flats/ingest/splice.py (`audit()` and `report()`). Do:
   show the latest splice audit's result read-only on /flats/refresh. First find where an
   audit's result is kept on VM 114; if it is not kept anywhere the app can read, stop and
   report. Must not change: splice or audit behaviour, the page's refresh actions, any
   answer. Test: tests/api/test_ui_flats_refresh.py -- the page renders with and without an
   audit result present.
