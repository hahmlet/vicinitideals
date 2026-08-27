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
    #: What to call this standard in front of a person. Field names are built
    #: for sorting and for the loader -- ``setback_front_ft`` puts the noun
    #: first so every setback files together -- and a reviewer reading a queue
    #: should not have to translate. Left blank where the derived form is
    #: already right.
    label: str = ""

    @property
    def shown(self) -> str:
        """The label, or a readable form derived from the name."""
        if self.label:
            return self.label
        if self.name in _LABELS:
            return _LABELS[self.name]
        words = self.name.split("_")
        words = [w for w in words if w not in _UNITS]
        if words and words[0] == "setback" and len(words) > 1:
            words = words[1:] + ["setback"]
        return " ".join(words).replace("min ", "min. ").replace("max ", "max. ")

    @property
    def has_slack(self) -> bool:
        """Whether being wrong about this can change whether a building fits.

        A boolean is settled or it is not: reading a chapter cannot make a
        prohibited use slightly more prohibited. Every other kind carries a
        distance between the standard and the building, and that distance is
        what a missed cross-reference eats into.
        """
        return self.kind not in ("bool", "enum")


#: Unit suffixes carried by field names for the loader's benefit, not a
#: reader's. ``du`` and ``per`` go too: "max density du per acre" reads worse
#: than "max. density".
_UNITS = frozenset({"ft", "sqft", "pct", "du", "per", "acre"})

