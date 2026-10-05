"""local_street from a city's TSP map: two sources for local, one for not.

The fact switches a looser number on (Milwaukie's 12 ft driveway apron,
Villebois's 12 ft front yard), so True is the expensive answer: it needs the
city's map and Metro's street type to agree, on every street line of the
lot. False -- a collector or an arterial on every line -- keeps the base
every encoding already uses, and needs the map alone.
"""

from __future__ import annotations

import json

from shapely.geometry import LineString

from flats.geom.street_class import (
    CLASS_MAPS,
    LOCAL_STREET,
    build,
    class_kind,
    edge_class,
    observed_local_street,
)
from flats.ingest.quadfit import OBSERVABLE, observed_facts, with_local_street
from flats.rules.conditions import CONDITIONS

MILWAUKIE = "or/clackamas/milwaukie"

# Main St runs east along y=0; Oak Ave runs north along x=400.
MAIN = LineString([(-200, 0), (400, 0)])
OAK = LineString([(400, -200), (400, 400)])


def cmap(main_kind: str = "local", oak_kind: str = "other", main_type: int = 1500, oak_type: int = 1450):
    return build(
        [MILWAUKIE],
        [MAIN, OAK],
        [main_kind, oak_kind],
        ["SE MAIN ST", "SE OAK AVE"],
        [MAIN, OAK],
        ["SE MAIN ST", "SE OAK AVE"],
        [main_type, oak_type],
    )


# Street lines 20 ft back from the centreline, as a lot line sits.
ON_MAIN = [100.0, 20.0, 200.0, 20.0, "F"]
ON_OAK = [380.0, 100.0, 380.0, 200.0, "F"]
SIDE = [100.0, 20.0, 100.0, 120.0, "S"]


def test_a_lot_on_a_local_street_is_on_a_local_street() -> None:
    m = cmap()
    assert edge_class(ON_MAIN, m) == "local"
    assert observed_local_street([ON_MAIN, SIDE], MILWAUKIE, [m]) == {LOCAL_STREET: True}


def test_a_lot_on_a_collector_is_not() -> None:
    m = cmap()
    assert edge_class(ON_OAK, m) == "other"
    assert observed_local_street([ON_OAK, SIDE], MILWAUKIE, [m]) == {LOCAL_STREET: False}


def test_a_corner_of_a_local_and_a_collector_is_left_unasked() -> None:
    assert observed_local_street([ON_MAIN, ON_OAK], MILWAUKIE, [cmap()]) == {}


def test_local_needs_metros_street_type_to_agree() -> None:
    # The city map says local, Metro types the street a neighbourhood
    # collector: a TSP newer than the plan in force would pass this lot.
    m = cmap(main_type=1450)
    assert edge_class(ON_MAIN, m) == ""
    assert observed_local_street([ON_MAIN], MILWAUKIE, [m]) == {}
    # Not local needs no agreement: it is the stricter answer.
    assert observed_local_street([ON_OAK], MILWAUKIE, [cmap(oak_type=1500)]) == {LOCAL_STREET: False}


def test_a_class_the_code_does_not_settle_reads_as_unknown() -> None:
    spec = CLASS_MAPS["street_class_milwaukie"]
    assert class_kind("Local Street", spec) == "local"
    assert class_kind("Collector", spec) == "other"
    assert class_kind("Through Movement Priority Arterial", spec) == "other"
    for value in ("Neighborhood Routes", "Proposed Local", "", None):
        assert class_kind(value, spec) == ""
    assert observed_local_street([ON_MAIN], MILWAUKIE, [cmap(main_kind="")]) == {}
    wilsonville = CLASS_MAPS["street_class_wilsonville"]
    assert class_kind("Minor Arterial", wilsonville) == "other"


def test_wilsonvilles_tsp_map_never_calls_a_villebois_street_local() -> None:
    # Villebois's Collector Avenues are the master plan's (Figure 7), which
    # draws Minor Collectors on streets the TSP map calls Local Street: the
    # TSP map can say a street is a collector, never that it is not one.
    wilsonville = CLASS_MAPS["street_class_wilsonville"]
    assert not wilsonville.local
    assert class_kind("Local Street", wilsonville) == ""
    assert class_kind("Collector", wilsonville) == "other"


def test_a_line_no_street_runs_beside_is_unread() -> None:
    far = [100.0, 300.0, 200.0, 300.0, "F"]
    assert edge_class(far, cmap()) == ""
    assert observed_local_street([far], MILWAUKIE, [cmap()]) == {}


def test_only_where_a_map_serves_the_lot() -> None:
    assert observed_local_street([ON_MAIN], "or/clackamas/oregon-city", [cmap()]) == {}
    assert observed_local_street([SIDE], MILWAUKIE, [cmap()]) == {}
    assert observed_local_street([], MILWAUKIE, [cmap()]) == {}


def test_the_bridge_carries_the_answer_into_the_facts(monkeypatch, tmp_path) -> None:
    import flats.ingest.quadfit as bridge

    monkeypatch.setattr(bridge, "load_class_maps", lambda sources: (cmap(),))
    rows = [
        {"TLID": "local", "jurisdiction": "milwaukie", "edges_json": json.dumps([ON_MAIN, SIDE])},
        {"TLID": "collector", "jurisdiction": "milwaukie", "edges_json": json.dumps([ON_OAK])},
        {"TLID": "corner", "jurisdiction": "milwaukie", "edges_json": json.dumps([ON_MAIN, ON_OAK])},
        {"TLID": "elsewhere", "jurisdiction": "gresham", "edges_json": json.dumps([ON_MAIN])},
    ]
    assert with_local_street(rows, tmp_path) == 2
    got = {r["TLID"]: r for r in rows}
    assert observed_facts(got["local"])[LOCAL_STREET] is True
    assert observed_facts(got["collector"])[LOCAL_STREET] is False
    assert LOCAL_STREET not in observed_facts(got["corner"])
    assert LOCAL_STREET not in observed_facts(got["elsewhere"])
    assert with_local_street(rows, None) == 0


def test_the_fact_is_observable_and_still_assumes_nothing() -> None:
    assert LOCAL_STREET in OBSERVABLE
    assert CONDITIONS[LOCAL_STREET].assume is None
