"""Every dimension s6s lays out with must be the one FLATS read.

s6s decides how many cars fit in a rear court and how much of the lot is left
over, and the answers move with the stall by half a foot and with the driveway
by eight. Those dimensions are law, so they belong in the FLATS corpus where
they carry a citation and can be signed against the page they came from —
footprints.yaml only mirrors them so the standalone pipeline can run without
importing the corpus.

Two families are mirrored. The stall and aisle, which decide how many cars a
court seats; and the driveway, the curb cut, the building-to-parking gap and
the private open-space reserve, which decide whether there is room for a court
at all. The second family got here late: until it did, s6s drew every city's
driveway to five constants lifted out of Gresham's TOWNHOUSE chapter, two of
which were not even Gresham's law on the plat this stage draws.

A mirror drifts. This is the guard: every number the site plan uses has to
still equal the number the corpus holds, and a rule the site plan leaves empty
has to be one the code genuinely never states rather than one nobody typed in.
"""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")

pytestmark = pytest.mark.unit

#: quadfit's StallGeometry field -> the FLATS field registry name.
MIRRORED = {
    "stall_width_ft": "parking_stall_width_ft",
    "stall_depth_ft": "parking_stall_depth_ft",
    "aisle_one_way_ft": "parking_aisle_one_way_ft",
    "aisle_two_way_ft": "parking_aisle_two_way_ft",
}

#: quadfit's DrivewayRules field -> the FLATS field registry name. The
#: open-space pair is in here too: it is not a driveway rule, but it is the
#: fourth claimant on the same lot and it arrived in the same reading.
DRIVEWAY_MIRRORED = {
    "approach_min_ft": "driveway_approach_min_width_ft",
    "approach_max_ft": "driveway_approach_max_width_ft",
    "drive_min_one_way_ft": "driveway_min_width_one_way_ft",
    "drive_min_two_way_ft": "driveway_min_width_two_way_ft",
    "maneuvering_max_ft": "parking_maneuvering_max_width_ft",
    "parking_max_frontage_pct": "parking_area_max_frontage_pct",
    "parking_max_width_ft": "parking_area_max_width_ft",
    "parking_front_yard_max_pct": "parking_front_yard_max_pct",
    "parking_street_setback_ft": "parking_street_setback_ft",
    "building_buffer_ft": "parking_building_buffer_ft",
    "open_space_pct": "open_space_min_pct",
    "open_space_sqft": "open_space_min_sqft",
}


def _corpus_value(layer_id: str, field: str):
    """The innermost layer's Value for one field, exempt ones included.

    Separate from _corpus_defaults because `exempt: true` means two different
    things depending on the field. For a dimension it means nobody stated one,
    which is the same as absent. For a maximum it is a READING — the city looked
    at its own ceiling table and this building is not on it — and it has to beat
    a broader layer's number rather than fall through to it.
    """
    from flats.encode.load import load_trusted
    from flats.rules.resolver import RuleSet

    rules = RuleSet(load_trusted(strict=False).layers)
    found = None
    for layer in rules.chain_for(layer_id):  # broadest first, so the city wins
        value = layer.defaults.get(field)
        if value is not None:
            found = value
    return found


def _corpus_defaults(layer_id: str) -> dict:
    """The parking geometry a layer resolves to, city over county over state."""
    from flats.encode.load import load_trusted
    from flats.rules.resolver import RuleSet

    rules = RuleSet(load_trusted(strict=False).layers)
    out: dict = {}
    for layer in rules.chain_for(layer_id):  # broadest first, so the city wins
        for field in MIRRORED.values():
            value = layer.defaults.get(field)
            if value is not None and not value.exempt:
                out[field] = value
    return out