#: Where the derived form is wrong rather than merely plain. Everything a
#: reviewer sees comes through here, so the unit belongs in the label when the
#: number is meaningless without it -- "min. lot 5,000" is a different claim
#: from "min. lot area 5,000 sq ft".
_LABELS: dict[str, str] = {
    "coverage_curve": "building coverage (by lot size)",
    "driveway_approach_max_width_ft": "max. driveway approach width",
    "driveway_approach_min_width_ft": "min. driveway approach width",
    "driveway_min_width_one_way_ft": "min. driveway width (one-way)",
    "driveway_min_width_two_way_ft": "min. driveway width (two-way)",
    "land_division_parent_standards": "parent-lot standards apply",
    "max_building_width_ft": "max. building width",
    "max_coverage_pct": "max. lot coverage %",
    "max_density_du_per_acre": "max. density (units/acre)",
    "max_far": "max. floor area ratio",
    "max_height_ft": "max. height",
    "max_height_stories": "max. height (storeys)",
    "max_lot_depth_ratio": "max. lot depth ratio",
    "max_units": "max. units",
    "min_building_separation_ft": "min. building separation",
    "min_density_du_per_acre": "min. density (units/acre)",
    "min_density_trigger_lot_sqft": "lot size that triggers min. density",
    "min_frontage_ft": "min. frontage",
    "min_landscaped_pct": "min. landscaping %",
    "min_lot_depth_ft": "min. lot depth",
    "min_lot_sqft": "min. lot area",
    "min_lot_width_ft": "min. lot width",
    "min_units_at_trigger": "min. units once triggered",
    "open_space_min_pct": "min. open space %",
    "open_space_min_sqft": "min. open space area",
    "orientation_constraint": "building orientation rule",
    "parking_area_max_frontage_pct": "max. parking share of frontage",
    "parking_area_max_width_ft": "max. parking area width",
    "parking_building_buffer_ft": "min. parking-to-building buffer",
    "parking_front_prohibited": "parking banned in front of building",
    "parking_front_yard_max_pct": "max. vehicle share of front yard",
    "parking_maneuvering_max_width_ft": "max. maneuvering-area width",
    "parking_max_per_unit": "max. parking per unit",
    "parking_min_per_unit": "min. parking per unit",
    "parking_street_setback_ft": "min. parking setback from street",
    "quadplex_allowed": "fourplex allowed",
    "setback_front_ft": "front setback",
    "setback_front_max_ft": "max. front setback",
    "setback_garage_entrance_ft": "garage entrance setback",
    "setback_rear_ft": "rear setback",
    "setback_side_ft": "side setback",
    "setback_side_total_ft": "combined side setbacks",
    "setback_street_side_ft": "street-side setback",
}


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
    FieldDef(
        "parking_max_per_unit",
        "ratio",
        "MAXIMUM off-street stalls per unit the code permits. A ceiling on "
        "parking, which reads like the opposite of a constraint and is not: "
        "the design catalog carries a stalls-per-unit target, and a site plan "
        "that seats more stalls than the zone allows is not a legal placement "
        "however well it fits. Portland caps a fourplex at 1.35 per unit in "
        "its multi-dwelling and commercial zones and at one per two units in "
        "EX, against a catalog target of 1.5 -- so the pod as specified is "
        "over the cap in thirteen of Portland's twenty-eight zones. Held "
        "apart from `parking_min_per_unit` because the two bind opposite "
        "ways and a city can state either without the other: Portland states "
        "no minimum anywhere and a maximum in half its zones. No National "
        "Zoning Atlas counterpart -- the checklist records what a code "
        "requires, not what it forbids.",
        True,
    ),
    # --- how big a stall is, which decides how many fit ------------------
    #
    # A stall count is a rule about arithmetic; these are rules about a
    # rectangle. The site plan has to seat real stalls on a real lot, and it
    # was doing that against one jurisdiction's numbers typed into a constant:
    # Gresham's 8.5 x 18 applied everywhere, and a one-way aisle of 20 feet
    # that is not Gresham's parking aisle at all -- Table 9.0825A asks 23 at
    # 90 degrees, and the 20 is note 1's emergency-vehicle access figure. A
    # narrow aisle and a narrow stall both err the same way: they seat stalls
    # a court could not really hold, which is a GREEN nobody can build.
    FieldDef(
        "parking_stall_width_ft",
        "length_ft",
        "Minimum width of one off-street parking stall. Cities differ by half "
        "a foot and half a foot per stall is a stall every eighteen: Gresham "
        "asks 8.5 for townhouses (7.0431(B)(5)(b)), Portland 9 for anything "
        "up to a fourplex (33.266.120.D.1). Read off the standard that governs "
        "THIS product -- Portland's 33.266.130 prints an 8 ft 6 in stall in "
        "Table 266-4 and hands residential vehicle areas straight back to "
        ".120, so reading .130 is how the half-foot error gets made.",
        False,
    ),
    FieldDef(
        "parking_stall_depth_ft",
        "length_ft",
        "Minimum depth of one off-street parking stall, measured from the "
        "aisle. Held apart from the width because a code can state either "
        "without the other and because a bumper overhang is subtracted from "
        "the depth alone -- Gresham's Table 9.0825A allows 3 feet of it at 90 "
        "degrees, which is only available where an extruded curb is built. "
        "Encode the figure with no overhang; the allowance is a design choice "
        "the screen has no way to know was taken.",
        False,
    ),
    FieldDef(
        "parking_aisle_one_way_ft",
        "length_ft",
        "Minimum drive-aisle width where traffic runs one way, at 90 degrees "
        "to the stalls. The aisle is usually the largest single piece of a "
        "rear court after the stalls themselves, so three feet of it is most "
        "of a stall. Beware the emergency-access figure printed beside it: "
        "Gresham's Table 9.0825A note 1 gives 20 feet for one-way emergency "
        "vehicle access, which is a different standard from the 23 the table "
        "itself asks, and the smaller number is the one that reads like the "
        "answer.",
        False,
    ),
    FieldDef(
        "parking_aisle_two_way_ft",
        "length_ft",
        "Minimum drive-aisle width where traffic runs both ways, at 90 "
        "degrees to the stalls. Stated separately because a court reached by "
        "a single side driveway may be laid out either way, and the two "
        "figures are far enough apart to decide whether a row of stalls fits.",
        False,
    ),
    # --- how the car gets in, and where it may sit once it is in --------
    #
    # Six jurisdictions were transcribed rather than encoded against this gap
    # -- Fairview, Wilsonville, Milwaukie, Oregon City, Happy Valley and
    # unincorporated Clackamas all print the state middle-housing model code
    # in local words, and none of it had anywhere to go. What they regulate is
    # not the stall, which the fields above hold; it is the curb cut, the
    # travel lane behind it, and the ground between the building and the
    # street. A site plan that seats four stalls in a rear court and then
    # crosses the front yard to reach them is answering all three, and until
    # now it answered them with Gresham's numbers everywhere.
    #
    # These are city-wide sentences out of a parking or access chapter, not
    # rows of a zone table, so they are optional: a layer that states none of
    # them is not thereby incomplete.
    FieldDef(
        "driveway_approach_min_width_ft",
        "length_ft",
        "Narrowest driveway approach -- the curb cut at the property line -- "
        "the code will accept. Held apart from the driveway itself because "
        "the approach is a public-works dimension and the driveway is a "
        "private one, and a city can state either without the other: Oregon "
        "City's Table 16.12.035.D asks 10 feet of approach and lets the drive "
        "widen behind the property line, which is the shape most of them "
        "take.",
        False,
    ),
    FieldDef(
        "driveway_approach_max_width_ft",
        "length_ft",
        "Widest driveway approach the code allows, counting every approach on "
        "one frontage together where the code counts them together. This is "
        "the field that decides whether a rear court is reachable at all: "
        "Gresham allows a fourplex with no garage 10 feet of it "
        "(7.0420(B)(2)(b)(ii)) and a townhouse project 18 (7.0431(B)(2)(b)), "
        "Oregon City allows a quadplex 36 and a townhouse 24, and the same "
        "building gets a different number depending on how the land is "
        "divided.",
        True,
    ),
    FieldDef(
        "driveway_min_width_one_way_ft",
        "length_ft",
        "Narrowest one-way driveway on private property. Stated separately "
        "from the two-way figure because the gap between them is most of a "
        "stall and decides the layout: Happy Valley asks 12 one-way and 20 "
        "two-way in the same sentence (16.41.030.B.1), and a court reached by "
        "a single drive is two-way unless a loop is drawn.",
        False,
    ),
    FieldDef(
        "driveway_min_width_two_way_ft",
        "length_ft",
        "Narrowest two-way driveway on private property -- the figure that "
        "binds a rear court served by one entrance. Portland states one "
        "number for both directions (33.266.120.D.2, 9 feet); Happy Valley "
        "states 20, which is wider than the pod's whole side yard on a narrow "
        "lot and is the difference between a plan and no plan.",
        False,
    ),
    FieldDef(
        "parking_maneuvering_max_width_ft",
        "length_ft",
        "Widest strip of outdoor parking and maneuvering area the code allows "
        "on a lot, where the code caps the strip rather than its share of the "
        "frontage. This is the state model code's townhouse branch and it is "
        "brutal: Gresham, Fairview, Wilsonville and Oregon City all say 12 "
        "feet and Milwaukie says 10, which is a driveway and not a court. It "
        "is normally reached only on unit lots -- the same rule usually "
        "states a 50-percent-of-frontage allowance for the one-lot case.",
        True,
    ),
    FieldDef(
        "parking_area_max_frontage_pct",
        "percent",
        "Most of the street frontage that garages, parking and maneuvering "
        "area together may occupy. Fifty percent is the model-code figure and "
        "four cities in this corpus print it. Distinct from "
        "`parking_front_yard_max_pct`: this is measured along the lot line, "
        "that one across the ground behind it, and a plan can pass either "
        "while failing the other.",
        True,
    ),
    FieldDef(
        "parking_area_max_width_ft",
        "length_ft",
        "A flat ceiling in feet on the width of outdoor parking and "
        "maneuvering area, stated alongside a share-of-frontage cap and "
        "binding whichever is less. Oregon City is the only city here that "
        "states one (17.16.060.D.1, forty feet), and on a wide lot it is the "
        "limb that binds.",
        True,
    ),
    FieldDef(
        "parking_front_yard_max_pct",
        "percent",
        "Most of the ground between the front lot line and the front building "
        "line that may be paved or used as vehicle area. Portland asks 40 "
        "percent (33.266.120.C.1.b) and Milwaukie 50 of the front yard area "
        "(19.607.1.D). An area share, not a frontage share -- a 12-foot drive "
        "down one side of a deep front yard passes this and can still fail "
        "`parking_area_max_frontage_pct` on a narrow lot.",
        True,
    ),
    FieldDef(
        "parking_front_prohibited",
        "bool",
        "True where the code bans PARKING between the primary building and "
        "the street outright rather than capping it. Portland "
        "(33.266.120.C.1.a) and Milwaukie (19.505.3.D.4.a) both do. Read the "
        "applicability first: unincorporated Clackamas states the same ban "
        "in ZDO 845.04 and it is a COTTAGE CLUSTER rule -- what 845.02 "
        "gives a quadplex is the 50-percent cap instead. Both carve the "
        "driveway out -- Portland in the same sentence, allowing drives to "
        "parking behind the building line -- so this bans a front-yard "
        "court and not the drive that reaches a rear one. A ban and a "
        "50-percent cap are not the same rule and cannot share a field: "
        "one of them a front-yard court can satisfy.",
        None,
    ),
    FieldDef(
        "parking_street_setback_ft",
        "length_ft",
        "How far a parking area must sit back from a street lot line. "
        "Portland keeps stalls out of the first ten feet and prints the ten "
        "(33.266.120.C.2.a). Happy Valley prints a ten too and does not mean "
        "it: 16.43.030.E.4 sets the standard to \"the same distance as the "
        "required building setbacks\" and floors it at ten, which comes to "
        "twenty-two feet in six of its districts and removes front-yard "
        "parking rather than trimming it. That is the field carried with "
        "`same_as` rather than a typed number -- see Value.same_as. The "
        "driveway reaching a rear court is not a parking area and is not "
        "caught by this.",
        False,
    ),
    FieldDef(
        "parking_building_buffer_ft",
        "length_ft",
        "Width of the pathway, plaza or landscape strip a code requires "
        "between a parking or maneuvering area and the wall of the building "
        "it serves. Fairview asks four feet and makes it a landscape buffer "
        "where the wall is ground-floor living space (19.163.030(E)(3)(b)). "
        "Real ground, subtracted from the court before any stall is seated.",
        False,
    ),
    FieldDef("open_space_min_pct", "percent", "Minimum private open space as a share of lot area.", False),
    FieldDef(
        "open_space_min_sqft",
        "area_sqft",
        "Minimum private open space stated as an area rather than a share. "
        "Held apart from `open_space_min_pct` because the two behave "
        "differently as the lot grows: Portland's Table 110-4 asks 250 square "
        "feet whatever the lot is, Milwaukie 96 per ground-floor dwelling "
        "(Table 19.505.3.D.1), and Gresham 15 percent -- which on a big lot "
        "is an order of magnitude more. A city that states both means both. "
        "The minimum DIMENSION some of them state alongside it (Portland's 12 "
        "by 12) is a shape test no field here holds.",
        False,
    ),
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
PER_DWELLING_FIELDS: frozenset[str] = frozenset(
    {"min_lot_sqft", "open_space_min_sqft"}
)

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

