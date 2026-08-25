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


def test_the_pilot_city_is_one_the_site_plan_can_actually_dimension():
    from common import load_footprints

    sp = load_footprints().siteplan
    geom = sp.geometry_for(sp.pilot_jurisdiction)
    assert geom is not None, f"{sp.pilot_jurisdiction} has no stall geometry"
    assert geom.lays_out(), (
        f"{sp.pilot_jurisdiction} states no aisle width, so a rear court cannot "
        "be dimensioned from its code — s6s would write passthrough columns"
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


def test_portland_is_refused_rather_than_given_greshams_stall():
    """Portland's stall is 9 ft and its code states no aisle. Both must hold.

    The trap is 33.266.130's Table 266-4, which prints an 8 ft 6 in stall and an
    aisle to go with it. That section's own applicability sentence hands
    residential vehicle areas back to 33.266.120, so borrowing from it is half a
    foot per stall too narrow — and an aisle Portland never wrote.
    """
    from common import load_footprints

    geom = load_footprints().siteplan.geometry["portland"]
    assert geom.stall_width_ft == 9.0
    assert geom.stall_depth_ft == 18.0
    assert geom.aisle_one_way_ft is None
    assert geom.aisle_two_way_ft is None
    assert not geom.lays_out()