def test_every_shipped_dimension_is_the_one_the_corpus_holds():
    from common import load_footprints
    from flats.encode.port_quadfit import layer_id_for

    sp = load_footprints().siteplan
    assert sp is not None and sp.geometry, "the site plan ships no stall geometry"

    for jurisdiction, geom in sp.geometry.items():
        corpus = _corpus_defaults(layer_id_for(jurisdiction))
        for mine, theirs in MIRRORED.items():
            shipped = getattr(geom, mine)
            read = corpus.get(theirs)
            if shipped is None:
                # Not "unknown" — the claim being made is that the code states
                # no such dimension. If the corpus has one, the site plan is
                # refusing to lay out a city it could have laid out.
                assert read is None, (
                    f"{jurisdiction}: footprints.yaml leaves {mine} empty but the "
                    f"corpus reads {theirs} = {read.value} ({read.prov.cite})"
                )
                continue
            assert read is not None, (
                f"{jurisdiction}: footprints.yaml ships {mine} = {shipped} with no "
                f"{theirs} in the corpus behind it — an uncited dimension"
            )
            assert float(read.value) == pytest.approx(float(shipped)), (
                f"{jurisdiction}: {mine} is {shipped} here and {read.value} in the "
                f"corpus ({read.prov.cite}); the corpus is the one that was read"
            )


def test_every_shipped_ceiling_is_the_one_the_corpus_holds():
    """The maximum mirrors too, and `null` here has to mean `exempt` there.

    A ceiling is the one parking number that can make a lot LOOK worse than it
    is — eight stalls of room and a city that permits four — so a stale copy of
    one is a site plan drawn to a rule that was repealed, or to none where one
    exists. Milwaukie is the live case at one space per unit.
    """
    from common import load_footprints
    from flats.encode.port_quadfit import layer_id_for

    for jurisdiction, geom in load_footprints().siteplan.geometry.items():
        read = _corpus_value(layer_id_for(jurisdiction), "parking_max_per_unit")
        stated = None if read is None or read.exempt else float(read.value)
        assert geom.max_per_unit == stated, (
            f"{jurisdiction}: footprints.yaml ships max_per_unit="
            f"{geom.max_per_unit} where the corpus reads {stated}"
            + (f" ({read.prov.cite})" if read is not None else " (nothing)")
        )


def test_a_dimension_that_stands_down_stands_down_for_the_same_reason():
    """`stands_down_on` mirrors the corpus `unless:`, not a local judgement.

    Oregon City is the only entry that carries one, because OCMC 17.52.010
    excludes townhouses from the parking chapter and leaves quadplexes in it.
    If the corpus ever drops that condition — or another city gains one — the
    mirror has to move with it, or s6s lays out a city on a plat path whose
    code never reached the building.
    """
    from common import load_footprints
    from flats.encode.port_quadfit import layer_id_for

    for jurisdiction, geom in load_footprints().siteplan.geometry.items():
        corpus = _corpus_defaults(layer_id_for(jurisdiction))
        for theirs in MIRRORED.values():
            read = corpus.get(theirs)
            if read is None:
                continue
            unless = sorted(getattr(read, "unless", ()) or ())
            assert sorted(geom.stands_down_on) == unless, (
                f"{jurisdiction}: {theirs} stands down on {unless} in the corpus "
                f"and on {sorted(geom.stands_down_on)} here"
            )


