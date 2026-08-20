"""Orient: a rural crossroads with two zones and one difference that matters.

MCC Part 4.C.5 and 4.C.6 cover the same unincorporated community. Orient Rural
Center Residential (OR) is 17 lots, Orient Commercial-Industrial (OCI) is six,
and both articles are built the same way: a closure sentence, an allowed list
whose only dwelling is a single-family detached one, a short review list, and
two conditional entries.

The two conditional entries are where they part. OR's first is "Planned
Developments pursuant to the provisions of MCC 39.5300 through 39.5350" with
nothing after it, which reaches an overlay that names attached dwellings. OCI's
are community service uses and a state or regional trail. Same crossroads, same
ordinance, and one of them can be argued to a yes.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

UNINC = "or/multnomah/_unincorporated"
POD = ("multi_story", "attached_wall")
ORIENT = ("OR", "OCI")


@pytest.fixture(scope="module")
def uninc() -> Layer:
    return load_rules()[UNINC]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_both_orient_zones_refuse_the_pod_outright(rules: RuleSet) -> None:
    for zone in ORIENT:
        res = rules.resolve(UNINC, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone


def test_the_closed_list_is_what_makes_each_silence_readable(
    uninc: Layer, store: ProvenanceStore
) -> None:
    for zone in ORIENT:
        text = store.quote(uninc.zones[zone].values["quadplex_allowed"].prov.quote)
        assert "the uses listed in" in text, zone
        assert "detached dwelling" in text, zone


def test_the_commercial_zone_owes_the_use_flag_and_nothing_else(
    uninc: Layer,
) -> None:
    """No dimensions on a zone whose use list already closed.

    39.4680 states an acre, 35 feet and the same 30/10/30/30 yard row the rest
    of rural Multnomah prints. Encoding them here would put an answerable-
    looking envelope on land nothing can be built on; the note carries them so
    the next reader can see they were read.
    """
    assert set(uninc.zones["OCI"].values) == {"quadplex_allowed"}

    notes = uninc.zones["OCI"].notes or ""
    assert "39.4680" in notes
    assert "30/10/30/30" in notes


def test_the_residential_zone_owes_the_whole_envelope(uninc: Layer) -> None:
    """Because a variant can make its use flag true, and a door needs a room."""
    values = set(uninc.zones["OR"].values)
    assert {"max_height_ft", "min_lot_sqft", "min_frontage_ft"} <= values
    assert {
        "setback_front_ft",
        "setback_side_ft",
        "setback_street_side_ft",
        "setback_rear_ft",
    } <= values


def test_the_residential_yard_row_is_read_across_not_down(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """One printed line -- "30 10 30 30" -- under "Front Side Street Side Rear".

    The street-side number matching the front number rather than the side one
    is what makes the ordering checkable, and it is the same row EFU, MUA-20
    and RR print.
    """
    zone = uninc.zones["OR"]
    assert zone.values["setback_front_ft"].value == 30
    assert zone.values["setback_side_ft"].value == 10
    assert zone.values["setback_street_side_ft"].value == 30
    assert zone.values["setback_rear_ft"].value == 30

    text = store.quote(zone.values["setback_side_ft"].prov.quote)
    assert "Front Side Street Side Rear" in text
    assert "30 10 30 30" in text


def test_the_difference_between_the_two_lists_is_recorded(uninc: Layer) -> None:
    """OCI's note says why it answers differently from the zone across the road.

    An absence is only usable where somebody has said what they looked for.
    """
    notes = uninc.zones["OCI"].notes or ""
    assert "Planned Development" in notes
    assert "39.5350(A)" in notes


def test_the_second_condition_nobody_can_check_is_written_down(
    uninc: Layer,
) -> None:
    """39.4620(A) also invokes OAR 660 Division 004 outside an acknowledged
    community, and neither the OAR nor the acknowledgement is in hand."""
    notes = uninc.zones["OR"].notes or ""
    assert "acknowledged unincorporated community" in notes
    assert "660" in notes


def test_the_orient_citations_all_point_at_their_own_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    ready = readiness_for(uninc, store=store)
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
