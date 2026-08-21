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
    FieldDef(
        "setback_side_total_ft",
        "length_ft",
        "Minimum COMBINED side setback, where the code regulates the pair "
        "rather than either yard: Lake Oswego's R-7.5 cell reads \"Total 15, "
        "5 min.\" Held apart from setback_side_ft because halving it invents "
        "a number the document does not print, and because the pair and the "
        "per-side floor bind differently -- the pair takes width off the lot, "
        "the floor says where the building may sit on what is left.",
        False,
        "side_setback",
    ),
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
    FieldDef(
        "min_building_separation_ft",
        "length_ft",
        "Minimum distance between two primary buildings on the SAME lot -- "
        "Fairview 19.30 calls it a special yard and asks ten feet. It is not a "
        "setback: no lot line is involved, and it binds only where the pod is "
        "going onto a lot that already holds a house, or where a site plan "
        "puts two pods on one parcel. Both are ordinary, and neither is "
        "visible to any of the lot-line fields.",
        False,
    ),
    # --- lot dimensions -------------------------------------------------
    FieldDef("min_lot_sqft", "area_sqft", "Minimum lot area for a fourplex.", False, "min_lot_size"),
    FieldDef("min_lot_width_ft", "length_ft", "Minimum lot width.", False, "min_lot_width"),
    FieldDef("min_frontage_ft", "length_ft", "Minimum street frontage.", False, "min_frontage"),
    FieldDef(
        "min_lot_depth_ft",
        "length_ft",
        "Minimum lot depth, front line to rear line. Distinct from lot area: a "
        "lot can hold the required square footage and still be too shallow to "
        "fit the pod between its front and rear setbacks, which is the exact "
        "shape a townhome on a wide-shallow lot fails in.",
        False,
    ),
    FieldDef(
        "max_lot_depth_ratio",
        "ratio",
        "Maximum lot depth as a multiple of lot width — Fairview 19.30 caps it "
        "at three. A ceiling on depth rather than a floor, and it is written "
        "against the width rather than in feet, so it cannot be folded into "
        "`min_lot_depth_ft` without losing what it says.",
        True,
    ),
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
    FieldDef(
        "max_height_stories",
        "count",
        "MAXIMUM building height where the code counts storeys instead of "
        "feet. Gresham's SC and SC-RJ read \"10 stories\" in Table 4.0430 and "
        "the chapter prints no figure in feet for them anywhere; GDC 3.0100 "
        "defines a story by which floor surfaces bound it and never says how "
        "tall one is, so every conversion to feet is an invention. Held as "
        "its own field rather than converted because a storey count is a "
        "different measurement, not a different spelling: a pod with one tall "
        "ground floor can clear the count and fail the feet, and the two are "
        "checked against different things about the design. A zone that "
        "states this has answered the height question, so it stands in for "
        "`max_height_ft` in the required-field check rather than beside it.",
        True,
        "max_height",
    ),
    FieldDef(
        "max_building_width_ft",
        "length_ft",
        "MAXIMUM width of the building itself, measured across it rather than "
        "from any lot line. West Linn CDC 25.070(C)(8) is the one instance in "
        "this corpus -- \"No building shall exceed 35 feet in overall width\" "
        "in the Willamette Historic District -- and it is the only standard "
        "read so far that the catalog pod fails on its own dimensions rather "
        "than on how it sits: 56 ft by 36 ft is over the cap whichever way it "
        "is turned. Not a setback, and not foldable into one: a setback says "
        "where a building may stand and this says how big it may be, so a lot "
        "with room to spare on every yard still fails it.",
        True,
    ),
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
    FieldDef(
        "min_density_du_per_acre",
        "ratio",
        "MINIMUM dwelling units per acre. The shape most Oregon codes state a "
        "density floor in, and one the trigger/units pair cannot hold: it is "
        "continuous, so what it requires depends on how big the lot is. "
        "Fairview asks 3.5 units per acre in R-10, which a four-unit pod meets "
        "on a 10,000 sq ft lot and fails on two acres -- where the code wants "
        "seven. Unencoded, that lot screens GREEN on every other standard, "
        "which is the false GREEN this field exists to close.",
        False,
        "min_density",
    ),
    FieldDef(
        "max_density_du_per_acre",
        "ratio",
        "MAXIMUM dwelling units per acre. A ceiling on units is a floor under "
        "lot area said in other units -- Milwaukie caps R-MD at 6.2 du/acre on "
        "a large lot, which asks 28,000 sq ft for four units where the lot "
        "size row asks 7,000. Held apart from min_lot_sqft because a code can "
        "state either without the other, and because the two disagree often "
        "enough that folding one into the other would lose which one bound.",
        True,
        "max_density",
    ),
    # --- parking and open space ----------------------------------------
    FieldDef("parking_min_per_unit", "ratio", "Required off-street stalls per unit.", False, "parking_min"),
    FieldDef("open_space_min_pct", "percent", "Minimum private open space as a share of lot area.", False),
    FieldDef(
        "min_landscaped_pct",
        "percent",
        "Minimum share of the site kept in landscaping. Distinct from private "
        "open space: nobody has to be able to sit in it, and it is written "
        "against the whole site rather than per unit. Portland Table 120-4 "
        "asks 30 percent in RM1 and 15 in RM4, and it binds the same way a "
        "coverage cap does -- it is lot area the pod and its parking may not "
        "have.",
        False,
    ),
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