def test_the_cities_laid_out_are_exactly_the_ones_that_can_be():
    """Scope follows the reading. A city read is a city laid out, or a refusal.

    The pilot city used to be the only thing this asserted, back when it was
    the only city with geometry. What matters now is that no city is quietly
    dropped: every entry either lays out or fails `lays_out()` for a stated
    reason, and the pilot — still the cell the drawings were sampled from —
    is among the ones that lay out.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    laid_out = set(sp.cities_it_can_dimension())
    assert laid_out, "nothing in the corpus can be dimensioned"
    assert sp.pilot_jurisdiction in laid_out

    for jurisdiction, geom in sp.geometry.items():
        if jurisdiction in laid_out:
            continue
        assert not geom.lays_out() or sp.plat in geom.stands_down_on, (
            f"{jurisdiction} states both a stall and an aisle and is still not "
            "being laid out"
        )


def test_greshams_one_way_aisle_is_the_parking_aisle_not_the_fire_lane():
    """Table 9.0825A says 23 ft at 90°. The 20 is note 1's emergency figure.

    Pinned by name because the two numbers sit four lines apart on the same page
    and the wrong one was read once already. A 20 ft aisle makes a 38 ft court
    look deep enough for a row of stalls that really needs 41.
    """
    from common import load_footprints

    geom = load_footprints().siteplan.geometry["gresham"]
    assert geom.aisle_one_way_ft == 23.0
    assert geom.aisle_two_way_ft == 24.0


def test_portland_takes_the_branch_a_parking_tract_reaches():
    """Table 266-4's 90° row, not 33.266.120.D.1's 9 x 18.

    Portland states both and routes between them in one sentence: 33.266.120
    governs this building type, but 120.B.1 sends parking that is in a parking
    TRACT to 33.266.130 instead, and 130.B agrees from the other side. A shared
    rear court serving four attached houses on fee-simple lots is a tract, so
    the table applies — 8'6" x 16 with a 20 ft aisle, where D.1 alone would have
    said 9 x 18 and no aisle at all.

    Pinned because the section titled for the building is the one you find
    first, and reading only that far is a court 9 ft deep instead of 36.
    """
    from common import load_footprints

    geom = load_footprints().siteplan.geometry["portland"]
    assert (geom.stall_width_ft, geom.stall_depth_ft) == (8.5, 16.0)
    # Both columns print 20. Every other city in the corpus widens the two-way,
    # so an assertion that they differ would look right and be wrong.
    assert geom.aisle_one_way_ft == 20.0
    assert geom.aisle_two_way_ft == 20.0
    assert geom.lays_out()


def test_a_city_that_states_no_aisle_is_declined_rather_than_borrowed_from():
    """The refusal path, exercised on a city rather than pinned to Portland.

    Portland used to be this test's example, on a reading that stopped at
    33.266.120. The machinery is still needed — a code really may state a stall
    and no aisle — but a live jurisdiction is the wrong way to hold it, because
    the test then goes green on a misreading and red when the misreading is
    corrected.
    """
    from common import StallGeometry

    stall_only = StallGeometry(stall_width_ft=9.0, stall_depth_ft=18.0)
    assert not stall_only.lays_out()
    assert StallGeometry(
        stall_width_ft=9.0, stall_depth_ft=18.0, aisle_one_way_ft=20.0
    ).lays_out() is False


# ---------------------------------------------------------------------------
# the driveway family
# ---------------------------------------------------------------------------


def _one_lot_value(layer_id: str, field: str):
    """What a city's code states for four units on ONE lot, or None.

    None where the corpus is silent AND where it is `exempt: true`, because for
    a rule about where pavement may sit the two constrain a drawing
    identically: neither puts a limit on the drawing. That is not true of the
    stall ceiling one file over, which is why this helper exists rather than
    reusing that one.

    Variants keyed to `unit_lots` are ignored and an `unless: [unit_lots]` is
    honoured, which is the one-lot branch — the plat this stage draws, and the
    plat SiteplanSpec refuses to move off while the mirror holds these values.
    """
    read = _corpus_value(layer_id, field)
    if read is None or read.exempt:
        return None
    return read


def test_every_shipped_driveway_rule_is_the_one_the_corpus_holds():
    """The second mirror, guarded exactly like the first.

    An omitted field means the city was read and its code states no such rule.
    A city omitted from the map entirely means nobody read that city. The
    difference decides whether a lot gets an approach cap and an open-space
    reserve charged against it or gets neither, so it cannot be left to
    whichever is easier to type.
    """
    from common import load_footprints
    from flats.encode.port_quadfit import layer_id_for

    sp = load_footprints().siteplan
    assert sp is not None and sp.driveway, "the site plan ships no driveway rules"

    for jurisdiction, dw in sp.driveway.items():
        layer = layer_id_for(jurisdiction)
        for mine, theirs in DRIVEWAY_MIRRORED.items():
            shipped = getattr(dw, mine)
            read = _one_lot_value(layer, theirs)
            if shipped is None:
                assert read is None, (
                    f"{jurisdiction}: footprints.yaml leaves {mine} empty but the "
                    f"corpus reads {theirs} = {read.value} ({read.prov.cite}); a "
                    f"rule read and not mirrored is a rule the site plan ignores"
                )
                continue
            assert read is not None, (
                f"{jurisdiction}: footprints.yaml ships {mine} = {shipped} with no "
                f"{theirs} in the corpus behind it — an uncited dimension"
            )
            assert float(read.value) == pytest.approx(float(shipped)), (
                f"{jurisdiction}: {mine} is {shipped} here and {read.value} in the "
                f"corpus ({read.prov.cite}); the corpus is the one that was read"
            )


def test_the_front_parking_ban_is_mirrored_as_a_ban_and_not_as_a_cap():
    """`parking_front_prohibited` is a bool, and the false value is None.

    Every other field in the family is a number, where absent and exempt mean
    the same thing. This one is three-valued and the middle value is the trap:
    Portland and Milwaukie BAN parking in front of the building, and Fairview,
    Wilsonville, Oregon City and unincorporated Clackamas CAP it at half the
    frontage instead. A ban and a cap are not the same rule; encoding one as
    the other is how a front-yard court gets drawn in a city that forbids it,
    or refused in a city that allows it.
    """
    from common import load_footprints
    from flats.encode.port_quadfit import layer_id_for

    for jurisdiction, dw in load_footprints().siteplan.driveway.items():
        read = _one_lot_value(layer_id_for(jurisdiction), "parking_front_prohibited")
        stated = None if read is None else bool(read.value)
        assert dw.parking_front_prohibited == stated, (
            f"{jurisdiction}: footprints.yaml ships parking_front_prohibited="
            f"{dw.parking_front_prohibited} where the corpus reads {stated}"
            + (f" ({read.prov.cite})" if read is not None else " (nothing)")
        )


def test_a_city_that_states_open_space_by_zone_is_mirrored_for_every_zone():
    """Portland is the only city that does, and a missed zone reserves nothing.

    Table 110-4 asks 250 sq ft of outdoor area in most residential zones and
    200 in R2.5. The jurisdiction-level fields cannot hold a per-zone rule, so
    the mirror carries a map — and a zone quadfit lays out that is missing from
    the map falls through to zero, which is a lot passed on a reserve the city
    does require. Every quadplex-allowed zone in rules.yaml has to be in it.
    """
    from common import load_footprints, load_rules
    from flats.encode.load import load_trusted
    from flats.encode.port_quadfit import layer_id_for
    from flats.rules.resolver import RuleSet

    rules = load_rules()
    corpus = RuleSet(load_trusted(strict=False).layers)

    for jurisdiction, dw in load_footprints().siteplan.driveway.items():
        if not dw.open_space_sqft_by_zone:
            continue
        jr = rules.jurisdictions.get(jurisdiction)
        assert jr is not None, f"{jurisdiction} has no rules.yaml block"
        layer = corpus.chain_for(layer_id_for(jurisdiction))[-1]
        for zr in jr.zones:
            if not zr.quadplex_allowed:
                continue
            assert zr.zone in dw.open_space_sqft_by_zone, (
                f"{jurisdiction} {zr.zone}: laid out by s6s and missing from "
                f"open_space_sqft_by_zone, so it reserves nothing"
            )
            shipped = dw.open_space_sqft_by_zone[zr.zone]
            z = layer.zones.get(zr.zone)
            read = None if z is None else z.values.get("open_space_min_sqft")
            stated = None if read is None or read.exempt else float(read.value)
            assert shipped == stated, (
                f"{jurisdiction} {zr.zone}: mirror says {shipped} sq ft and the "
                f"corpus says {stated}"
            )


def test_the_open_space_reserve_is_each_citys_own_and_not_greshams():
    """The single largest thing this change moved, pinned by name.

    Fifteen percent of every lot was being reserved in seven cities on the
    strength of Gresham GDC 7.0431(D)(1). Four of the cities s6s can dimension
    state no private open space standard for this building at all — Fairview's
    is an RM-district multi-unit rule, Wilsonville's is the Villebois village
    zone, Oregon City's was a cottage-cluster IMPERVIOUS cover rule, and Happy
    Valley's footnote points at a section that does not contain it. A reserve
    charged to a city that never asked for it is a lot refused for nothing.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    lot = 5000.0
    assert sp.open_space_required_sqft("gresham", "LDR-5", lot) == pytest.approx(750.0)
    assert sp.open_space_required_sqft("milwaukie", "R-MD", lot) == pytest.approx(384.0)
    assert sp.open_space_required_sqft("portland", "R5", lot) == pytest.approx(250.0)
    assert sp.open_space_required_sqft("portland", "R2.5", lot) == pytest.approx(200.0)
    for none_at_all in ("fairview", "wilsonville", "oregon_city", "happy_valley"):
        assert sp.open_space_required_sqft(none_at_all, "", lot) == 0.0, (
            f"{none_at_all} states no private open space for this building and "
            f"is being charged one anyway"
        )


