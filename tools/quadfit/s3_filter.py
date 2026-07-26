"""s3 — STRUCTURAL eligibility filter: reduce all Multnomah lots to the set
worth running geometry on. Only exclusions that no plausible config change can
reverse are applied here; POLICY exclusions (jurisdiction on/off, z overlay,
minimum lot area, minimum frontage) are annotated as columns and applied at
report time in s7 — so toggling a jurisdiction or adjusting a threshold needs
only an s7 re-run (seconds), not a pipeline re-run.

Structural drops (first-hit counted, written to funnel.json):
  1. condo-stack representative (stacked platting is not a redevelopable lot)
  2. jurisdiction unmapped (JURIS_CITY not in rules)
  3. jurisdiction ineligible AND no zone rules compiled (e.g. Maywood Park —
     can't come back without new research; ineligible jurisdictions WITH
     compiled zone rules, e.g. Lake Oswego, are kept and gated in s7)
  4. outside UGB where the jurisdiction requires it (statutory, stable)
  5. no zone assigned (zoning layer gap)
  6. zone not present in rules table
  7. zone present but quadplex not allowed (no setbacks to build an envelope)
  8. sliver / degenerate: lot smaller than sliver_min_lot_sqft, or nowhere
     20 ft wide (negative 10 ft buffer collapses to empty)

Lots surviving here may still be policy-excluded in s7 (z overlay, min lot
area, min frontage, ineligible-but-compiled jurisdiction).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import DATA_DIR, load_rules, read_stage, write_stage

NARROW_TEST_BUFFER_FT = -10.0  # lot must survive a 10 ft inward buffer somewhere


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    import numpy as np
    import pandas as pd
    import shapely

    rules = load_rules()
    lots = read_stage("s2_lots")
    funnel: list[dict] = [{"step": "all_multnomah_lots", "count": int(len(lots))}]

    def drop(mask, reason: str):
        nonlocal lots
        n = int(mask.sum())
        if n:
            lots = lots[~mask]
        funnel.append({"step": reason, "dropped": n, "remaining": int(len(lots))})
        print(f"  -{n:>8,}  {reason:<28} remaining {len(lots):,}")

    print(f"s3: starting from {len(lots):,} lots (structural filter only)")

    drop(lots["stacked"], "condo_stack")
    drop(lots["jurisdiction"].isna(), "jurisdiction_unmapped")

    # Ineligible jurisdictions with NO compiled zone rules can never be
    # re-enabled by a config toggle — drop. Ineligible ones WITH rules
    # (Lake Oswego) keep their geometry and are gated in s7.
    dead_juris = {
        k for k, j in rules.jurisdictions.items() if not j.eligible and not j.zones
    }
    drop(lots["jurisdiction"].isin(dead_juris), "jurisdiction_ineligible_no_rules")

    needs_ugb = {
        k for k, j in rules.jurisdictions.items() if j.require_inside_ugb
    }
    drop(lots["jurisdiction"].isin(needs_ugb) & ~lots["inside_ugb"], "outside_ugb")

    drop(lots["zone_raw"].isna(), "no_zone_assigned")

    # Rules lookup: zone in table? quadplex allowed (i.e. setbacks exist)?
    def _lookup(row):
        j = rules.jurisdictions[row["jurisdiction"]]
        rule = j.rule_for(row["zone_raw"])
        if rule is None:
            return "absent"
        return "allowed" if rule.quadplex_allowed else "not_allowed"

    verdict = lots.apply(_lookup, axis=1)
    drop(verdict == "absent", "zone_not_in_rules")
    verdict = verdict[verdict != "absent"]
    drop(verdict == "not_allowed", "zone_quadplex_not_allowed")

    drop(lots["area_sqft"] < rules.defaults.sliver_min_lot_sqft, "sliver_area")

    shrunk = shapely.buffer(
        np.array(list(lots["geom"]), dtype=object), NARROW_TEST_BUFFER_FT
    )
    too_narrow = np.array([g.is_empty for g in shrunk])
    drop(pd.Series(too_narrow, index=lots.index), "too_narrow_20ft")

    # Normalized zone code for grouping in reports.
    lots["zone"] = [
        rules.jurisdictions[j].normalize_zone(z)
        for j, z in zip(lots["jurisdiction"], lots["zone_raw"])
    ]

    print(f"s3: geometry universe {len(lots):,} lots "
          "(policy gates applied later in s7)")
    write_stage(lots, "s3_lots")
    (DATA_DIR / "funnel.json").write_text(json.dumps(funnel, indent=2), encoding="utf-8")
    print("s3 done.")


if __name__ == "__main__":
    main()
