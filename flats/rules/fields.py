"""Field registry — the single place FLATS names a zoning standard.

Every encodable standard is declared here once, with its value kind, its
National Zoning Atlas checklist counterpart (gap-finding), and a slot for its
OZFS name once that spec publishes. Renaming a field for OZFS alignment is an
edit to this module plus ``ozfs_map.yaml`` — never a refactor of the rule files.

Kinds drive validation and slack arithmetic:

``bool``        allowed / prohibited
``length_ft``   setbacks, heights, widths — slack in feet
``area_sqft``   minimum lot area — slack in square feet
``ratio``       FAR, stalls per unit — slack as a ratio
``percent``     coverage, open space — slack in percentage points
``count``       max units
``curve``       lot-size-tiered table (Portland building coverage, Table 110-5)
``enum``        constrained vocabulary (orientation policy)

A field with ``higher_is_slack=True`` passes when the observed value is at or
below the encoded standard (a maximum). ``False`` means the standard is a floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["bool", "length_ft", "area_sqft", "ratio", "percent", "count", "curve", "enum"]


@dataclass(frozen=True, slots=True)
class FieldDef:
    name: str
    kind: Kind
    describe: str
    #: True when the encoded number is a ceiling the lot must stay under
    #: (coverage, height, FAR). False when it is a floor the lot must meet
    #: (minimum lot area, minimum frontage). None for non-numeric fields.
    is_maximum: bool | None = None
    #: National Zoning Atlas field this corresponds to, for the gap audit.
    nza: str | None = None
    #: OZFS field name. Populated once the spec publishes; see ozfs_map.yaml.
    ozfs: str | None = None
    #: Permitted values for ``enum`` fields.
    choices: tuple[str, ...] = ()


_F: tuple[FieldDef, ...] = (
    # --- use permission -------------------------------------------------
    FieldDef(
        "quadplex_allowed",
        "bool",
        "Fourplex permitted by right in this zone.",
        nza="4_family_treatment",
    ),
    # --- setbacks -------------------------------------------------------
    FieldDef("setback_front_ft", "length_ft", "Minimum front setback.", False, "front_setback"),
    FieldDef("setback_side_ft", "length_ft", "Minimum interior side setback.", False, "side_setback"),
    FieldDef("setback_rear_ft", "length_ft", "Minimum rear setback.", False, "rear_setback"),
    FieldDef(
        "setback_street_side_ft",
        "length_ft",
        "Minimum street-side setback on a corner lot.",
        False,
        "corner_side_setback",
    ),
    FieldDef(
        "setback_front_max_ft",
        "length_ft",
        "MAXIMUM front setback — forces the building toward the street. "
        "Gresham DRL and Fairview base zones impose these.",
        True,
        "max_front_setback",
    ),
    FieldDef(
        "setback_garage_entrance_ft",
        "length_ft",
        "Minimum setback to a garage entrance / vehicle door.",
        False,
    ),
    # --- lot dimensions -------------------------------------------------
    FieldDef("min_lot_sqft", "area_sqft", "Minimum lot area for a fourplex.", False, "min_lot_size"),
    FieldDef("min_lot_width_ft", "length_ft", "Minimum lot width.", False, "min_lot_width"),
    FieldDef("min_frontage_ft", "length_ft", "Minimum street frontage.", False, "min_frontage"),
    FieldDef(
        "land_division_parent_standards",
        "bool",
        "True where splitting the building onto one lot per unit is judged "
        "against the standards for the ORIGINAL lot, not against a fresh set "
        "for each resulting lot. Oregon states this for every middle housing "
        "land division (ORS 92.031(2)(b)), which is why the split-plat path "
        "does not multiply a zone's minimum lot area by four.",
    ),
    # --- bulk -----------------------------------------------------------
    FieldDef("max_height_ft", "length_ft", "Maximum building height.", True, "max_height"),
    FieldDef("max_far", "ratio", "Maximum floor area ratio.", True, "max_far"),
    FieldDef("max_coverage_pct", "percent", "Maximum building coverage, flat percentage.", True, "max_lot_coverage"),
    FieldDef(
        "coverage_curve",
        "curve",
        "Lot-size-tiered coverage table: [[lot_sqft_floor, base_sqft, pct_over_floor], ...]. "
        "Portland Table 110-5 is tiered, not flat — encode the tiers.",
        True,
        "max_lot_coverage",
    ),
    FieldDef("max_units", "count", "Maximum dwelling units.", True, "max_units"),
    # --- density --------------------------------------------------------
    FieldDef(
        "min_density_trigger_lot_sqft",
        "area_sqft",
        "Lot area at or above which a MINIMUM density applies.",
        False,
        "min_density",
    ),
    FieldDef("min_units_at_trigger", "count", "Units required once the density trigger is met.", False),
    # --- parking and open space ----------------------------------------
    FieldDef("parking_min_per_unit", "ratio", "Required off-street stalls per unit.", False, "parking_min"),
    FieldDef("open_space_min_pct", "percent", "Minimum private open space as a share of lot area.", False),
    # --- orientation ----------------------------------------------------
    FieldDef(
        "orientation_constraint",
        "enum",
        "How the code constrains building orientation. `entrance_only` binds the main entrance without fixing the long axis; `axis_required` forces the building to face the street, which halves the orientations the fit stage may try.",
        None,
        "building_orientation",
        choices=("none", "entrance_only", "axis_required"),
    ),
)

FIELDS: dict[str, FieldDef] = {f.name: f for f in _F}

#: Fields whose absence should not by itself block a zone from `verified`.
#: Everything else, if the code speaks to it, must be encoded or explicitly
#: recorded as not-applicable via the clause ledger.
OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {
        "setback_street_side_ft",
        "setback_front_max_ft",
        "setback_garage_entrance_ft",
        "min_lot_width_ft",
        "min_frontage_ft",
        "land_division_parent_standards",
        "max_far",
        "max_coverage_pct",
        "coverage_curve",
        "max_units",
        "min_density_trigger_lot_sqft",
        "min_units_at_trigger",
        "open_space_min_pct",
        "orientation_constraint",
    }
)

#: Required before a zone can reach `verified`.
REQUIRED_FIELDS: frozenset[str] = frozenset(FIELDS) - OPTIONAL_FIELDS


def field(name: str) -> FieldDef:
    """Look up a field definition, failing loudly on an unknown name.

    Explicit failure over silent default: an unrecognised key in a rule file is
    a typo or an un-registered standard, and either way must not be ignored.
    """
    try:
        return FIELDS[name]
    except KeyError:
        raise KeyError(
            f"unknown rule field {name!r} — register it in flats/rules/fields.py "
            f"before using it in a jurisdiction file"
        ) from None
