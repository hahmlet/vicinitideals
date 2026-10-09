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


# --- which street a lowest-class corner lot's driveway uses (41(i)) --------

def ranked(main: int | None = 0, oak: int | None = 1):
    return build(
        [MILWAUKIE],
        [MAIN, OAK],
        ["local", "other"],
        ["SE MAIN ST", "SE OAK AVE"],
        [MAIN, OAK],
        ["SE MAIN ST", "SE OAK AVE"],
        [1500, 1450],
        [main, oak],
    )


def corner(main: int | None, oak: int | None):
    """A corner lot on Main (front) and Oak, its lines ranked."""
    from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg

    def edge(x1, y1, x2, y2, cls, rank=None):
        return Edge(
            x1, y1, x2, y2, length_ft=((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5,
            bearing_deg=bearing_deg(x1, y1, x2, y2), cls=cls, street_rank=rank,
        )

    lines = (
        edge(280, 20, 380, 20, EdgeClass.front, main),
        edge(380, 20, 380, 120, EdgeClass.front, oak),
        edge(380, 120, 280, 120, EdgeClass.rear),
        edge(280, 120, 280, 20, EdgeClass.side),
    )
    bearings = (lines[0].bearing_deg, lines[1].bearing_deg)
    return LotEdges(Tier.corner, lines, bearings, 200.0, 1.0), bearings


def access(value: str = "lowest_class"):
    from flats.rules.resolver import Resolved, ZoneResolution

    held = Resolved("corner_access_street", value, None, None, "or/clackamas/milwaukie", "defaults")  # type: ignore[arg-type]
    return ZoneResolution("milwaukie", "R-5", None, {"corner_access_street": held})  # type: ignore[arg-type]


def test_the_map_ranks_each_street_line() -> None:
    from flats.geom.street_class import edge_rank, street_ranks

    m = ranked()
    assert edge_rank(ON_MAIN, m) == 0
    assert edge_rank(ON_OAK, m) == 1
    assert street_ranks([ON_MAIN, ON_OAK, SIDE], MILWAUKIE, [m]) == [0, 1, None]
    assert street_ranks([ON_MAIN], "or/clackamas/oregon-city", [m]) == [None]
    assert street_ranks([ON_MAIN], MILWAUKIE, [ranked(main=None)]) == [None]
    spec = CLASS_MAPS["street_class_milwaukie"]
    assert spec.rank["Local Street"] < spec.rank["Neighborhood Routes"] < spec.rank["Collector"] < spec.rank["Arterial"]
    assert "Proposed Local" not in spec.rank


def test_every_ranking_map_starts_local_at_zero_and_ranks_no_proposal() -> None:
    from flats.geom.street_class import class_rank
    from flats.ingest.sources import load_pipeline

    datasets = load_pipeline().datasets
    for key, spec in CLASS_MAPS.items():
        assert key in datasets and datasets[key].serves, key
        lowest = min([*spec.rank.values(), *([] if spec.unlisted is None else [spec.unlisted])])
        assert lowest == 0, key
        assert not any("Proposed" in v for v in spec.rank), key
    beaverton = CLASS_MAPS["street_class_beaverton"]
    # Coded domains arrive as numbers or strings alike.
    assert class_rank(9, beaverton) == class_rank("9", beaverton) == 0
    assert class_rank("4", beaverton) is None  # Proposed Arterial
    west_linn = CLASS_MAPS["street_class_west_linn"]
    assert class_rank(10, west_linn) is None and class_rank(11, west_linn) is None
    washington = CLASS_MAPS["street_class_washington"]
    assert washington.unlisted == 0 and class_rank(5, washington) == 1  # Neighborhood Route
    assert class_rank(40, washington) is None  # Proposed Collector


def unlisted_map(oak: int | None = 2, main_type: int = 1500):
    """Washington County's shape of map: Oak drawn (ranked ``oak``), Main
    not drawn at all, Metro typing Main ``main_type``."""
    return build(
        ["or/washington/_unincorporated"],
        [OAK],
        [""],
        [""],
        [MAIN, OAK],
        ["SE MAIN ST", "SE OAK AVE"],
        [main_type, 1450],
        [oak],
        unlisted=0,
    )


def test_a_street_the_map_leaves_out_is_local_only_where_metro_says_so() -> None:
    from flats.geom.street_class import edge_rank

    m = unlisted_map()
    assert edge_rank(ON_OAK, m) == 2
    assert edge_rank(ON_MAIN, m) == 0
    # Metro calls Main something busier: the absence alone ranks nothing.
    assert edge_rank(ON_MAIN, unlisted_map(main_type=1450)) is None
    # A drawn street of no rank (a proposal) is not read as undrawn.
    assert edge_rank(ON_OAK, unlisted_map(oak=None)) is None
    # A line no street runs beside stays unread.
    assert edge_rank([100.0, 900.0, 200.0, 900.0, "F"], m) is None
    # Every other map: an undrawn street is unread.
    no_unlisted = build(["x"], [OAK], [""], [""], [MAIN, OAK], ["", ""], [1500, 1450], [2])
    assert edge_rank(ON_MAIN, no_unlisted) is None


def test_a_quiet_front_sends_the_driveway_to_the_front() -> None:
    from flats.geom.corner import name_front
    from flats.geom.street_class import FRONT_ACCESS, measured_access
    from flats.score.paper import side_street_fed

    edges, (main, oak) = corner(main=0, oak=2)
    rules = access()
    got = measured_access(rules, name_front(edges, main), main)
    assert got.get("corner_access_street") == FRONT_ACCESS
    assert got.values["corner_access_street"].shadowed == "lowest_class"
    assert side_street_fed(rules, None, True) and not side_street_fed(got, None, True)
    # The busy street named the front: the quiet side street serves.
    assert measured_access(rules, name_front(edges, oak), oak) is rules


def test_anything_short_of_a_measured_quieter_front_changes_nothing() -> None:
    from flats.geom.corner import name_front
    from flats.geom.street_class import measured_access

    for main, oak in ((1, 1), (2, 0), (None, 2), (0, None)):
        edges, (front, _) = corner(main, oak)
        rules = access()
        assert measured_access(rules, name_front(edges, front), front) is rules
    edges, (front, _) = corner(0, 2)
    rules = access()
    assert measured_access(rules, edges, None) is rules  # no front named
    assert measured_access(rules, None, front) is rules
    for value in ("any", "side"):
        other = access(value)
        assert measured_access(other, name_front(edges, front), front) is other


def test_each_plans_access_street_is_recorded_with_why() -> None:
    from flats.geom.corner import name_front
    from flats.geom.street_class import access_record, measured_access

    def record(main, oak, front_index, value="lowest_class"):
        edges, bearings = corner(main, oak)
        front = bearings[front_index]
        rules = access(value)
        named = name_front(edges, front)
        return access_record(rules, measured_access(rules, named, front), named, front)

    assert record(0, 2, 0)["access"] == "front" and record(0, 2, 0)["why"] == "front_quieter"
    assert record(2, 0, 0)["access"] == "side" and record(2, 0, 0)["why"] == "side_quieter_or_equal"
    for main, oak in ((None, 2), (0, None)):
        got = record(main, oak, 0)
        assert (got["access"], got["why"]) == ("side", "rank_missing")
    assert record(0, 2, 0, "side")["why"] == "code_names_street"
    edges, (front, _) = corner(0, 2)
    none = access_record(access(), access(), edges, None)
    assert (none["access"], none["why"], none["front_deg"]) == ("side", "no_front_named", None)


def test_the_bridge_carries_the_ranks_onto_the_lot_lines(monkeypatch, tmp_path) -> None:
    import flats.ingest.quadfit as bridge

    monkeypatch.setattr(bridge, "load_class_maps", lambda sources: (ranked(),))
    row = {
        "TLID": "corner", "jurisdiction": "milwaukie", "tier": "A",
        "edges_json": json.dumps([ON_MAIN, ON_OAK, SIDE]), "front_bearings_json": "[90.0, 0.0]",
    }
    with_local_street([row], tmp_path)
    assert json.loads(row["street_ranks_json"]) == [0, 1, None]
    edges = bridge.lot_edges(row)
    assert [e.street_rank for e in edges.edges] == [0, 1, None]
    # A row with no ranks (no map) ranks nothing.
    del row["street_ranks_json"]
    assert all(e.street_rank is None for e in bridge.lot_edges(row).edges)
