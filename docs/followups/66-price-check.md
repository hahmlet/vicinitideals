# 66. A price check beside the fit (Steph 2026-10-10: "Do we not have a financial screen? If there's a large commercial use ... redevelopment wouldn't support") -- (A) LIVE 2026-10-10 (merge d1d8c03f).

66. [Claude] [Steph: (a), (d)] [scan: NO for (A); YES for (B)] **A price check beside the fit (Steph 2026-10-10: "Do we
   not have a financial screen? If there's a large commercial use ... redevelopment wouldn't
   support") -- (A) LIVE 2026-10-10 (merge d1d8c03f).** STEPH RULED 2026-10-10 (register
   `2026-10-10-price-per-home-label`): (A) -- colour unchanged, a PRICE PER UNIT label + a
   filter set at $30k/unit ($120k a pod), adjustable ("land price is passed to the buyer, so
   it flexes with the market"; look at everything). Units = pods the lot could hold x 4, NOT
   one pod: a big lot pays for (lot area - roads to serve the pods) / (pod + its parking),
   with parking possibly pooled to save buffers and planters (pods stay independent). STEPH
   CONFIRMED 2026-10-10 the defaults (4,500 sq ft a pod incl. parking + yard share; 25% to
   roads on lots of 3+ pods) and the guards: pods capped by the zone's density limit;
   multi-pod counts labelled ESTIMATE (new roads / a land division may need a review);
   county market value by default, last sale shown beside it; the two defaults adjustable.
   Price is rough until a PAID price feed arrives (vendor TBD, ~2 months): a paid feed goes IN
   FRONT in flats/score/price.py PRICE_SOURCES with one entry (each price carries its source +
   date). True layouts stay item 31 / parked 92.
   Built: table flats.lot_prices (migration 0143), app/services/flats_price.py, settings
   flats/config/price.yaml, filled by scripts/flats_load_bridge.py and
   scripts/flats_backfill_lot_prices.py (run it for the live copy, and again after a rule
   change moves a zone's density limit). TRAP: the first deploy (34e1a771) HUNG PRODUCTION
   and was reverted (4670491e) -- it worked the price out of each lot's JSON per row against
   the wide lot table; keep the page on the stored narrow columns (work_mem 128MB, 25 s
   statement_timeout inside a savepoint).
   (b) BUILT 2026-10-16 (77d466a0 on main): stored cap inputs now include max_units and
   whether density is measured on net area; the columns come from migration 0145 (renumbered
   from 0144 by 4e668a34) and a repeat run of scripts/flats_backfill_lot_prices.py -- that
   backfill re-run on production is not recorded as done; colours are unchanged.
   Open: (a) filter is opt-in, not on by default -- Steph to say if it should start ON;
   (c) ~10 greens carry county values under $1 a sq ft (price per home of $17-$950) -- shown
   as-is; (d) a "value looks too low" mark -- Steph to decide. Only (a) and (d) wait on Steph.
