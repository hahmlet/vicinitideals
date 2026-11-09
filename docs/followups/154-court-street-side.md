# 154. Court between the building and a street -- false greens (re-screen 1110)

**Status:** building (2026-11-08).

The re-screen 1110 move-reader found 36 lots wrongly GREEN: the pod's parking
court sits between the building and a street (ruling 2026-11-08 front-yard
parking; Portland 33.266.120.C.1.a, through lots have two fronts). The
`_court_street_side` check in `flats/ingest/quadfit.py` ran only in the
fire-reach retry. Lot list and evidence: `/root/rd1110/gains_ss.parquet` on 137.

First question: does rel4 (ed1d094d, which merged court-front-yard) already
cover every placement path? If yes, rel4 closes it. If not, branch
`flats/court-street-side` off rel4 and re-bound the affected lots on top of
`/root/bound_rel4`.

The re-screen 1110 output is NOT released by itself because of these 36: it
ships inside rel4.