def test_happy_valleys_driveway_is_twenty_feet_and_everyone_elses_is_twelve():
    """The one number in this family that takes lots away, pinned by name.

    LDC 16.41.030.B.1 asks 20 ft for a two-way drive. The lane this stage draws
    is two-way, so a Happy Valley side yard gives up twenty feet for the depth
    of the building where every other city gives up twelve. It is a MINIMUM: it
    cannot be traded down the way an approach ceiling can be traded up, and on
    a narrow lot it is the whole difference between a site plan and none.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    assert sp.lane_ft_for("happy_valley") == 20.0
    for twelve in ("gresham", "portland", "fairview", "oregon_city"):
        assert sp.lane_ft_for(twelve) == sp.driveway_lane_design_ft


def test_greshams_curb_cut_is_ten_feet_on_the_plat_this_stage_draws():
    """7.0420(B)(2)(b)(ii), not 7.0431(B)(2)(b), and it is nearly half.

    Eighteen feet shipped for a year. It is the TOWNHOUSE combined approach and
    it reaches this pod only on four lots; on the one lot s6s draws, a fourplex
    with no garage gets ten. Pinned because the two sections are eleven pages
    apart in the same chapter and the wrong one was read once already — the
    same failure, in the same document, as the aisle above.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    assert sp.driveway_for("gresham").approach_max_ft == 10.0
    # The cut narrows to the cap and the lane stays a lane: legal, because the
    # approach standard governs the opening at the property line and nothing
    # behind it.
    assert sp.curb_cut_ft_for("gresham") == 10.0
    assert sp.lane_ft_for("gresham") == 12.0


