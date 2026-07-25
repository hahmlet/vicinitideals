"""s3 — eligibility funnel: reduce all Multnomah lots to the quadplex-by-right
universe. Every exclusion is counted and written to data/quadfit/funnel.json so
the summary can show exactly what was dropped and why.

Order matters — a lot is counted against the FIRST reason that removes it:
  1. condo-stack representative (stacked platting is not a redevelopable lot)
  2. jurisdiction unmapped (JURIS_CITY not in rules) / ineligible (Maywood Park)
  3. outside UGB where the jurisdiction requires it (unincorporated county)
  4. no zone assigned (zoning layer gap)
  5. zone not present in rules table
  6. zone present but quadplex not allowed
  7. Portland Constrained Sites overlay (PCC 33.418) voids the fourplex
     allowance (any portion of lot in "z")
  8. lot below the zone's quadplex minimum lot area (e.g. Portland Table 110-7)
  9. sliver / degenerate: lot smaller than sliver_min_lot_sqft, or nowhere
     20 ft wide (negative 10 ft buffer collapses to empty)
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
    reasons = []

    def drop(mask, reason: str):
        nonlocal lots
        n = int(mask.sum())
        if n:
            lots = lots[~mask]
        funnel.append({"step": reason, "dropped": n, "remaining": int(len(lots))})
        reasons.append((reason, n))
        print(f"  -{n:>8,}  {reason:<28} remaining {len(lots):,}")

    print(f"s3: starting from {len(lots):,} lots")

    drop(lots["stacked"], "condo_stack")
    drop(lots["jurisdiction"].isna(), "jurisdiction_unmapped")

    ineligible = {
        k for k, j in rules.jurisdictions.items() if not j.eligible
    }
    drop(lots["jurisdiction"].isin(ineligible), "jurisdiction_ineligible")

    needs_ugb = {
        k for k, j in rules.jurisdictions.items() if j.eligible and j.require_inside_ugb
    }
    drop(lots["jurisdiction"].isin(needs_ugb) & ~lots["inside_ugb"], "outside_ugb")

    drop(lots["zone_raw"].isna(), "no_zone_assigned")

    # Rules lookup: zone in table? quadplex allowed?
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

    # Portland Constrained Sites overlay (PCC 33.418.040.B): fourplex allowance
    # void where any portion of the lot is in the z overlay — applies to city
    # lots and the Portland-administered unincorporated pockets.
    if "has_z_overlay" in lots.columns:
        drop(
            lots["jurisdiction"].isin(["portland", "multnomah_unincorporated"])
            & lots["has_z_overlay"],
            "z_overlay_constrained_site",
        )

    # Per-zone minimum lot area for a quadplex (e.g. Portland Table 110-7).
    def _min_lot(row):
        rule = rules.jurisdictions[row["jurisdiction"]].rule_for(row["zone_raw"])
        return rule.min_lot_sqft if rule and rule.min_lot_sqft else 0.0

    min_lot = lots.apply(_min_lot, axis=1)
    drop(lots["area_sqft"] < min_lot, "lot_below_zone_min_area")

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

    print(f"s3: eligible universe {len(lots):,} lots")
    write_stage(lots, "s3_lots")
    (DATA_DIR / "funnel.json").write_text(json.dumps(funnel, indent=2), encoding="utf-8")
    print("s3 done.")


if __name__ == "__main__":
    main()
