"""Condominium / air-parcel detection.

A condominium unit is recorded as its own taxlot, but it is not land — it is a
volume inside someone else's building. Nothing can be built on it. Left in the
corpus these rows inflate every count in dense zones and then fail geometry for
the wrong reason.

Quadfit's condo handling looked for *coincident geometry stacks* and reported
``condo_stack: 0 dropped`` while 43,604 Portland taxlots under 2,000 sqft sat in
the data — 75% of RM3/RM4/RX and 80% of CX/CE/EX. The stack test never fired
because these parcels are separately drawn, not stacked duplicates.

What the data actually shows (Multnomah, inside UGB):

======  ======  ==============  ===============
code     lots   median lot sqft  median bldg sqft
======  ======  ==============  ===============
122     18,338            46.7                0
102     22,273           459.8              915
======  ======  ==============  ===============

A 46 sq ft "lot" is an air parcel. A 460 sq ft lot under a 915 sq ft building is
a stacked unit. For comparison, genuine lots have a building-to-lot ratio whose
99th percentile is 1.28 — a ratio above 1.5 means the building cannot be sitting
on that parcel alone.

**Bias.** A false exclusion silently deletes an acquisition target we never
learn about; a false inclusion costs one review. So only unambiguous cases are
excluded. Anything merely suspicious is flagged for REVIEW and kept.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Mapping

#: Multnomah County assessor property codes that denote condominium interests.
#: County-specific: Clackamas codes differently, so this is a supporting signal,
#: never the only one. Keyed by county letter as carried in the RLIS taxlot data.
CONDO_PROP_CODES: dict[str, frozenset[str]] = {
    "M": frozenset({"102", "122", "132", "202"}),
}

#: No jurisdiction in the corpus sets a fourplex minimum lot area below
#: 1,500 sqft, and a four-unit pod needs roughly 2,000 sqft of footprint. A
#: parcel under this cannot host the product under any encoding, so excluding it
#: cannot hide an opportunity.
ABSOLUTE_MIN_LOT_SQFT = 800.0

#: Genuine lots top out near 1.28 (99th percentile). Above this the building
#: cannot rest on this parcel alone.
SUSPECT_BUILDING_RATIO = 1.5

#: Ratio rule only applies below this size; a large lot with a big building is
#: an ordinary dense development, not an air parcel.
SUSPECT_MAX_LOT_SQFT = 2000.0


class CondoVerdict(str, enum.Enum):
    """Outcome of the check. Only ``excluded`` removes a row."""

    land = "land"
    #: Unambiguously not land. Dropped, counted, and given a reason code.
    excluded = "excluded"
    #: Probably not land, but not certain. Kept and routed to REVIEW.
    suspect = "suspect"


@dataclass(frozen=True, slots=True)
class CondoCheck:
    verdict: CondoVerdict
    #: Reason code, empty when the parcel is ordinary land.
    reason: str = ""
    detail: str = ""

    @property
    def is_land(self) -> bool:
        return self.verdict is not CondoVerdict.excluded


def _num(row: Mapping[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN


def check_condo(row: Mapping[str, Any]) -> CondoCheck:
    """Classify one taxlot row.

    Expects the RLIS-derived columns ``area_sqft``, ``BLDGSQFT``, ``PROP_CODE``
    and ``COUNTY``. Missing columns degrade the check rather than crashing it —
    a row we cannot assess is land, because the recall bias says so.
    """
    area = _num(row, "area_sqft")
    bldg = _num(row, "BLDGSQFT")
    county = str(row.get("COUNTY") or "").strip().upper()
    prop_code = str(row.get("PROP_CODE") or "").strip()

    if prop_code and prop_code in CONDO_PROP_CODES.get(county, frozenset()):
        # A condominium code covers two very different things: the tiny air
        # parcels a unit owner holds, and the common-element parcel that is the
        # development's actual land — which can be large. Excluding the second
        # on code alone would silently delete real sites (the R5 corpus holds
        # condo-coded parcels up to 329,000 sqft). Size decides which we have.
        if area is None:
            return CondoCheck(
                CondoVerdict.suspect,
                "SUSPECT_CONDO_UNKNOWN_AREA",
                f"property code {prop_code} is a condominium interest but the parcel "
                f"has no area to judge it by",
            )
        if area >= SUSPECT_MAX_LOT_SQFT:
            return CondoCheck(
                CondoVerdict.suspect,
                "SUSPECT_CONDO_COMMON_AREA",
                f"property code {prop_code} on a {area:.0f} sqft parcel — likely the "
                f"condominium's common-element land, which is encumbered but real",
            )
        return CondoCheck(
            CondoVerdict.excluded,
            "CONDO_AIR_PARCEL",
            f"county {county} property code {prop_code} on {area:.0f} sqft — "
            f"a condominium interest, not land",
        )

    if area is not None and area < ABSOLUTE_MIN_LOT_SQFT:
        return CondoCheck(
            CondoVerdict.excluded,
            "LOT_BELOW_PHYSICAL_MINIMUM",
            f"{area:.0f} sqft is below the {ABSOLUTE_MIN_LOT_SQFT:.0f} sqft floor "
            f"any fourplex needs under any encoding",
        )

    if (
        area is not None
        and bldg is not None
        and area > 0
        and bldg > 0
        and area < SUSPECT_MAX_LOT_SQFT
        and bldg / area > SUSPECT_BUILDING_RATIO
    ):
        return CondoCheck(
            CondoVerdict.suspect,
            "SUSPECT_STACKED_UNIT",
            f"building {bldg:.0f} sqft on a {area:.0f} sqft parcel "
            f"(ratio {bldg / area:.1f}× — genuine lots peak near 1.3×)",
        )

    return CondoCheck(CondoVerdict.land)


def classify_frame(df: Any) -> Any:
    """Add ``condo_verdict`` / ``condo_reason`` columns to a pandas DataFrame.

    Row-wise on purpose: the check is cheap, and keeping one implementation
    means the ledger, the pipeline, and the tests cannot disagree.
    """
    checks = [check_condo(r) for r in df.to_dict("records")]
    out = df.copy()
    out["condo_verdict"] = [c.verdict.value for c in checks]
    out["condo_reason"] = [c.reason for c in checks]
    return out