#: How many dwellings the standards in this registry are read for.
#:
#: Not a design parameter -- the design catalog carries its own unit count.
#: This is a property of the FIELD: `min_lot_sqft` is defined as the minimum
#: lot area *for a fourplex*, so a code that states its lot area per dwelling
#: unit has stated this field four times over. Written down because the
#: multiplication has to happen somewhere, and the two honest places are here
#: or nowhere -- a rule file that typed the product would be citing a sentence
#: for a number the sentence does not print.
DWELLINGS = 4

#: Fields a rule file may state as an area per dwelling unit rather than as a
#: density. Portland prints its multi-dwelling floor as "1 unit per 2,500 sq.
#: ft. of site area" and prints 17.424 units per acre nowhere; the two are the
#: same standard, and only one of them is in the document. The conversion runs
#: through :data:`SQFT_PER_ACRE`, and what a citation is checked against is the
#: figure the table prints.
PER_UNIT_AREA_FIELDS: frozenset[str] = frozenset(
    {"min_density_du_per_acre", "max_density_du_per_acre"}
)

#: Square feet in an acre. The one conversion this registry performs, and it
#: is here rather than in a rule file because a file that typed the quotient
#: would be citing a sentence for a number the sentence does not contain.
SQFT_PER_ACRE = 43_560

#: Fields whose number is a rate, so the quantity underneath it decides what
#: the number means. Portland's multi-dwelling floor is stated per square foot
#: of *site area*, which is the lot; nearly every other Oregon city states its
#: density per *net acre*, which is the lot less rights-of-way, floodplain,
#: steep slopes, wetlands and Goal 5 resources. Those are different
#: denominators and they are not close: Tualatin's own code offers 15 to 20
#: percent as the deduction to assume when nobody has surveyed it.
#:
#: A screen holding only the parcel's square footage can run the first
#: outright. For the second the lot's own area is still a bound -- net is
#: never more than gross -- which settles a floor that clears and a ceiling
#: that is exceeded, and leaves the other outcome to a survey nobody ran.
#: `measured_on` is how a rule file says which one it is.
#:
#: A floor area ratio is the same shape of number and takes the same
#: subtraction. West Linn prints one sentence in all nine zone chapters —
#: "Type I and II lands shall not be counted toward lot area when determining
#: allowable floor area ratio" — so the ratio that governs there is the
#: building's floor area over something smaller than the lot, and the bound
#: argument above carries over unchanged: a FAR already over the ceiling on
#: the whole lot is over it on any part of the lot.
MEASURED_ON_FIELDS: frozenset[str] = frozenset(
    {"min_density_du_per_acre", "max_density_du_per_acre", "max_far"}
)

#: Fields a rule file may state per dwelling unit rather than outright.
#: An area scales with the number of dwellings; a width, a depth or a setback
#: does not. MCC 39.4862(C) asks "5,000 square feet for each dwelling unit"
#: and a fourplex needs four of them; four times a minimum lot WIDTH would be
#: a requirement no code anywhere states.
PER_DWELLING_FIELDS: frozenset[str] = frozenset({"min_lot_sqft"})

#: Fields a rule file may state in ACRES rather than in square feet. Rural
#: Oregon is written this way and only this way -- MCC 39.4245(A) asks 80 acres
#: of a new EFU parcel, 39.4325 asks 20 of MUA-20, 39.4705(E) asks 38 of a
#: dwelling in MUF -- and none of those articles prints a square footage
#: anywhere. Typing the product into the file would cite a sentence for a
#: number the sentence does not contain, which is the failure this registry
#: exists to make impossible; the multiplication runs through
#: :data:`SQFT_PER_ACRE` at load and the citation is checked against the
#: acreage a reader will actually find.
#:
#: Restricted to areas for the same reason as `per_dwelling`: an acre is a
#: unit of area, and a lot WIDTH stated in acres is not a rule any code
#: writes.
ACRE_STATED_FIELDS: frozenset[str] = frozenset({"min_lot_sqft"})