#: Fields a rule file may state as a count of spaces FOR THE WHOLE BUILDING
#: rather than as a rate per unit. Oregon's middle-housing rule is written this
#: way and the cities that adopted its model code copied the wording: OAR
#: 660-046-0220(2)(e)(B) caps what a large city may require of a quadplex at
#: "one space in total" under 3,000 square feet, rising a space a band to "four
#: spaces in total" at 7,000 -- and prints 0.25, 0.5 and 0.75 nowhere. The word
#: doing the dividing is "Quadplexes" in the stem of the sentence, which is
#: :data:`DWELLINGS` by another name.
#:
#: Restricted to the two parking fields because a total is only a total where
#: the standard counts things the building has. A lot WIDTH stated as a total
#: for four dwellings is not a rule any code writes.
PARKING_TOTAL_FIELDS: frozenset[str] = frozenset(
    {"parking_min_per_unit", "parking_max_per_unit"}
)

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
        # A ceiling on parking, which most Oregon codes do not state at all --
        # Portland states one in thirteen zones and no other jurisdiction in
        # the corpus states one anywhere. Unlike the minimum beside it, which
        # every code answers even when the answer is zero, silence here is the
        # ordinary case and is not an incomplete zone.
        "parking_max_per_unit",
        # Stall and aisle geometry. Every code in the corpus states a stall
        # size somewhere, but not in the zone's own table -- it is a citywide
        # sentence in the parking chapter, so it belongs to `defaults` and a
        # zone that does not repeat it is not an incomplete zone. The aisle
        # figures are rarer still: a code can state a stall and leave the
        # aisle to a figure or a public-works standard.
        "parking_stall_width_ft",
        "parking_stall_depth_ft",
        "parking_aisle_one_way_ft",
        "parking_aisle_two_way_ft",
        # Driveway, approach and parking placement. Same argument one step
        # further out: these are sentences in an access or parking chapter
        # that name a housing type, not rows of a zone table, so a zone that
        # does not repeat them is not an incomplete zone. They are also the
        # newest family here, and listing them as required would put every
        # zone in nineteen jurisdictions into the gap ledger overnight for a
        # question no reader has been asked yet.
        "driveway_approach_min_width_ft",
        "driveway_approach_max_width_ft",
        "driveway_min_width_one_way_ft",
        "driveway_min_width_two_way_ft",
        "parking_maneuvering_max_width_ft",
        "parking_area_max_frontage_pct",
        "parking_area_max_width_ft",
        "parking_front_yard_max_pct",
        "parking_front_prohibited",
        "parking_street_setback_ft",
        "parking_building_buffer_ft",
        "open_space_min_pct",
        "open_space_min_sqft",
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
