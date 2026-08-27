"""The stall dimensions s6s lays out with must be the ones FLATS read.

s6s decides how many cars fit in a rear court, and the answer moves with the
stall by half a foot at a time. Those dimensions are law, so they belong in the
FLATS corpus where they carry a citation and can be signed against the page they
came from — footprints.yaml only mirrors them so the standalone pipeline can run
without importing the corpus.

A mirror drifts. This is the guard: every number the site plan uses has to still
equal the number the corpus holds, and an aisle the site plan leaves empty has
to be an aisle the code genuinely never states rather than one nobody typed in.
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