#: Fields a rule file may state as ACRES PER DWELLING UNIT -- the two
#: conversions above, composed, and the composition is the whole reason it
#: exists. Multnomah County's Planned Development overlay is the case: MCC
#: 39.5340(A) sets the number of dwellings a PD may hold by "dividing the total
#: site area by the minimum lot area per dwelling unit required by the
#: underlying district", and the underlying districts state that minimum in
#: acres -- one acre in the Orient Rural Center Residential zone, five in Rural
#: Residential. So a four-unit PD needs four acres in the first and twenty in
#: the second, and neither article prints either figure.
#:
#: Written as its own form rather than by letting a value carry `acres` and
#: `per_dwelling` together, because the citation check has to know which single
#: figure a reader will find in the text. Here that figure is the acreage, and
#: the file states the acreage.
ACRE_PER_DWELLING_FIELDS: frozenset[str] = frozenset({"min_lot_sqft"})

#: The height, in feet, of the building this screen answers for. A design
#: constant in the rules registry for the same reason :data:`DWELLINGS` is one:
#: some codes state a standard as a function of the building rather than of the
#: lot, and the multiplication has to happen somewhere. The two honest places
#: are here or nowhere, and nowhere means a rule file typing a product that
#: appears in no ordinance.
#:
#: Portland's Table 150-2 is the case that forced it. The IR column of all
#: three minimum-setback rows is one merged cell: "1 ft. for every 2 ft. of
#: building height but not less than 10 ft." For a 26 ft pod that is 13 ft, and
#: 13 is printed nowhere.
#:
#: It is the TALLEST design in the catalog, not an average, because a taller
#: building owes a larger setback and the conservative answer is the strict
#: one. `flats/tests/test_height_ratio.py` fails the moment a catalog entry
#: exceeds it, which is the revisit this constant is owed rather than a number
#: that silently goes stale.
DESIGN_HEIGHT_FT = 26

#: Fields a rule file may state as a ratio of building height. Restricted to
#: the yards and the separation between buildings, because those are the
#: standards codes actually write this way -- a step-back against a smaller
#: neighbour, a light-and-air rule, a fire-separation rule. A minimum lot AREA
#: stated per foot of height is not a rule any code writes, and a maximum
#: height stated as a fraction of itself is not one either.
HEIGHT_RATIO_FIELDS: frozenset[str] = frozenset(
    {
        "setback_front_ft",
        "setback_side_ft",
        "setback_street_side_ft",
        "setback_rear_ft",
        "min_building_separation_ft",
    }
)

#: Fields a rule file may state with a STEP-BACK behind them -- a second rule,
#: usually in a different chapter, that limits how tall a building may be near
#: the line and so decides how far back a building of a given height has to
#: stand. Gresham 7.0420(G)(1) is the case: in six of its residential districts
#: "the maximum roof height at the rear setback line is 21 feet and increases
#: at a rate of one foot in height for every one foot of distance further from
#: the rear property line", which for a 26 ft box is five feet further back
#: than the district table prints.
#:
#: Restricted to the yards, because a step-back is a rule about a lot line. It
#: is the second form here that reads :data:`DESIGN_HEIGHT_FT`, and unlike
#: `per_height_ft` it does not replace the district's own number -- it adds to
#: it, which is why a value carrying one states both figures and cites both
#: sentences.
STEP_BACK_FIELDS: frozenset[str] = frozenset(
    {
        "setback_front_ft",
        "setback_side_ft",
        "setback_street_side_ft",
        "setback_rear_ft",
    }
)

#: Fields whose absence should not by itself block a zone from `verified`.
#: Everything else, if the code speaks to it, must be encoded or explicitly
#: recorded as not-applicable via the clause ledger.
OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {
        # Answers the height question in the other unit. Required-ness is
        # handled by ALTERNATIVES in the resolver, which reads one as
        # standing in for the other; listed as required here it would be
        # demanded of every zone whose code states feet.
        "max_height_stories",
        "setback_street_side_ft",
        # Only a handful of codes regulate the pair rather than either yard,
        # and a zone that states one side yard is not an incomplete zone.
        "setback_side_total_ft",
        "setback_front_max_ft",
        "setback_garage_entrance_ft",
        "min_building_separation_ft",
        "min_lot_width_ft",
        "min_frontage_ft",
        # Most Oregon codes state neither, and a zone that is silent about depth
        # is not an incomplete zone. Where one does state it, the gap ledger
        # still surfaces the omission through the clause ledger.
        "min_lot_depth_ft",
        "max_lot_depth_ratio",
        # One jurisdiction in the corpus caps building width, and only inside
        # a historic district. A zone that is silent about it is not an
        # incomplete zone.
        "max_building_width_ft",
        "land_division_parent_standards",
        "max_far",
        "max_coverage_pct",
        "coverage_curve",
        "max_units",
        "min_density_trigger_lot_sqft",
        "min_units_at_trigger",
        "min_density_du_per_acre",
        # Most Oregon codes cap density in the multi-family zones only, and a
        # zone that states no ceiling is not an incomplete zone.
        "max_density_du_per_acre",
        "open_space_min_pct",
        "min_landscaped_pct",
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
