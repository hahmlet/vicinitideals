# 13. Tax code area in the RLIS ingest.

13. [Claude] [scan: NO -- lands with the November county data refresh] **Tax code area in the RLIS ingest.** The Gresham tax-impact snapshot
   (`scripts/flats_tax_snapshot.py`, migration 0136) needs each lot's tax
   code area (RLIS `TAXCODE`), which acquire drops because it is not a
   declared field; the script's `taxcodes` step pulls it separately out of
   the quarterly ZIP. Declare `TAXCODE` in the RLIS fields and carry it into
   `facts["assessor"]` so the next snapshot joins on the lot row and the
   county copy and the code areas are guaranteed the same release.
   TIMING TRAP: editing the `rlis_taxlots` registry entry makes the monthly
   probe report `registry_changed` and turns the Lots banner red until a
   new copy is taken -- make the edit as the first step of the November
   RLIS refresh, not before.
