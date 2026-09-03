"""s7 — POLICY gates + aggregation: per-lot table, summary.md, spot-check.

s6 output is a pure-geometry superset (every lot with a computable envelope,
both orientations tested). This stage applies everything configurable:

- jurisdiction eligibility (rules.yaml `eligible` toggles)
- Portland Constrained Sites z overlay (PCC 33.418)
- per-zone quadplex minimum lot area / minimum frontage
- orientation constraints (axis_required disables the 90° flip)
- coverage caps (percent or curve)
- large-lot subdivision screen (footprints.yaml `split` block)

So toggling a jurisdiction, adjusting a threshold, or changing the parking
buffer needs ONLY this stage re-run:  uv run --extra gis python tools/quadfit/s7_report.py

Headline statistics use tiers A+B only (clean geometry); tier C (irregular,
conservative envelope) is reported separately; tier D is excluded. frontier_json
holds max-depth-per-width in CELLS at s6_meta grid resolution.

Outputs: summary.md · lots_results.csv (all geometry-universe lots, with
policy_exclusion column) · conversion_candidates.csv (eligible, fits, NOT a
split candidate) · split_candidates.csv (eligible, >= min_quads if split) ·
viable_candidates.csv (fitting lots clearing the per-door land-cost ceiling,
cheapest first) · spot_check.geojson.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import (
    DATA_DIR, load_footprints, load_overlays, load_rules, read_stage, stage_path,
)

HEADLINE_TIERS = ("A", "B")
Z_OVERLAY_JURISDICTIONS = ("portland", "multnomah_unincorporated")


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def open_space_label(dw) -> str:
    """How one city's open-space reserve reads in the per-city table.

    This was a literal string, "by zone (250 / 200 sq ft)", for as long as
    Portland held the only per-zone reserve in the file. The second one to
    arrive -- unincorporated Multnomah's single 1,200 sq ft on LR-7, which the
    county reaches only through design review of a conditional use -- printed
    Portland's two numbers under the county's name, which is a report stating
    a false fact about a jurisdiction. The figures now come out of the map.

    A map whose values are every one of them null is a city that was read and
    reserves nothing, and it says so in the same words as a city with no map.
    """
    if dw is None:
        return "*not read*"
    if dw.open_space_sqft_by_zone:
        figs = sorted({v for v in dw.open_space_sqft_by_zone.values() if v},
                      reverse=True)
        if figs:
            return "by zone (" + " / ".join(f"{v:g}" for v in figs) + " sq ft)"
        return "**none stated**"
    if dw.open_space_pct:
        return f"{dw.open_space_pct:g}% of lot"
    if dw.open_space_sqft:
        return f"{dw.open_space_sqft:g} sq ft"
    return "**none stated**"


# Oregon assessor property-class first digit -> broad current use. 4xx tract
# land is residential in practice; 3xx industrial folded into commercial
# (both are "valuable existing use we won't replace").
_USE_BY_CLASS_DIGIT = {
    "1": "single_family", "4": "single_family",
    "2": "commercial", "3": "commercial", "7": "multifamily",
}
_USE_BY_LANDUSE = {
    "SFR": "single_family", "MFR": "multifamily",
    "COM": "commercial", "IND": "commercial", "VAC": "vacant",
}


def current_use_column(lots, vacant_max: float = 0.0) -> list[str]:
    """Broad current-use tag per lot. STATECLASS is assessor-authoritative;
    RLIS LANDUSE fills its blanks. Improvement value at or under vacant_max =
    vacant regardless of class (nothing worth keeping to replace)."""
    import pandas as pd

    bldg = pd.to_numeric(lots["BLDGVAL"], errors="coerce").fillna(0.0)
    out = []
    for sc, lu, bv in zip(lots["STATECLASS"], lots["LANDUSE"], bldg):
        if bv <= vacant_max:
            out.append("vacant")
            continue
        sc = str(sc or "").strip()
        use = _USE_BY_CLASS_DIGIT.get(sc[:1]) if sc else None
        if use is None:
            use = _USE_BY_LANDUSE.get(str(lu or "").strip().upper(), "other")
        out.append(use)
    return out


def policy_gates(lots, rules, ocfg=None, screen=None):
    """Per-lot policy columns from the CURRENT rules.yaml + overlays.yaml.

    Returns (gates DataFrame aligned to lots, policy funnel rows). The funnel
    counts first-hit exclusions in a fixed order over the geometry universe.
    Overlay KILL layers (ovl_* columns written by s5o) append funnel steps,
    then the current-use screen (existing multifamily/commercial) — last, so
    legal exclusions win the first-hit label when both apply.
    """
    import numpy as np
    import pandas as pd

    n = len(lots)
    elig_j = np.zeros(n, dtype=bool)
    z_ok = np.ones(n, dtype=bool)
    min_lot_ok = np.ones(n, dtype=bool)
    frontage_ok = np.ones(n, dtype=bool)
    frontage_unmeasured = np.zeros(n, dtype=bool)
    # s4 takes the width where the city defines one and the shape allows it.
    # Absent on a pre-width parquet -> every lot falls back to the frontage
    # treatment, which is what this screen did before the measurement existed.
    lot_width = (
        pd.to_numeric(lots["lot_width_ft"], errors="coerce").to_numpy()
        if "lot_width_ft" in lots.columns
        else np.full(n, np.nan)
    )
    flip_allowed = np.ones(n, dtype=bool)
    cov_cap = np.full(n, np.nan)
    accessory = np.zeros(n)

    has_z = (
        lots["has_z_overlay"].to_numpy()
        if "has_z_overlay" in lots.columns
        else np.zeros(n, dtype=bool)
    )
    for i, (jkey, zraw, area, frontage, hz) in enumerate(zip(
        lots["jurisdiction"], lots["zone_raw"], lots["area_sqft"],
        lots["frontage_ft"], has_z,
    )):
        j = rules.jurisdictions[jkey]
        rule = j.rule_for(zraw)
        elig_j[i] = j.eligible
        if jkey in Z_OVERLAY_JURISDICTIONS and hz:
            z_ok[i] = False
        if rule is None:
            continue
        if rule.min_lot_sqft is not None and float(area) < rule.min_lot_sqft:
            min_lot_ok[i] = False
        if rule.min_frontage_ft is not None:
            width = lot_width[i]
            if j.lot_width_measure and np.isfinite(width):
                # The city's own measurement, taken. It rules both ways: a lot
                # too narrow at the street can be wide enough across the middle
                # and pass, and a lot with generous street frontage can be
                # pinched behind it and fail.
                if float(width) < rule.min_frontage_ft:
                    frontage_ok[i] = False
            elif float(frontage) < rule.min_frontage_ft:
                # Where the city's number is a mid-lot WIDTH rather than a
                # street frontage and no width could be measured, the screen is
                # not entitled to a verdict: it measured a different line. Hold
                # the lot for review instead of dropping it.
                if j.frontage_is_lot_width:
                    frontage_unmeasured[i] = True
                else:
                    frontage_ok[i] = False
        constraint = rule.orientation_constraint or j.orientation_constraint
        flip_allowed[i] = constraint != "axis_required"
        cap = rule.coverage_cap_sqft(float(area))
        if cap is not None:
            cov_cap[i] = cap
        accessory[i] = rule.accessory_allowance_sqft

    gates = pd.DataFrame({
        "elig_jurisdiction": elig_j, "z_ok": z_ok, "min_lot_ok": min_lot_ok,
        "frontage_ok": frontage_ok, "frontage_unmeasured": frontage_unmeasured,
        "flip_allowed": flip_allowed,
        "cov_cap": cov_cap, "accessory": accessory,
    }, index=lots.index)

    # First-hit policy funnel + per-lot exclusion label.
    steps = [
        ("jurisdiction_disabled", ~gates["elig_jurisdiction"]),
        ("z_overlay_constrained_site", ~gates["z_ok"]),
        ("lot_below_zone_min_area", ~gates["min_lot_ok"]),
        ("below_min_frontage", ~gates["frontage_ok"]),
    ]
    if ocfg is not None:
        for spec in ocfg.overlays:
            col = f"ovl_{spec.key}"
            if spec.action == "kill" and col in lots.columns:
                steps.append((f"overlay_{spec.key}", lots[col].astype(bool)))
    if screen is not None and "current_use" in lots.columns:
        for cat in screen.exclude_current_use:
            steps.append((f"existing_{cat}", lots["current_use"] == cat))
    exclusion = pd.Series("", index=lots.index)
    remaining = pd.Series(True, index=lots.index)
    funnel = []
    for name, bad in steps:
        hit = remaining & bad
        exclusion[hit] = name
        remaining &= ~bad
        funnel.append({"step": name, "dropped": int(hit.sum()),
                       "remaining": int(remaining.sum())})
    gates["policy_exclusion"] = exclusion
    gates["eligible"] = remaining
    return gates, funnel


# Triage tunables (narrow-neck flag-lot heuristic + utility-diligence cutline).
FLAG_MAX_FRONTAGE_FT = 30.0   # a narrow street neck on ...
FLAG_MIN_AREA_SQFT = 4000.0   # ... an otherwise large lot => likely flag-lot pole
SEWER_REVIEW_FT = 50.0        # a 4-plex ties into a main at the street; beyond
                              # ~50 ft the main no longer fronts the lot =>
                              # not "on sewer" (review, or red where no district)

# Clackamas County jurisdictions — the coverage of the sanitary Sewer_Districts
# polygon layer. Only here does "outside every district" mean "no public sewer"
# (a hard red); Multnomah has no district map so its no-main lots stay review.
CLACKAMAS_JURIS = (
    "oregon_city", "gladstone", "milwaukie", "west_linn", "wilsonville",
    "happy_valley", "tualatin", "clackamas_unincorporated",
)


def attribute_and_triage(lots, fp_names, rules, has_siteplan, flag_ovl_cols,
                         min_stalls, ocfg=None):
    """Add per-lot `flag_suspect`, `binding_constraint`, and `triage` columns.

    `binding_constraint` = the single first-hit reason a lot is NOT buildable
    (policy -> no-envelope -> no-fit -> over-coverage -> site-plan sub-reason),
    "" when the lot passes every test. This is the per-lot source for the
    "which constraint binds most often" histogram (combined with the structural
    funnel counts, which are aggregate-only because s3 deletes those rows).

    `triage` buckets every surviving lot into:
      - red    : a hard, trustworthy test fails (binding_constraint set)
      - review : passes the hard tests but the geometry can't be fully trusted
                 or a silent-killer layer is touched — a narrow flag-lot neck,
                 an irregular (tier C) shape, steep/unknown slope, far/unknown
                 sewer, an unverified zone rule, or a flag-action overlay
      - green  : passes and is trustworthy
    Review deliberately absorbs the wide-flag-pole false-green: a lot whose
    frontage is a narrow neck is never hard-greened, even though the raster
    fit (which can't see the access strip) said a pod fits.
    """
    import numpy as np
    import pandas as pd

    n = len(lots)
    frontage = pd.to_numeric(lots["frontage_ft"], errors="coerce").to_numpy()
    area = pd.to_numeric(lots["area_sqft"], errors="coerce").to_numpy()
    flag_suspect = (frontage <= FLAG_MAX_FRONTAGE_FT) & (area >= FLAG_MIN_AREA_SQFT)
    lots["flag_suspect"] = flag_suspect

    fits_any = np.zeros(n, dtype=bool)
    fits_cov_any = np.zeros(n, dtype=bool)
    for name in fp_names:
        fits_any |= lots[f"fits_{name}"].to_numpy()
        fits_cov_any |= lots[f"fits_cov_{name}"].to_numpy()

    eligible = lots["eligible"].to_numpy()
    pol = lots["policy_exclusion"].astype(str).to_numpy()
    tier = lots["tier"].astype(str).to_numpy()

    if has_siteplan and "parking_tier" in lots.columns:
        evaluated = lots["parking_tier"].to_numpy() != "not_evaluated"
        site_ok = lots["site_plan_ok"].to_numpy()
        stalls = pd.to_numeric(lots["stalls_provided"], errors="coerce").fillna(0).to_numpy()
        open_ok = lots["open_space_ok"].to_numpy()
        method = lots["layout_method"].astype(str).to_numpy()
    else:
        evaluated = np.zeros(n, dtype=bool)
        site_ok = np.ones(n, dtype=bool)
        stalls = np.zeros(n)
        open_ok = np.ones(n, dtype=bool)
        method = np.array([""] * n)

    binding = np.empty(n, dtype=object)
    binding[:] = ""
    for i in range(n):
        if not eligible[i]:
            binding[i] = pol[i] or "policy_excluded"
        elif tier[i] == "D":
            binding[i] = "no_buildable_envelope"
        elif not fits_any[i]:
            binding[i] = "pod_no_fit"
        elif not fits_cov_any[i]:
            binding[i] = "over_coverage"
        elif evaluated[i] and not site_ok[i]:
            if method[i] == "none":
                binding[i] = "siteplan_no_layout"
            elif not open_ok[i]:
                binding[i] = "siteplan_open_space_short"
            elif stalls[i] < min_stalls:
                binding[i] = "siteplan_too_few_stalls"
            else:
                binding[i] = "siteplan_fail"
    lots["binding_constraint"] = binding

    # Review triggers (only meaningful for lots that pass the hard tests).
    unver = {(jk, z.zone) for jk, j in rules.jurisdictions.items() if j.eligible
             for z in j.zones if z.confidence != "verified"}
    juris = lots["jurisdiction"].astype(str).to_numpy()
    zone = lots["zone"].astype(str).to_numpy()
    unverified_zone = np.array([(juris[i], zone[i]) in unver for i in range(n)])
    if "frontage_unmeasured" in lots.columns:
        frontage_unmeasured = lots["frontage_unmeasured"].fillna(False).to_numpy().astype(bool)
    else:
        frontage_unmeasured = np.zeros(n, dtype=bool)
    if "slope_tier" in lots.columns:
        slope_bad = np.isin(lots["slope_tier"].astype(str).to_numpy(),
                            ("cost_prohibitive", "unknown"))
    else:
        slope_bad = np.zeros(n, dtype=bool)
    # A slope read off the coarse (~10 m) DEM answers a question the 1 m lidar
    # could not answer at all, because 3DEP has no 1 m product east of about
    # longitude -122.48 -- Gresham, Troutdale, Fairview and Wood Village
    # entirely, and Portland's eastern third. Until 2026-09-01 those lots
    # carried no elevation at all and were held at review as "unknown", which
    # is why four whole cities had never produced a single green.
    #
    # A number from a coarser instrument is not the same claim as a number from
    # a finer one, and this one is measurably softer: calibrated against the
    # 1 m answer on the 184,101 lots where both DEMs exist, the rule used here
    # (max slope over a 50 m box <= 10%) wrongly clears 1.50% of genuinely
    # steep lots. So by default a coarse answer is REPORTED but may not GREEN
    # -- the lot keeps its place in the human queue with a number attached
    # instead of a blank. `slope.fallback_10m_may_green` flips that; it is a
    # business call about 7,231 lots and 1.5%, not a technical one, and it
    # lives in docs/HUMAN_TODO.md until somebody makes it.
    coarse_may_green = bool(ocfg and ocfg.slope.fallback_10m_may_green)
    if "slope_source" in lots.columns and not coarse_may_green:
        slope_bad = slope_bad | (
            lots["slope_source"].astype(str).to_numpy() == "dem_10m")
    if "sewer_main_dist_ft" in lots.columns:
        sew = pd.to_numeric(lots["sewer_main_dist_ft"], errors="coerce").to_numpy()
        near_main = np.isfinite(sew) & (sew <= SEWER_REVIEW_FT)
    else:
        near_main = np.zeros(n, dtype=bool)
    # No mapped main within reach => sewer not confirmed: review (yellow).
    sewer_review = ~near_main
    # Sanitary sewer DISTRICT gate. A real nearby main always wins (stays
    # green). Where no main is mapped, district membership decides, but ONLY in
    # Clackamas (the Sewer_Districts layer's coverage): inside a district =
    # keep as review (connectable but unconfirmed, yellow); OUTSIDE every
    # district = no public sewer path -> hard red (no_public_sewer). Multnomah
    # has no district map, so its no-main lots stay review, never forced red.
    # Computed in s5o; absent on pre-district parquet -> no district reds (a
    # no-main lot just stays review, the old behavior).
    if "in_sewer_district" in lots.columns:
        in_dist = lots["in_sewer_district"].fillna(False).to_numpy().astype(bool)
        clackamas = np.isin(juris, CLACKAMAS_JURIS)
        no_sewer_red = clackamas & ~near_main & ~in_dist
        newly_red = (binding == "") & no_sewer_red
        if newly_red.any():
            binding = binding.copy()
            binding[newly_red] = "no_public_sewer"
            lots["binding_constraint"] = binding
    overlay_flag = np.zeros(n, dtype=bool)
    for c in flag_ovl_cols:
        overlay_flag |= lots[c].to_numpy().astype(bool)

    # An assumed aisle is NOT a review trigger, decided 2026-08-31, and the
    # reason is the statute this whole screen already rests on. ORS 197A.400
    # (renumbered from ORS 197.307(4)) lets a local government apply only
    # CLEAR AND OBJECTIVE standards to housing, and a standard that does not
    # exist cannot be clear and objective. Milwaukie and Wilsonville publish no
    # drive-aisle width for this building anywhere -- verified to the end of
    # OAR 660-046-0220(2)(e)(E)'s single-family redirect, which lands back on
    # sections that state none either -- so neither city has a lawful basis to
    # impose one. A court drawn to the national engineering minimum cannot be
    # refused for a dimension nobody wrote down.
    #
    # Which makes silence a BETTER position than a published number, not a
    # worse one: Troutdale's 25 ft binds, and nothing binds here. So these lots
    # are graded like any other -- green where they pass. `geometry_assumed`
    # survives as a CSV column rather than a verdict, so a reviewer can still
    # filter for the rows whose aisle came from ULI/NPA instead of a code.
    #
    # What would overturn it: either city publishing an aisle (the mirror test
    # fails that day), or a discretionary hook surviving 197A.400 for middle
    # housing -- Wilsonville 4.155 sends "drive aisle design" to review
    # criteria, and Milwaukie 19.607.1.E.2 asks for a turnaround with no width.

    # A lot can be too BIG. Forty zones state a MINIMUM density -- units per
    # acre a residential site has to reach -- and four homes clear it on an
    # ordinary lot and stop clearing it on a large one. Not preempted: OAR
    # 660-046-0220(2)(b) strikes out density MAXIMUMS for a quadplex and says
    # nothing about a floor, and Oregon City states the point twice (Table
    # 17.08.050 note B.2 counts all four units toward it; 17.65.070.D.4 says the
    # minimum "may not be reduced").
    #
    # REVIEW rather than RED, and the asymmetry is the reason. Every city that
    # states a floor divides by NET developable area -- gross less rights-of-way,
    # floodplain, steep slopes and resource land -- and nothing here surveys
    # that. Net is smaller than gross, so the density computed on net is HIGHER:
    # a lot that clears the floor on its gross area clears it outright, and a
    # lot that fails on gross might still pass once the undevelopable ground
    # comes out. One direction is settled and the other is a question, which is
    # what the review queue is for.
    # The RATE is banded too. Gresham applies MDR-24's 12.1 du/acre only to a
    # site of 11,000 sq ft and up, so whether a lot has a floor at all is a
    # question about its own size and has to be asked per lot.
    def _floor(j: str, z: str, a: float):
        jr = rules.jurisdictions.get(j)
        zr = None if jr is None else jr.rule_for(z)
        return None if zr is None else zr.density_floor_lot_sqft(lot_area_sqft=a)

    area = lots["area_sqft"].to_numpy(dtype=float)
    density_floor_short = np.array([
        (f is not None and a > float(f))
        for f, a in zip((_floor(j, z, a) for j, z, a in zip(juris, zone, area)), area)
    ])
    lots["density_floor_short"] = density_floor_short

    review = (flag_suspect | (tier == "C") | unverified_zone | slope_bad
              | sewer_review | overlay_flag | frontage_unmeasured
              | density_floor_short)
    lots["triage"] = np.where(binding != "", "red",
                              np.where(review, "review", "green"))

    # Say WHY, in the row. A red lot has carried its `binding_constraint` since
    # the triage split was built; a yellow one carried nothing, and the eight
    # conditions above are not all recoverable from the exported columns --
    # `unverified_zone` needs rules.yaml and `slope_bad` needs a config flag
    # that is not in the CSV at all. So "why is this lot in the queue" could
    # only be answered by re-deriving the whole disjunction, which is how the
    # question gets answered WRONG. One joined column, computed here where the
    # arrays already exist, and the queue becomes sortable by cause.
    # Only for lots that ARE yellow. `review` is true on plenty of red lots
    # too -- triage just reaches `binding` first -- and naming yellow causes on
    # a lot already off the board would make the queue look bigger than it is.
    yellow = np.asarray(lots["triage"].to_numpy() == "review", dtype=bool)
    reasons = np.empty(n, dtype=object)
    reasons[:] = ""
    for name, mask in (
        ("suspect_geometry", flag_suspect),
        ("tier_c", tier == "C"),
        ("unverified_zone", unverified_zone),
        ("slope", slope_bad),
        ("sewer_unconfirmed", sewer_review),
        ("overlay", overlay_flag),
        ("frontage_unmeasured", frontage_unmeasured),
        ("density_floor", density_floor_short),
    ):
        m = np.asarray(mask, dtype=bool) & yellow
        if m.any():
            reasons[m] = [r + ("," if r else "") + name for r in reasons[m]]
    lots["review_reasons"] = reasons


def quads_if_split(lots, gates, rules, split):
    """Vector of carve-count estimates (0 where ineligible / nothing fits).

    Each carved lot must supply split.per_quad_lot_sqft() of buildable
    envelope AND satisfy the zone's quadplex minimum lot area. Interior-lot
    setback loss from new lot lines is NOT modeled (stated approximation).
    """
    import numpy as np

    per_quad = split.per_quad_lot_sqft()
    out = np.zeros(len(lots), dtype=int)
    for i, (jkey, zraw, area, env) in enumerate(zip(
        lots["jurisdiction"], lots["zone_raw"], lots["area_sqft"],
        lots["envelope_sqft"],
    )):
        rule = rules.jurisdictions[jkey].rule_for(zraw)
        if rule is None:
            continue
        denom = max(per_quad, rule.min_lot_sqft or 0.0)
        out[i] = min(
            int(float(area) // denom), int(float(env) // per_quad)
        )
    return np.where(gates["eligible"].to_numpy(), out, 0)


def acquisition_estimate(lots, screen):
    """(acq $, uses_sale bool) per lot.

    A post-cutoff arm's-length sale price where we have one — SALEPRICE >=
    recent_sale_min_price AND sale year >= recent_sale_min_year (SALEDATE is
    YYYYMM). Post-COVID prices are trusted; anything older or nominal falls back
    to TOTALVAL, the county Real Market Value (land+building market estimate,
    NOT the Measure-50 capped assessed value).
    """
    import numpy as np
    import pandas as pd

    price = pd.to_numeric(lots["SALEPRICE"], errors="coerce").fillna(0.0).to_numpy()
    saledate = pd.to_numeric(lots["SALEDATE"], errors="coerce").fillna(0.0).to_numpy()
    year = (saledate // 100).astype(int)  # YYYYMM -> YYYY
    rmv = pd.to_numeric(lots["TOTALVAL"], errors="coerce").fillna(0.0).to_numpy()
    uses_sale = (price >= screen.recent_sale_min_price) & (
        year >= screen.recent_sale_min_year)
    acq = np.where(uses_sale, price, rmv)
    return acq, uses_sale


def land_cost_per_unit(acq, doors):
    """acq / doors, NaN where doors <= 0 or acq <= 0 (no usable value)."""
    import numpy as np

    acq = np.asarray(acq, dtype=float)
    doors = np.asarray(doors, dtype=float)
    out = np.full(acq.shape, np.nan)
    ok = (doors > 0) & (acq > 0)
    out[ok] = acq[ok] / doors[ok]
    return out


def viability_tier(lpu, screen):
    """preferred (<= preferred_land_cost_per_unit) / viable (<= max) /
    over_budget / unknown (no usable acquisition value)."""
    import numpy as np

    lpu = np.asarray(lpu, dtype=float)
    return np.select(
        [np.isnan(lpu),
         lpu <= screen.preferred_land_cost_per_unit,
         lpu <= screen.max_land_cost_per_unit],
        ["unknown", "preferred", "viable"],
        default="over_budget",
    )


def sweep_fit_matrix(df, widths_ft, frontier_cells, res, sweep, flip_allowed):
    """Boolean matrix lots x sweep-widths for a constant-area sweep.

    Both orientations, matching the named-footprint treatment: width-facing
    (W along the front line, depth D = area/W into the lot) OR — where
    orientation policy allows — flipped (D along the front, W into the lot).
    The flip reads the frontier at the smallest grid width >= D (conservative).
    """
    import bisect

    import numpy as np

    cols = []
    for w in sweep.widths():
        d_needed = sweep.area_sqft / w
        try:
            w_idx = widths_ft.index(round(w, 4))
        except ValueError:
            cols.append(np.zeros(len(df), dtype=bool))
            continue
        wf = frontier_cells[:, w_idx] >= math.ceil(d_needed / res)
        d_idx = bisect.bisect_left(widths_ft, round(d_needed, 4))
        if d_idx < len(widths_ft):
            flipped = flip_allowed & (
                frontier_cells[:, d_idx] >= math.ceil(w / res)
            )
        else:
            flipped = np.zeros(len(df), dtype=bool)
        cols.append(wf | flipped)
    return np.column_stack(cols)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spot-check", type=int, default=36)
    args = ap.parse_args()

    import numpy as np
    import pandas as pd

    rules = load_rules()
    fps = load_footprints()
    meta = json.loads((DATA_DIR / "s6_meta.json").read_text(encoding="utf-8"))
    res = meta["grid_resolution_ft"]
    widths_ft = [round(w, 4) for w in meta["frontier_widths_ft"]]
    fps_meta = meta["footprints"]
    fp_names = [f["name"] for f in fps_meta]

    # Prefer the site-plan stage (superset of s6_lots) when it exists.
    stage = "s6s_lots" if stage_path("s6s_lots").exists() else "s6_lots"
    lots = read_stage(stage)
    has_siteplan = "parking_tier" in lots.columns
    struct_funnel = json.loads((DATA_DIR / "funnel.json").read_text(encoding="utf-8"))

    # Lot centroid (lat/lng, WGS84) for mapping / field navigation. The polygon
    # is dropped from s6 onward, so re-read the raw lot from s3 and project its
    # centroid 2913 -> 4326. Merged here so every downstream CSV carries it.
    import shapely
    from pyproj import Transformer

    from common import CRS_WGS84, CRS_WORKING
    _s3c = read_stage("s3_lots")[["TLID", "geom"]]
    _cent = shapely.centroid(np.array(_s3c["geom"].tolist(), dtype=object))
    _lng, _lat = Transformer.from_crs(CRS_WORKING, CRS_WGS84, always_xy=True).transform(
        shapely.get_x(_cent), shapely.get_y(_cent))
    _s3c = _s3c.assign(lat=np.round(_lat, 6), lng=np.round(_lng, 6))
    lots = lots.merge(_s3c[["TLID", "lat", "lng"]], on="TLID", how="left")

    # A parquet built before s4 measured lot width has no column for it, and
    # re-running s4 would mean re-running the envelope and the fit behind it
    # for a number that changes neither. Take it here instead, from the same
    # edges and the same lot polygon s4 would have used.
    if "lot_width_ft" not in lots.columns:
        from lotwidth import width_ft

        _geoms = dict(zip(_s3c["TLID"], _s3c["geom"]))
        _widths = []
        for _tlid, _juris, _tier, _ej, _fbj in zip(
            lots["TLID"], lots["jurisdiction"], lots["tier"],
            lots["edges_json"], lots["front_bearings_json"],
        ):
            _j = rules.jurisdictions.get(_juris)
            _m = None if _j is None else _j.lot_width_measure
            _w = width_ft(
                _m, _geoms.get(_tlid),
                json.loads(_ej) if _ej else [],
                json.loads(_fbj) if _fbj else [],
                _tier,
            )
            _widths.append(float("nan") if _w is None else _w)
        lots["lot_width_ft"] = _widths
        print(f"s7: lot width backfilled on "
              f"{int(np.isfinite(np.array(_widths, dtype=float)).sum()):,} lots")

    ocfg = load_overlays()
    lots["current_use"] = current_use_column(
        lots, fps.screen.vacant_max_improvement_value)
    gates, pol_funnel = policy_gates(lots, rules, ocfg, fps.screen)
    lots = lots.join(gates)

    # Finance tier from Real Market Value (TOTALVAL = land+building market
    # estimate; the Measure-50 capped ASSESSVAL is ~45% of it and unused here).
    # RMV is reasonable in aggregate but wrong on any single lot, so this slices
    # — it never gates. Cutlines are s7-time knobs.
    bldg = pd.to_numeric(lots["BLDGVAL"], errors="coerce").fillna(0.0).to_numpy()
    total = pd.to_numeric(lots["TOTALVAL"], errors="coerce").fillna(0.0).to_numpy()
    share = np.divide(bldg, total, out=np.zeros_like(bldg), where=total > 0)
    lots["improvement_share"] = share
    lots["finance_tier"] = np.where(
        bldg <= fps.screen.vacant_max_improvement_value, "vacant",
        np.where(share <= fps.screen.teardown_max_improvement_share,
                 "teardown_candidate", "improved"))

    # Acquisition estimate (post-COVID arm's-length sale where recorded, else
    # RMV). Land-cost-per-door tiering needs door counts, so it lands in the
    # split block below; the raw estimate is available to every lot here.
    acq, uses_sale = acquisition_estimate(lots, fps.screen)
    lots["acq_estimate"] = acq
    lots["acq_basis"] = np.where(uses_sale, "recent_sale", "market_value")

    # Slope tier from the configured statistic (cutlines are s7-time knobs).
    stat_col = f"slope_{ocfg.slope.stat}_pct"
    if stat_col in lots.columns:
        vals = lots[stat_col].to_numpy()
        lots["slope_tier"] = [
            ocfg.slope.tier(float(v)) if np.isfinite(v) else "unknown"
            for v in vals]
    else:
        lots["slope_tier"] = "unknown"

    # Orientation policy + coverage, from raw wf/df geometry results.
    for f in fps_meta:
        name, w_ft, d_ft = f["name"], f["width_ft"], f["depth_ft"]
        wf = lots[f"fits_{name}_wf"].to_numpy()
        df_ = lots[f"fits_{name}_df"].to_numpy() & lots["flip_allowed"].to_numpy()
        lots[f"fits_{name}"] = wf | df_
        lots[f"flip_only_{name}"] = df_ & ~wf
        cap = lots["cov_cap"].to_numpy()
        cov_ok = np.isnan(cap) | (w_ft * d_ft + lots["accessory"].to_numpy() <= cap)
        lots[f"fits_cov_{name}"] = lots[f"fits_{name}"] & cov_ok

    # Per-lot failure attribution + green/review/red triage (adds flag_suspect,
    # binding_constraint, triage). Computed on the full universe so elig inherits.
    flag_ovl_cols = [f"ovl_{s.key}" for s in ocfg.overlays
                     if s.action == "flag" and f"ovl_{s.key}" in lots.columns]
    min_stalls = fps.siteplan.min_stalls() if (has_siteplan and fps.siteplan) else 0
    attribute_and_triage(lots, fp_names, rules, has_siteplan, flag_ovl_cols,
                         min_stalls, ocfg)

    elig = lots[lots["eligible"]]
    frontier_cells_e = np.array(
        [json.loads(s) for s in elig["frontier_json"]], dtype=np.int32
    )
    head_mask = elig["tier"].isin(HEADLINE_TIERS).to_numpy()
    head = elig[head_mask]
    head_frontier = frontier_cells_e[head_mask]

    any_fit = np.zeros(len(head), dtype=bool)
    for name in fp_names:
        any_fit |= head[f"fits_{name}"].to_numpy()
    head = head.assign(_any=any_fit)

    # Split screen (attribute math — see footprints.yaml `split`).
    split = fps.split
    if split is not None:
        elig_any = np.zeros(len(elig), dtype=bool)
        for name in fp_names:
            elig_any |= elig[f"fits_{name}"].to_numpy()
        q = quads_if_split(elig, gates.loc[elig.index], rules, split)
        q = np.where(elig_any, q, 0)  # parent must host at least one quad shape
        split_candidate = q >= split.min_quads
        # Site-plan tightening: a 1-lot conversion counts only if a real plan
        # lays out (building + parking + driveway + open space), in every city
        # s6s could dimension. Non-evaluated lots keep the bare-rectangle
        # behavior. Split (multi-pod carve) geometric validation is deferred to
        # phase 2, so it's untouched.
        if has_siteplan:
            evaluated_e = elig["parking_tier"].to_numpy() != "not_evaluated"
            site_ok_e = np.where(evaluated_e, elig["site_plan_ok"].to_numpy(), True)
        else:
            evaluated_e = np.zeros(len(elig), dtype=bool)
            site_ok_e = np.ones(len(elig), dtype=bool)
        conv_ok = elig_any & ~split_candidate & site_ok_e
        # Acquisition economics: doors per lot, land cost per door, viability.
        # Conversion = units_per_quad on the existing lot; split = that x carved
        # pods (the theoretical max, so per-door cost is a floor). No fit / failed
        # site plan -> 0 doors (drops out of the viable list).
        doors = np.where(split_candidate, q * split.units_per_quad, 0.0)
        doors = np.where(conv_ok, float(split.units_per_quad), doors)
        lpu = land_cost_per_unit(elig["acq_estimate"].to_numpy(), doors)
        elig = elig.assign(
            quads_if_split=q,
            split_candidate=split_candidate,
            siteplan_evaluated=evaluated_e,
            site_ok_effective=site_ok_e,
            candidate_type=np.where(split_candidate, "split",
                                    np.where(conv_ok, "conversion", "no_fit")),
            doors_planned=doors.astype(int),
            land_cost_per_unit=lpu,
            viability=viability_tier(lpu, fps.screen))

    L: list[str] = []
    L.append("# Quadfit — Multnomah + Clackamas County quadplex buildability\n")
    L.append(f"Grid resolution {res} ft · headline universe = tiers A+B "
             f"({len(head):,} of {len(elig):,} eligible lots; geometry universe "
             f"{len(lots):,}). Results are an **upper bound** — see Blind spots.\n")

    unverified = [
        (k, z.zone) for k, j in rules.jurisdictions.items() if j.eligible
        for z in j.zones if z.confidence != "verified"
    ]
    if unverified:
        L.append(f"\n> ⚠ {len(unverified)} zone rules still `needs_verification`: "
                 + ", ".join(f"{k}:{z}" for k, z in unverified) + "\n")
    disabled = [k for k, j in rules.jurisdictions.items() if not j.eligible and j.zones]
    if disabled:
        L.append(f"\n> Jurisdictions disabled by policy: {', '.join(disabled)} "
                 "(re-enable with `eligible: true` + s7 re-run only)\n")

    L.append("\n## Exclusion funnel\n")
    L.append("| step | dropped | remaining |")
    L.append("|---|---:|---:|")
    L.append(f"| {struct_funnel[0]['step']} | | {struct_funnel[0]['count']:,} |")
    for row in struct_funnel[1:]:
        L.append(f"| {row['step']} | {row['dropped']:,} | {row['remaining']:,} |")
    for row in pol_funnel:
        L.append(f"| {row['step']} (policy) | {row['dropped']:,} | {row['remaining']:,} |")

    L.append("\n## Triage — green / needs-review / red\n")
    L.append("Every lot in the geometry universe is bucketed. **green** = passes all "
             "hard tests and the geometry is trustworthy — safe to pursue. **review** = "
             "passes the hard tests but a silent-killer or low-trust signal needs a "
             "human before diligence spend: a narrow flag-lot neck, an irregular shape, "
             "steep/unknown slope, far/unknown sewer, an unverified zone rule, or a "
             "flag overlay. **red** = a hard test fails (see binding constraint below). "
             "The review tier is where a false green would otherwise cost acquisition "
             "dollars — it is deliberately cautious.\n")
    tri_all = lots["triage"].value_counts()
    tri_head = head["triage"].value_counts()
    L.append("| triage | geometry universe | headline (tiers A+B) |")
    L.append("|---|---:|---:|")
    for t in ("green", "review", "red"):
        L.append(f"| {t} | {int(tri_all.get(t, 0)):,} | {int(tri_head.get(t, 0)):,} |")
    if "geometry_assumed" in lots.columns:
        ga = lots["geometry_assumed"].fillna(False).to_numpy().astype(bool)
        n_ga = int((ga & (lots["triage"].to_numpy() == "green")).sum())
        if n_ga:
            per = lots.loc[ga & (lots["triage"] == "green"),
                           "jurisdiction"].value_counts()
            L.append(
                f"\nOf the greens, **{n_ga:,}** rest on an assumed drive aisle "
                "(" + ", ".join(f"{k} {v:,}" for k, v in per.items())
                + ") — the plan is real and every other number is the city's "
                  "own; only the aisle width comes from the national standard, "
                  "because the city never published one. "
                  "`geometry_assumed` marks them in `lots_results.csv`.")
    L.append("\nThe human-review queue is `review_candidates.csv`.")

    # What the queue is actually made of. The binding-constraint table below
    # explains every RED lot and there was never a companion for the yellow
    # ones, so "why are thirty thousand lots in the queue" could only be
    # answered by re-deriving eight conditions from the CSV -- twice now, and
    # wrongly the first time. Sorted by lots, because that is the order the
    # human list is kept in and this is where its next item comes from.
    if "review_reasons" in lots.columns:
        rr = lots.loc[lots["triage"] == "review", "review_reasons"]
        counts: dict[str, int] = {}
        for cell in rr:
            for r in str(cell).split(","):
                if r:
                    counts[r] = counts.get(r, 0) + 1
        if counts:
            L.append("\n### Why each lot is in the queue\n")
            L.append("A lot can be held by more than one of these, so the "
                     "column sums past the queue total. **Solo** is the number "
                     "held by that reason ALONE -- the lots a single answer "
                     "would release, and the honest size of the prize.\n")
            solo = rr[~rr.str.contains(",", na=False)].value_counts()
            L.append("| reason | lots held | solo |")
            L.append("|---|---:|---:|")
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
                L.append(f"| {k} | {v:,} | {int(solo.get(k, 0)):,} |")
            L.append(f"| **queue total** | **{len(rr):,}** | |")

    L.append("\n## Binding constraint — what stops each lot (first-hit)\n")
    L.append("The single first reason each lot is not buildable. Structural drops are "
             "aggregate counts (those rows are removed early in the pipeline); policy, "
             "geometry, and site-plan reasons are per-lot. Sorted by how many lots each "
             "stops — the top rows are where design or acquisition strategy pays off "
             "most. Full table in `binding_constraints.csv`.\n")
    bc_rows = [(r["step"], int(r["dropped"])) for r in struct_funnel[1:]]
    bc = lots["binding_constraint"].value_counts()
    bc_rows += [(k, int(v)) for k, v in bc.items() if k != ""]
    bc_rows.sort(key=lambda kv: kv[1], reverse=True)
    buildable = int((lots["binding_constraint"] == "").sum())
    L.append("| binding constraint | lots |")
    L.append("|---|---:|")
    for step, cnt in bc_rows[:15]:
        L.append(f"| {step} | {cnt:,} |")
    L.append(f"| **(none — buildable)** | **{buildable:,}** |")

    L.append("\n## Eligible universe\n")
    L.append("| jurisdiction | lots | tier A | B | C | D |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for j, grp in elig.groupby("jurisdiction"):
        t = grp["tier"].value_counts()
        L.append(f"| {j} | {len(grp):,} | {t.get('A',0):,} | {t.get('B',0):,} "
                 f"| {t.get('C',0):,} | {t.get('D',0):,} |")

    L.append("\n## Current use & value screen\n")
    L.append("Existing " + " + ".join(fps.screen.exclude_current_use) +
             " excluded from the headline (counted in the funnel above; "
             "reversible in footprints.yaml `screen:`). TOTALVAL is the county "
             "**Real Market Value** (land+building market estimate — NOT the "
             "Measure-50 capped assessed value, which is ~45% of it and unused "
             "here). RMV is reasonable in aggregate but wrong on any single lot, "
             "so finance tiers slice the results; they never gate. Vacant = "
             f"improvement value ≤ ${fps.screen.vacant_max_improvement_value:,.0f} "
             "(a token shed is virtually vacant); teardown cutline: building ≤ "
             f"{fps.screen.teardown_max_improvement_share:.0%} of total market "
             "value. Dollar viability is in Acquisition economics below.\n")
    L.append("| finance tier | headline lots | any-pod fit % | median market "
             "value | median land value |")
    L.append("|---|---:|---:|---:|---:|")
    htot = pd.to_numeric(head["TOTALVAL"], errors="coerce")
    hland = pd.to_numeric(head["LANDVAL"], errors="coerce")
    for tier_name in ("vacant", "teardown_candidate", "improved"):
        mask = (head["finance_tier"] == tier_name).to_numpy()
        n = int(mask.sum())
        fit = _pct(int(head["_any"].to_numpy()[mask].sum()), n) if n else "n/a"
        mt = htot[mask].median() if n else float("nan")
        ml = hland[mask].median() if n else float("nan")
        L.append(f"| {tier_name} | {n:,} | {fit} | ${mt:,.0f} | ${ml:,.0f} |")
    L.append("\nPer-lot `current_use`, `finance_tier`, market/land value, last "
             "sale price/date, and the derived `acq_estimate` are in every CSV "
             "— filter to your own price tolerance.")

    L.append("\n## Footprint fit rates (headline: tiers A+B)\n")
    L.append("| footprint | fits | fit % | +coverage ok | flip-only | tier C fits |")
    L.append("|---|---:|---:|---:|---:|---:|")
    tier_c = elig[elig["tier"] == "C"]
    for name in fp_names:
        fits = int(head[f"fits_{name}"].sum())
        cov = int(head[f"fits_cov_{name}"].sum())
        flip_only = int(head[f"flip_only_{name}"].sum())
        c_fits = int(tier_c[f"fits_{name}"].sum())
        L.append(f"| {name} | {fits:,} | {_pct(fits, len(head))} | {cov:,} "
                 f"| {flip_only:,} | {c_fits:,}/{len(tier_c):,} |")

    L.append("\n### By jurisdiction\n")
    L.append("| jurisdiction | " + " | ".join(fp_names) + " | any |")
    L.append("|---|" + "---:|" * (len(fp_names) + 1))
    for j, grp in head.groupby("jurisdiction"):
        cells = [
            _pct(int(grp[f"fits_{name}"].sum()), len(grp)) for name in fp_names
        ]
        cells.append(_pct(int(grp["_any"].sum()), len(grp)))
        L.append(f"| {j} ({len(grp):,}) | " + " | ".join(cells) + " |")

    L.append("\n### By zone (10 largest)\n")
    L.append("| jurisdiction / zone | lots | " + " | ".join(fp_names) + " |")
    L.append("|---|---:|" + "---:|" * len(fp_names))
    zone_sizes = head.groupby(["jurisdiction", "zone"]).size().sort_values(ascending=False)
    for (j, z), n in zone_sizes.head(10).items():
        grp = head[(head["jurisdiction"] == j) & (head["zone"] == z)]
        cells = [_pct(int(grp[f"fits_{name}"].sum()), len(grp)) for name in fp_names]
        L.append(f"| {j} / {z} | {n:,} | " + " | ".join(cells) + " |")

    if len(fp_names) >= 2:
        L.append("\n### Marginal unlock between footprints\n")
        L.append("| gained by | over | lots unlocked | lots lost |")
        L.append("|---|---|---:|---:|")
        for a in fp_names:
            for b in fp_names:
                if a >= b:
                    continue
                fa, fb = head[f"fits_{a}"], head[f"fits_{b}"]
                L.append(f"| {b} | {a} | {int((fb & ~fa).sum()):,} "
                         f"| {int((fa & ~fb).sum()):,} |")

    for sweep in fps.constant_area_sweeps:
        L.append(f"\n## Fixed-area sweep — {sweep.area_sqft:.0f} sqft footprint\n")
        m = sweep_fit_matrix(head, widths_ft, head_frontier, res, sweep,
                             head["flip_allowed"].to_numpy())
        sw = sweep.widths()
        L.append("| width ft | depth ft | fit % (A+B) |")
        L.append("|---:|---:|---:|")
        rates = m.mean(axis=0)
        for w, r in zip(sw, rates):
            L.append(f"| {w:.1f} | {sweep.area_sqft / w:.1f} | {100*r:.1f}% |")
        best_i = int(np.argmax(rates))
        L.append(f"\n**County-wide optimum: {sw[best_i]:.1f} × "
                 f"{sweep.area_sqft / sw[best_i]:.1f} ft — fits "
                 f"{_pct(int(m[:, best_i].sum()), len(head))} of headline lots.**\n")
        L.append("Per-jurisdiction optima:\n")
        for j in sorted(head["jurisdiction"].unique()):
            mask = (head["jurisdiction"] == j).to_numpy()
            if not mask.any():
                continue
            jr = m[mask].mean(axis=0)
            bi = int(np.argmax(jr))
            L.append(f"- {j}: {sw[bi]:.1f} × {sweep.area_sqft / sw[bi]:.1f} ft "
                     f"({100*jr[bi]:.1f}%)")

    if split is not None:
        sc = elig[elig["split_candidate"]]
        conv = elig[elig["candidate_type"] == "conversion"]
        L.append("\n## Large-lot subdivision screen\n")
        L.append(f"Per carved quadplex lot: {split.quad_ground_sqft:,.0f} sqft "
                 f"buildable + {split.units_per_quad} units × "
                 f"{split.parking_slots_per_unit} slots × "
                 f"{split.parking_sqft_per_slot:,.0f} sqft = "
                 f"**{split.per_quad_lot_sqft():,.0f} sqft each** (stalls only, "
                 "no travel lanes; new interior lot-line setbacks not modeled; "
                 "zone quadplex minimum lot area also enforced per carved lot). "
                 "Conversion lots (below) carry NO parking requirement.\n")
        L.append(f"- **Split candidates (≥{split.min_quads} quads): {len(sc):,} lots** "
                 f"→ theoretical {int(sc['quads_if_split'].sum()):,} quadplexes "
                 f"({int(sc['quads_if_split'].sum()) * split.units_per_quad:,} units)")
        L.append(f"- 1-for-1 conversion candidates (fit, not split-worthy): {len(conv):,} lots\n")
        L.append("| jurisdiction | split lots | theoretical quads |")
        L.append("|---|---:|---:|")
        for j, grp in sc.groupby("jurisdiction"):
            L.append(f"| {j} | {len(grp):,} | {int(grp['quads_if_split'].sum()):,} |")
        L.append("\nTop 15 by carve count:\n")
        L.append("| TLID | address | jurisdiction / zone | lot sqft | buildable sqft | quads |")
        L.append("|---|---|---|---:|---:|---:|")
        for row in sc.sort_values("quads_if_split", ascending=False).head(15).itertuples(index=False):
            L.append(f"| {row.TLID} | {row.SITEADDR or '—'} | {row.jurisdiction} / "
                     f"{row.zone} | {row.area_sqft:,.0f} | {row.envelope_sqft:,.0f} "
                     f"| {row.quads_if_split} |")

        # --- Acquisition economics: land cost per door --------------------
        fits_any_e = np.logical_or.reduce(
            [elig[f"fits_{n}"].to_numpy() for n in fp_names])
        lpu = elig["land_cost_per_unit"].to_numpy()
        via = elig["viability"].to_numpy()
        used_sale = elig["acq_basis"].to_numpy() == "recent_sale"
        viable_mask = np.isin(via, ("preferred", "viable"))
        pref_mask = via == "preferred"
        n_fit = int(fits_any_e.sum())
        n_viable = int(viable_mask.sum())
        n_pref = int(pref_mask.sum())
        pref_k = fps.screen.preferred_land_cost_per_unit
        max_k = fps.screen.max_land_cost_per_unit
        L.append("\n## Acquisition economics — land cost per door\n")
        L.append(
            "Acquisition estimate = a post-"
            f"{fps.screen.recent_sale_min_year} arm's-length sale where recorded "
            f"({_pct(int((used_sale & fits_any_e).sum()), n_fit)} of fitting "
            "lots), else TOTALVAL (RMV — reasonable in aggregate, wrong on any "
            f"single lot). Land cost per door = acquisition ÷ doors, where doors "
            f"= {split.units_per_quad} for a 1-lot conversion and "
            f"{split.units_per_quad} × carved pods for a split (split door "
            "counts are the theoretical maximum, so per-door cost there is a "
            f"floor). Preferred ≤ ${pref_k:,.0f}, ceiling ≤ ${max_k:,.0f}. This "
            "is a **slice, not a gate** — nothing above is dropped.\n")
        L.append(
            f"**Of {n_fit:,} fitting eligible lots, {n_viable:,} clear the "
            f"${max_k:,.0f}/door ceiling ({_pct(n_viable, n_fit)}); {n_pref:,} "
            f"clear the ${pref_k:,.0f}/door target ({_pct(n_pref, n_fit)}).** "
            "Ranked cheapest-dirt-first in `viable_candidates.csv`.\n")
        L.append(f"| candidate type | fitting lots | ≤ ${max_k:,.0f}/door "
                 f"| ≤ ${pref_k:,.0f}/door | median $/door |")
        L.append("|---|---:|---:|---:|---:|")
        groups = [
            ("1-for-1 conversion",
             elig["candidate_type"].to_numpy() == "conversion"),
            (f"split (≥{split.min_quads} quads)",
             elig["split_candidate"].to_numpy()),
            ("of which vacant land",
             (elig["finance_tier"].to_numpy() == "vacant") & fits_any_e),
            ("all fitting", fits_any_e),
        ]
        for label, gmask in groups:
            n = int(gmask.sum())
            v = int((gmask & viable_mask).sum())
            p = int((gmask & pref_mask).sum())
            grp_lpu = lpu[gmask]
            has_val = n and bool(np.isfinite(grp_lpu).any())
            med_s = f"${np.nanmedian(grp_lpu):,.0f}" if has_val else "n/a"
            L.append(f"| {label} | {n:,} | {v:,} | {p:,} | {med_s} |")
        L.append("\nDoors, `acq_estimate`, `acq_basis`, `land_cost_per_unit`, and "
                 "`viability` are in the split/conversion CSVs; "
                 "`viable_candidates.csv` is the union that clears the ceiling, "
                 "cheapest first.")

    # --- Site-plan tightening ---------------------------------------------
    if has_siteplan and fps.siteplan is not None:
        sp = fps.siteplan
        pil = elig[elig["parking_tier"] != "not_evaluated"]
        if len(pil):
            geom_fit = np.logical_or.reduce(
                [pil[f"fits_{n}"].to_numpy() for n in fp_names])
            n_geom = int(geom_fit.sum())
            n_site = int(pil["site_plan_ok"].to_numpy().sum())
            cities = sp.cities_it_can_dimension()
            declined = sorted(set(sp.geometry) - set(cities))
            L.append("\n## Site-plan tightening\n")
            L.append(
                "A bare pod rectangle fitting the envelope (s6) is necessary but "
                "not sufficient. This stage lays out a full plan — pod + driveway "
                "+ 90° parking + whatever private open space the city requires — "
                "and counts a lot as buildable only if the plan resolves. "
                "Parking tiers are "
                "the marketability target "
                f"({sp.min_stalls()}/{sp.target_stalls()}/{sp.preferred_stalls()} "
                "stalls = 1 / 1.5 / 2 per unit).\n")
            L.append(
                "Every lot below sits in a city whose own code states both a stall "
                "size and a drive-aisle width, and is laid out to that city's "
                "numbers — never to another's. That now covers the driveway too: "
                "the approach width, the lane, the building gap and the "
                "open-space reserve are each city's own. Cities laid out: "
                + ", ".join(f"**{c}**" for c in cities) + ".")
            if declined:
                L.append(
                    "Read and declined for want of an aisle width (their codes "
                    "dimension a space and never the drive that reaches it): "
                    + ", ".join(f"**{c}**" for c in declined)
                    + ". Every other city is unread and passes through as "
                      "`not_evaluated`.\n")
            else:
                L.append("")
            assumed_cities = sp.cities_on_an_assumed_aisle()
            if assumed_cities:
                L.append(
                    "One exception to \"never to another's\": "
                    + ", ".join(f"**{c}**" for c in assumed_cities)
                    + " state a stall and no aisle width anywhere — checked to "
                      "the end of the state's own single-family redirect — so "
                      "their courts are drawn to an **assumed 24 ft aisle** "
                      "(ULI/NPA *Dimensions of Parking* via SUDAS 8B-1, "
                      "85th-percentile design vehicle). Under ORS 197A.400 a "
                      "city may apply only clear and objective standards to "
                      "housing, and a width nobody wrote down is not one, so "
                      "these lots grade normally, green included. Filter them "
                      "with the `geometry_assumed` column.\n")
            capped = [(c, sp.stall_cap_for(c)) for c in cities
                      if sp.stall_cap_for(c) < sp.preferred_stalls()]
            if capped:
                L.append(
                    "A stated MAXIMUM binds in "
                    + ", ".join(f"**{c}** ({n} stalls)" for c, n in capped)
                    + " — the higher tiers are not on offer there at any lot "
                      "size.\n")
            L.append(f"- Eligible lots in scope that fit a bare pod: **{n_geom:,}**")
            L.append(f"- …that also lay out a full site plan: **{n_site:,}** "
                     f"({_pct(n_site, n_geom)}) — the rest fail on parking, "
                     "driveway, or open space\n")
            L.append("| parking tier | lots | share of pod-fitting |")
            L.append("|---|---:|---:|")
            for t in ("preferred", "target", "minimum", "fail"):
                m = int((pil["parking_tier"] == t).to_numpy().sum())
                L.append(f"| {t} | {m:,} | {_pct(m, n_geom)} |")
            if len(cities) > 1:
                L.append("\n| city | stall | aisle | cap | evaluated | "
                         "site plan resolves |")
                L.append("|---|---|---|---:|---:|---:|")
                for c in cities:
                    g = sp.geometry_for(c)
                    m = (pil["jurisdiction"] == c).to_numpy()
                    ok_c = int((pil["site_plan_ok"].to_numpy() & m).sum())
                    # The one number in this table that may not be the city's:
                    # an assumed aisle is marked where it is printed, because a
                    # reader comparing this row to the code will not find it.
                    aisle = (f"{g.aisle_one_way_ft} / {g.aisle_two_way_ft} ft"
                             + (" **(assumed)**" if g.aisle_assumed else ""))
                    L.append(
                        f"| {c} | {g.stall_width_ft} × {g.stall_depth_ft} ft "
                        f"| {aisle} "
                        f"| {sp.stall_cap_for(c)} | {int(m.sum()):,} "
                        f"| {ok_c:,} ({_pct(ok_c, int(m.sum()))}) |")
            methods = [(meth, int((pil["layout_method"] == meth).to_numpy().sum()))
                       for meth in ("townhome_rear_court",)]
            method_str = ", ".join(f"{meth} {n:,}" for meth, n in methods if n)
            ok_os = int(pil["open_space_ok"].to_numpy().sum())
            L.append(f"\nLayout method used: {method_str or 'none'}. "
                     f"Open-space reservation satisfied on {ok_os:,} of {len(pil):,} "
                     "evaluated lots. Sampled site-plan drawings are in "
                     "`siteplans.geojson`; per-lot `parking_tier`, `stalls_provided`, "
                     "`layout_method`, `driveway_len_ft`, `driveway_width_ft`, "
                     "`open_space_req_sqft` and `open_space_ok` are in "
                     "`conversion_candidates.csv`.")
            L.append("\nDriveway, curb cut and open space, per city:\n")
            L.append("| city | side lane | curb cut | private open space |")
            L.append("|---|---|---|---|")
            for c in cities:
                dw = sp.driveway_for(c)
                osp = open_space_label(dw)
                L.append(f"| {c} | {sp.lane_ft_for(c):g} ft "
                         f"| {sp.curb_cut_ft_for(c):g} ft | {osp} |")
            L.append(
                "\nWhat this does NOT check: the placement rules the rear court "
                "satisfies by construction rather than by measurement — the "
                "share-of-frontage caps, the front-yard area shares, the "
                "façade-relative bans. Every stall drawn here is behind the "
                "building, which is what each of those asks for, so they are "
                "mirrored and not tested; a front-court typology would have to "
                "test them. What IS checked is the street setback: Happy "
                "Valley LDC 16.43.030.E.4 sets a parking area back from a "
                "street by the ZONE'S building setback, printing only a "
                "ten-foot floor of its own, and the corpus now carries a "
                "standard stated as equal to another one. The envelope this "
                "stage lays out in is already cut back by that same "
                "setback, so the rule binds on no lot in the city — checked "
                "on every one of them, and satisfied by the sentence that "
                "made it.")

    # --- Phase 2 sections: overlays / slope / sewer / data coverage --------
    flag_specs = [s for s in ocfg.overlays
                  if s.action == "flag" and f"ovl_{s.key}" in elig.columns]
    carve_specs = [s for s in ocfg.overlays
                   if s.action == "carve" and f"ovl_{s.key}" in elig.columns]
    if flag_specs or carve_specs:
        L.append("\n## Overlay exposure on eligible lots\n")
        L.append("Kill overlays already removed in the funnel above. Carve "
                 "overlays are subtracted from buildable area before fitting "
                 "(their effect is inside the fit numbers); flags add "
                 "cost/process but do not block.\n")
        L.append("| overlay | action | eligible lots touched | avg sqft where touched |")
        L.append("|---|---|---:|---:|")
        for s in carve_specs + flag_specs:
            col = elig[f"ovl_{s.key}"]
            n = int(col.sum())
            avg = elig.loc[col, f"ovl_{s.key}_sqft"].mean() if n else 0.0
            L.append(f"| {s.name} | {s.action} | {n:,} | {avg:,.0f} |")

    if (lots["slope_tier"] != "unknown").any():
        L.append(f"\n## Slope tiers (statistic: {ocfg.slope.stat}, cutlines "
                 f"{ocfg.slope.ideal_max_pct:.0f}% / "
                 f"{ocfg.slope.tolerable_max_pct:.0f}% — adjustable, s7-only)\n")
        L.append("| tier | headline lots | share | any-pod fit % |")
        L.append("|---|---:|---:|---:|")
        head_any = head["_any"].to_numpy()
        for tier in ("ideal", "tolerable", "cost_prohibitive", "unknown"):
            mask = (head["slope_tier"] == tier).to_numpy()
            n = int(mask.sum())
            fit = _pct(int(head_any[mask].sum()), n)
            L.append(f"| {tier} | {n:,} | {_pct(n, len(head))} | {fit} |")
        L.append("\nSlope tiers do NOT gate the headline numbers — filter the "
                 "CSVs on `slope_tier` to apply your cost tolerance.")

    if "sewer_main_dist_ft" in elig.columns and split is not None:
        sc_l = elig[elig["split_candidate"]]
        if len(sc_l):
            L.append("\n## Sewer main proximity — split candidates\n")
            L.append("| distance to mapped main | split lots |")
            L.append("|---|---:|")
            d = sc_l["sewer_main_dist_ft"].to_numpy()
            bins = [(0, 100, "in/adjacent street (<=100 ft)"),
                    (100, 300, "close (100-300 ft)"),
                    (300, 1000, "extension likely (300-1000 ft)"),
                    (1000, float("inf"), "far / unserved (>1000 ft)")]
            for lo, hi, label in bins:
                n = int(((d >= lo) & (d < hi)).sum())
                L.append(f"| {label} | {n:,} |")
            L.append("\nConversion lots are assumed already served (existing "
                     "home). Unincorporated pockets have no public sewer "
                     "layer — distances there are to city mains, proxy only.")

    themes = [(f"ovl:{s.key}", s.name, s.coverage) for s in ocfg.overlays]
    themes += [("slope", "Slope/DEM", ocfg.slope_coverage),
               ("sewer", "Sewer mains", ocfg.sewer_coverage)]
    if any(cov for _, _, cov in themes):
        L.append("\n## Data coverage by municipality (A parcel-grade / "
                 "B regional fallback / C coarse-partial / X none)\n")
        jlist = [j for j in sorted(rules.jurisdictions)
                 if rules.jurisdictions[j].eligible or rules.jurisdictions[j].zones]
        L.append("| theme | " + " | ".join(jlist) + " |")
        L.append("|---|" + "---:|" * len(jlist))
        for _, name, cov in themes:
            if not cov:
                continue
            row = [cov[j].grade if j in cov else "–" for j in jlist]
            L.append(f"| {name} | " + " | ".join(row) + " |")
        notes = sorted({f"{j}: {c.note}" for _, _, cov in themes
                        for j, c in cov.items() if c.grade in ("C", "X") and c.note})
        if notes:
            L.append("\nCoverage caveats:")
            for note in notes:
                L.append(f"- {note}")

    L.append("\n## Max-rectangle frontier distribution (tiers A+B)\n")
    L.append("| width ft | median max depth | 25th pct | 75th pct | % supporting ≥25 ft depth |")
    L.append("|---:|---:|---:|---:|---:|")
    for w in (18.0, 20.0, 25.0, 30.0, 40.0):
        if round(w, 4) not in widths_ft:
            continue
        wi = widths_ft.index(round(w, 4))
        depths = head_frontier[:, wi] * res
        L.append(f"| {w:.0f} | {np.median(depths):.1f} | "
                 f"{np.percentile(depths, 25):.1f} | {np.percentile(depths, 75):.1f} | "
                 f"{100 * (depths >= 25).mean():.1f}% |")

    if "slope_source" in lots.columns:
        src = lots["slope_source"].astype(str)
        n10 = int((src == "dem_10m").sum())
        if n10:
            L.append("\n### Which DEM answered\n")
            L.append("USGS 3DEP's 1 m lidar for this metro comes from two "
                     "projects that stop at about longitude -122.48. East of "
                     "that line there is no 1 m product at any vintage, so "
                     "those lots are read off the seamless 1/3 arc-second "
                     f"(~10 m) DEM instead - {n10:,} lots. The statistic there "
                     "is the MAXIMUM slope over a "
                     f"{ocfg.slope.fallback_10m_window * 10:.0f} m box, not a "
                     "polygon percentile, because a lot is one to four cells "
                     "wide at that resolution.\n")
            L.append("| jurisdiction | 1 m lidar | 10 m fallback | no data |")
            L.append("|---|---:|---:|---:|")
            for jk in sorted(lots["jurisdiction"].astype(str).unique()):
                m = (lots["jurisdiction"].astype(str) == jk)
                a = int((m & (src == "dem_1m")).sum())
                b = int((m & (src == "dem_10m")).sum())
                c = int((m & (src == "none")).sum())
                L.append(f"| {jk} | {a:,} | {b:,} | {c:,} |")
            if not ocfg.slope.fallback_10m_may_green:
                held = int(((src == "dem_10m")
                            & (lots["triage"] == "review")).sum())
                L.append(
                    f"\n**{held:,} lots are held at review by the source "
                    "alone** - they pass every hard test and the coarse DEM "
                    "calls them buildable, but a coarse answer is not "
                    "currently allowed to grade green "
                    "(`slope.fallback_10m_may_green: false`). Measured against "
                    "the 1 m answer where both DEMs exist, the rule used here "
                    "wrongly clears 1.50% of genuinely steep lots.")
            else:
                # The same sentence from the other side of the decision. A
                # reader who does not know WHICH greens rest on the coarse map
                # cannot act on the 1.50%, and "filter it yourself" is not an
                # answer if nobody says how many there are to filter.
                on_coarse = int(((src == "dem_10m")
                                 & (lots["triage"] == "green")).sum())
                L.append(
                    f"\n**{on_coarse:,} of the greens rest on the coarse DEM** "
                    "and are graded green like any other, decided 2026-09-03 "
                    "(`slope.fallback_10m_may_green: true`). Measured against "
                    "the 1 m answer where both DEMs exist, the rule used here "
                    "wrongly clears 1.50% of genuinely steep lots, so about "
                    f"{round(on_coarse * 0.015):,} of these should be steeper "
                    "on the ground than they look here - one wasted site visit "
                    "each, found on the first one. Filter them with "
                    "`slope_source == 'dem_10m'` in `lots_results.csv`.")

    L.append("\n## Blind spots (results are a ceiling)\n")
    L.append("- Private easements (title reports only) are not modeled.")
    L.append("- Portland tree preservation and historic/design review are NOT "
             "modeled (cost/process, not mapped kills). Environmental overlays, "
             "floodplain, and slope ARE applied per the overlay/slope sections "
             "above — but only where source data exists (see coverage matrix; "
             "slope 'unknown' lots have neither a 1 m tile nor a 10 m cell).")
    L.append("- Existing structures assumed demolished; building value & year built "
             "are carried per-lot for later filtering.")
    L.append("- Conversion lots in a city whose code states a stall AND an aisle: "
             "a full plan — building + driveway + 90° parking + that city's own "
             "open-space reserve, where it states one — "
             "is laid out to that city's own dimensions and tightens the verdict "
             "(see Site-plan tightening). Everywhere else on-lot parking is out "
             "of scope (bare-rectangle fit only), either because the city "
             "dimensions a space and never the drive that reaches it, or because "
             "nobody has read it. Split lots: parking buffer is stalls-only (area "
             "allowance, no geometry check) everywhere — deferred to phase 2.")
    L.append("- Split screen ignores subdivision road/utility/frontage requirements "
             "and new interior-lot-line setbacks — treat as a lead list, not a yield.")
    L.append("- Envelope + raster are conservative (~±" + str(res) + " ft), so the "
             "geometric side slightly UNDER-counts fits; unmodeled overlays "
             "over-count. Net: treat as upper bound.")

    (DATA_DIR / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'summary.md'}")

    # Per-lot CSVs. Master = whole geometry universe with policy_exclusion.
    phase2_cols = [c for c in lots.columns
                   if c.startswith("ovl_") and not c.endswith("_sqft")]
    phase2_cols += [c for c in (
        "slope_p85_pct", "slope_tier", "slope_source", "sewer_main_dist_ft",
        "in_sewer_district", "envelope_setback_sqft") if c in lots.columns]
    # Why an Oregon City or Tualatin lot is sitting in the review queue with
    # nothing apparently wrong with it: its street frontage fell short of a
    # number the code measures across the middle of the lot, and the pipeline
    # cannot take that measurement. Same idea as `geometry_assumed` -- the
    # caveat travels with the row, not three files away in rules.yaml.
    if "frontage_unmeasured" in lots.columns:
        phase2_cols.append("frontage_unmeasured")
    # And why a large Oregon City lot is in the queue looking perfect: it is
    # above its zone's minimum density, so four homes may not be enough on it.
    # Same discipline -- the caveat travels with the row.
    if "density_floor_short" in lots.columns:
        phase2_cols.append("density_floor_short")
    # `geometry_assumed` rides in the CSV beside the plan it qualifies: a
    # reviewer opening a Milwaukie or Wilsonville row needs the caveat next to
    # the stall count, not three files away in footprints.yaml.
    siteplan_cols = [c for c in (
        "parking_tier", "stalls_provided", "layout_method", "site_plan_ok",
        "geometry_assumed", "driveway_len_ft", "open_space_ok",
        "utility_run_ft") if c in lots.columns]
    screen_cols = ["current_use", "finance_tier", "improvement_share",
                   "LANDVAL", "SALEPRICE", "SALEDATE", "acq_estimate", "acq_basis"]
    csv_cols = [
        "TLID", "SITEADDR", "lat", "lng", "jurisdiction", "zone", "tier",
        "area_sqft", "envelope_sqft", "frontage_ft",
        # Next to the frontage, because it is not the frontage. In Oregon City
        # and Tualatin the minimum a lot is judged against is a WIDTH across
        # the middle, and since 55d1e34c the verdict uses this column rather
        # than the street edge. A reviewer looking at a lot that just turned
        # red for `below_min_frontage`, or one held at `frontage_unmeasured`,
        # has to be able to see the number the screen decided on. Blank means
        # the shape declined to be measured, or the city states a frontage and
        # this never applied to it.
        "lot_width_ft", "YEARBUILT", "BLDGSQFT",
        "BLDGVAL", "TOTALVAL", "split_zone", "policy_exclusion", "eligible",
        # `binding_constraint` says why a lot is RED. `review_reasons` says why
        # it is YELLOW -- next to it, because the two answer the same question
        # for the two colours and nobody should have to know which is which.
        "flag_suspect", "binding_constraint", "review_reasons", "triage",
    ] + screen_cols \
      + [f"fits_{n}" for n in fp_names] + [f"fits_cov_{n}" for n in fp_names] \
      + phase2_cols + siteplan_cols
    lots[csv_cols].to_csv(DATA_DIR / "lots_results.csv", index=False)
    print(f"wrote {DATA_DIR / 'lots_results.csv'} ({len(lots):,} rows)")

    # Binding-constraint histogram (structural aggregate + per-lot first-hit) +
    # the human-review queue (passes the hard tests but needs a look).
    hist = [(r["step"], int(r["dropped"])) for r in struct_funnel[1:]]
    hist += [(k, int(v)) for k, v in lots["binding_constraint"].value_counts().items()
             if k != ""]
    hist.sort(key=lambda kv: kv[1], reverse=True)
    hist.append(("(none - buildable)", int((lots["binding_constraint"] == "").sum())))
    pd.DataFrame(hist, columns=["binding_constraint", "lots"]).to_csv(
        DATA_DIR / "binding_constraints.csv", index=False)
    review = lots[lots["triage"] == "review"]
    review[csv_cols].to_csv(DATA_DIR / "review_candidates.csv", index=False)
    print(f"wrote binding_constraints.csv ({len(hist)} reasons) + "
          f"review_candidates.csv ({len(review):,})")

    if split is not None:
        # Per-door economics columns (elig-only — need door counts).
        econ_cols = ["candidate_type", "doors_planned", "land_cost_per_unit",
                     "viability"]
        sub_cols = [
            "TLID", "SITEADDR", "lat", "lng", "jurisdiction", "zone", "tier",
            "area_sqft", "envelope_sqft", "frontage_ft", "YEARBUILT", "BLDGSQFT",
            "BLDGVAL", "TOTALVAL",
        ] + screen_cols + phase2_cols
        sc = elig[elig["split_candidate"]].sort_values("quads_if_split", ascending=False)
        sc[sub_cols + ["quads_if_split"] + econ_cols].to_csv(
            DATA_DIR / "split_candidates.csv", index=False)
        conv_mask = elig["candidate_type"].to_numpy() == "conversion"
        conv_extra = [c for c in ("parking_tier", "stalls_provided",
                                  "layout_method", "driveway_len_ft",
                                  "open_space_ok", "utility_run_ft")
                      if c in elig.columns]
        elig[conv_mask][sub_cols + [f"fits_{n}" for n in fp_names]
                        + econ_cols + conv_extra].to_csv(
            DATA_DIR / "conversion_candidates.csv", index=False)
        # Viable list: every fitting lot clearing the per-door ceiling, cheapest
        # dirt first — the practical target list.
        viable = elig[elig["viability"].isin(("preferred", "viable"))].sort_values(
            "land_cost_per_unit")
        viable[sub_cols + ["quads_if_split"] + econ_cols].to_csv(
            DATA_DIR / "viable_candidates.csv", index=False)
        print(f"wrote split_candidates.csv ({int(elig['split_candidate'].sum()):,}) "
              f"+ conversion_candidates.csv ({int(conv_mask.sum()):,}) "
              f"+ viable_candidates.csv ({len(viable):,})")

    _write_spot_check(elig, fps, meta, args.spot_check)
    if has_siteplan:
        _write_siteplans(elig, args.spot_check)
    print("s7 done.")


def _write_siteplans(lots, n_sample: int) -> None:
    """Sampled per-lot site-plan drawings (building/driveway/stalls/utility)
    from the s6s `siteplan_json` WKB-hex geometry, with lot + envelope context.
    Reprojected to WGS84 for geojson.io. Evaluated, `site_plan_ok` lots only,
    sampled ROUND-ROBIN across the cities laid out — `head()` would have handed
    back one city's drawings once this stage stopped being one city."""
    import shapely
    from pyproj import Transformer

    from common import CRS_WGS84, CRS_WORKING

    if "siteplan_json" not in lots.columns:
        return
    pil = lots[(lots["parking_tier"] != "not_evaluated")
               & lots["site_plan_ok"].astype(bool)]
    if not len(pil):
        print("no site_plan_ok lots — skipping siteplans.geojson")
        return
    per_city = pil.groupby("jurisdiction", sort=True, group_keys=False)
    take = max(1, n_sample // max(1, pil["jurisdiction"].nunique()))
    sample = per_city.head(take).head(n_sample)
    s3 = read_stage("s3_lots")[["TLID", "geom"]].rename(columns={"geom": "lot_geom"})
    s5 = read_stage("s5o_lots")[["TLID", "geom"]].rename(columns={"geom": "env_geom"})
    sample = sample.merge(s3, on="TLID").merge(s5, on="TLID")

    tr = Transformer.from_crs(CRS_WORKING, CRS_WGS84, always_xy=True)

    def to4326(geom):
        import numpy as np

        def _fn(coords):
            x, y = tr.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, _fn)

    feats = []
    for row in sample.itertuples(index=False):
        props = {
            "tlid": row.TLID, "addr": row.SITEADDR, "zone": row.zone,
            "parking_tier": row.parking_tier, "stalls": int(row.stalls_provided),
            "layout_method": row.layout_method,
            "driveway_len_ft": round(float(row.driveway_len_ft), 1),
        }
        if row.lot_geom is not None and not row.lot_geom.is_empty:
            feats.append({"type": "Feature", "properties": {**props, "role": "lot"},
                          "geometry": json.loads(shapely.to_geojson(to4326(row.lot_geom)))})
        if row.env_geom is not None and not row.env_geom.is_empty:
            feats.append({"type": "Feature", "properties": {**props, "role": "envelope"},
                          "geometry": json.loads(shapely.to_geojson(to4326(row.env_geom)))})
        for role, hexwkb in json.loads(row.siteplan_json).items():
            g = shapely.from_wkb(bytes.fromhex(hexwkb))
            feats.append({"type": "Feature", "properties": {**props, "role": role},
                          "geometry": json.loads(shapely.to_geojson(to4326(g)))})

    doc = {"type": "FeatureCollection", "features": feats}
    (DATA_DIR / "siteplans.geojson").write_text(json.dumps(doc), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'siteplans.geojson'} "
          f"({len(sample)} lots, {len(feats)} features)")


