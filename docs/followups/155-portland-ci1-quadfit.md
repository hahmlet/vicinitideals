# 155. Portland CI1 lots unmeasured in quadfit

**Status:** open (2026-11-08).

Since RICAP 11 (2026-11-01) CI1 allows homes built to RM1 standards. FLATS
knows that, but quadfit has no CI1 rules, so 36 Portland CI1 lots went
red -> yellow in re-screen 1110 and stay unmeasured. Add CI1 (RM1
standards) to quadfit's rules.yaml via the port, mirror test, then bound the
CI1 lots. Never a false GREEN: unmeasured stays yellow.
