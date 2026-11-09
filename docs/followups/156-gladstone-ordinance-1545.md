# 156. Gladstone quadfit rules follow the old printed code, not Ordinance 1545

**Status:** open (2026-11-09). Found by the CI1 lane (155).

quadfit's `Lot Analysis/quadfit/config/rules.yaml` still carries Gladstone R10
and C1 as the old printed code, not as amended by Ordinance 1545. quadfit can
measure lots the new law would reject; FLATS still refuses them, so no false
GREEN, but the envelope figures are wrong. Bring R10/C1 to the amended text
(the CI1 lane added `corpus_amendment:` on rules rows for this; reuse it),
mirror test, rides the next package.