def _write_spot_check(lots, fps, meta, n_sample: int) -> None:
    import shapely
    from pyproj import Transformer

    import s6_fit
    from common import CRS_WGS84, CRS_WORKING

    s3 = read_stage("s3_lots")[["TLID", "geom"]].rename(columns={"geom": "lot_geom"})
    s5 = read_stage("s5o_lots")[["TLID", "geom"]].rename(columns={"geom": "env_geom"})
    sample = (
        lots.groupby(["jurisdiction", "tier"], group_keys=False, sort=False)
        .head(2)
        .head(n_sample)
    )
    sample = sample.merge(s3, on="TLID").merge(s5, on="TLID")

    res = meta["grid_resolution_ft"]
    cfg = {
        "res": res,
        "width_cells": [round(w / res) for w in meta["frontier_widths_ft"]],
        "footprints": [(f["name"], f["width_ft"], f["depth_ft"]) for f in meta["footprints"]],
    }
    s6_fit._init_worker(cfg)
    fp0 = fps.footprints[0]

    tr = Transformer.from_crs(CRS_WORKING, CRS_WGS84, always_xy=True)

    def to4326(geom):
        import numpy as np

        def _fn(coords):
            x, y = tr.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, _fn)

    feats = []
    for row in sample.itertuples(index=False):
        r = s6_fit.fit_lot(
            shapely.to_wkb(row.env_geom),
            json.loads(row.front_bearings_json),
            bool(row.flip_allowed),
            collect_placement=(fp0.width_ft, fp0.depth_ft),
        )
        props = {
            "tlid": row.TLID, "addr": row.SITEADDR, "jurisdiction": row.jurisdiction,
            "zone": row.zone, "tier": row.tier,
        }
        feats.append({"type": "Feature", "properties": {**props, "role": "lot"},
                      "geometry": json.loads(shapely.to_geojson(to4326(row.lot_geom)))})
        if not row.env_geom.is_empty:
            feats.append({"type": "Feature", "properties": {**props, "role": "envelope"},
                          "geometry": json.loads(shapely.to_geojson(to4326(row.env_geom)))})
        if r["placement"]:
            rect = shapely.from_wkb(r["placement"])
            feats.append({"type": "Feature",
                          "properties": {**props, "role": f"fit_{fp0.name}"},
                          "geometry": json.loads(shapely.to_geojson(to4326(rect)))})

    doc = {"type": "FeatureCollection", "features": feats}
    (DATA_DIR / "spot_check.geojson").write_text(json.dumps(doc), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'spot_check.geojson'} ({len(feats)} features)")


if __name__ == "__main__":
    main()
