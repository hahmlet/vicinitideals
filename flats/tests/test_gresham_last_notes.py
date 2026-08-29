"""Gresham's last ten footnotes, and the two things they turned out to be.

Three hundred and fourteen notes were captured from this layer and ten were
still unread. Reading them settled the layer at zero and produced no encoding,
which is a result worth pinning rather than a shrug -- because the reasons are
two distinct findings and both of them look like gaps from the outside.

**Standards waiting for land.** Eight of the ten sit on Pleasant Valley's and
Springwater's mixed-use and employment tables, whose eight columns include four
districts this layer does not hold: TC-PV, ME-PV, VC-SW and NC-SW. An
unencoded zone is normally a hole -- Lake Oswego was short six of ten and no
ledger that counts fields could see it. These four are not. No observed lot
claims any of them, so they appear in no zone_missing row either. Gresham wrote
standards for sub-districts of two urban reserve areas that are still largely
unbuilt.

**A ceiling that does not bind.** The other two are Table 9.0851's, and one is
the only auto-parking MAXIMUM in the layer. It is real, it is now a field this
system has, and the pod is under every residential row of it: None for
quadplexes and townhouses in the eleven districts at (A)(1), None for
townhouses everywhere else, 2.0 spaces per unit for a four-or-more-unit
development. Not encoding it is a decision with a reason, and the reason is
recorded in the ruling rather than left as an absence.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.encode.dispositions import notes
from flats.rules.caps import caps_for
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"

#: Columns of Table 4.1424 and Table 4.1521 this layer does not hold.
UNCLAIMED = ("TC-PV", "ME-PV", "VC-SW", "NC-SW")
#: Columns it does hold, all four with the quadplex row reading NP.
SETTLED = ("NC-PV", "PUB-PV", "RTI-SW", "IND-SW")


def test_the_layer_has_no_unread_notes_left() -> None:
    assert [n for n in notes(GRESHAM) if n.state == "unread"] == []


def test_the_four_districts_the_tables_name_are_absent_from_both_sides() -> None:
    """Which is what makes them not a gap.

    A district missing from the rules while lots claim it is the hole this
    corpus keeps finding. A district missing from the rules that no lot claims
    is a standard Gresham has written and nobody has built under yet. The
    difference is one join, and it is the join this test makes.
    """
    encoded = set(load_rules()[GRESHAM].zones)
    observed = {r.zone for r in read_coverage() if r.jurisdiction == GRESHAM}

    for zone in UNCLAIMED:
        assert zone not in encoded, zone
        assert zone not in observed, zone


def test_the_four_it_does_hold_are_settled_prohibitions() -> None:
    """Settled, not merely shut. A prohibition under an unmeasured footnote is
    a lever and the zone still owes its five standards -- that is what caught
    RTC, MC, CC and Portland's CI1. These four carry no cap on the use gate, so
    the reading ends there and the notes above them reach no number."""
    layer = load_rules()[GRESHAM]
    owed = {
        r.zone: r.missing_required
        for r in read_coverage()
        if r.jurisdiction == GRESHAM and r.missing_required
    }

    for zone in SETTLED:
        assert layer.zones[zone].values["quadplex_allowed"].value is False, zone
        assert "quadplex_allowed" not in caps_for(GRESHAM, zone), zone
        assert zone not in owed, zone


def test_gresham_states_an_auto_parking_maximum_and_none_is_encoded() -> None:
    """Table 9.0851's ceiling column is real and the pod is under all of it.

    The number that would bind is 2.0 spaces per unit, on a development of four
    or more dwelling units outside the eleven districts at (A)(1); quadplexes
    and townhouses inside them, and townhouses anywhere, read None. Against a
    catalog target of 1.5 there is nothing to encode -- and encoding it anyway
    would mean reading five further tables, because Table 9.0851 is expressly
    displaced in the Downtown, Civic Neighborhood, Corridor and Pleasant Valley
    districts, which is 22 of this layer's 38 zones.

    Pinned so that the absence reads as a decision. If a design ever asks more
    than 2.0 stalls per unit, this is the test that should fail.
    """
    layer = load_rules()[GRESHAM]

    assert "parking_max_per_unit" not in layer.defaults
    for zone in layer.zones.values():
        assert "parking_max_per_unit" not in zone.values, zone.zone

    for design in load_catalog():
        assert design.parking.stalls_per_unit <= 2.0, design.id


def test_the_layers_that_state_a_parking_ceiling_are_the_three_that_state_one() -> None:
    """Portland was the only one until 2026-08-27, and Milwaukie is the second.

    Milwaukie's is the tighter of the two and it is aimed at this housing type
    by name: Table 19.605.1 is headed "Maximum Allowed", row A.3.c reads
    "Quadplexes -- 1 space per dwelling unit", and the row above gives
    Multi-Unit Dwellings two per unit while single detached dwellings get "No
    maximum." Four stalls for the whole building, citywide, in a code that
    requires none of them.

    That matters to the site-plan generator rather than to the screen: a rear
    court drawn at more stalls than the cap allows is not a lot that fails, it
    is a drawing that is not permitted. Gresham's ceiling is the one that came
    closest to a third and it was read and declined above.

    West Linn is the third, from 2026-08-27, and it is the loosest: CDC
    46.090(A) caps multifamily non-studio units at 2.0 spaces per unit, which
    is eight stalls for this building and above anything a rear court would
    draw. It is here because the city states a figure, not because the figure
    binds. Recording it is the point -- `exempt: true` would say West Linn has
    no ceiling, and it has one; the row simply sits above the design.

    A stated absence is not a ceiling. Portland writes `exempt: true` on the
    fifteen zones whose cell reads "No maximum", Wilsonville writes it on the
    whole layer because Table 5's middle housing row reads "No Limit", and
    Fairview and Happy Valley write it because their tables print None -- all
    four are readings, and none is a number that can refuse a building. This
    counts only the layers holding a figure.
    """

    def states_a_figure(value: object) -> bool:
        return getattr(value, "value", None) is not None

    carrying = {
        name
        for name, layer in load_rules().items()
        if states_a_figure(layer.defaults.get("parking_max_per_unit"))
        or any(
            states_a_figure(z.values.get("parking_max_per_unit"))
            for z in layer.zones.values()
        )
    }

    assert carrying == {
        "or/multnomah/portland",
        "or/clackamas/milwaukie",
        "or/clackamas/west-linn",
    }