def test_a_lane_a_city_forbids_is_a_city_that_is_not_laid_out():
    """A maneuvering cap under a car's width is a refusal, not a narrow drive.

    Milwaukie's townhouse path caps outdoor parking and maneuvering areas at
    ten feet, which is a single-file driveway and not a court. Nothing in the
    shipped one-lot config hits this, so it is exercised directly: the point is
    that the generator declines the city rather than drawing a lane two feet
    narrower than the code allows a car to be.
    """
    from common import DrivewayRules, StallGeometry, load_footprints

    sp = load_footprints().siteplan.model_copy(deep=True)
    sp.geometry["testville"] = StallGeometry(
        stall_width_ft=9, stall_depth_ft=18, aisle_one_way_ft=24, aisle_two_way_ft=24
    )
    sp.driveway["testville"] = DrivewayRules(maneuvering_max_ft=10)
    assert sp.lane_ft_for("testville") is None
    assert sp.curb_cut_ft_for("testville") is None
    assert "testville" not in sp.cities_it_can_dimension()


def test_the_unit_lot_plat_is_refused_while_the_mirror_is_the_one_lot_branch():
    """Flipping `plat` has to be a reading, not a config change.

    Every city in this corpus states a different approach width and a different
    maneuvering cap for townhouses on their own lots — Oregon City 24 ft where a
    quadplex gets 36, Milwaukie 10 ft where a quadplex has no width limit at
    all. The mirror holds the one-lot branch. Loading the other plat against it
    would draw a townhouse to a quadplex's numbers silently, so it raises.
    """
    import pydantic

    from common import load_footprints

    sp = load_footprints().siteplan
    with pytest.raises(pydantic.ValidationError, match="ONE-LOT"):
        sp.model_copy(update={"plat": "unit_lots"}).model_validate(
            sp.model_dump() | {"plat": "unit_lots"}
        )
