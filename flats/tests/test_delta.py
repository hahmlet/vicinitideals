"""The delta: lineage by geometry overlap between two copies of the county map.

A block of a dozen lots does everything a quarter does -- attributes change,
a boundary shifts, a parent splits and keeps its number, another splits and
is renumbered, two merge, one is vacated, one is swallowed, one appears from
nothing, one is renumbered in place, a condo unit is stacked on an unchanged
footprint -- and each case is held to the one row (or pair of rows) the
promotion step will read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flats.ingest import delta
from flats.ingest.delta import (
    Change,
    classify,
    crosscheck,
    iter_features,
    load_lots,
    read_change_log,
    read_changes,
    report,
    run,
    summarize,
    write_changes,
)


def square(x: float, y: float, w: float = 100.0, h: float = 100.0) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]}


def feature(tlid: str, geom: dict[str, Any] | None, *, county: str = "M", landval: float = 1000.0, addr: str = "") -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"TLID": tlid, "COUNTY": county, "LANDVAL": landval, "SITEADDR": addr or f"{tlid} ST"},
        "geometry": geom,
    }


def write(path: Path, features: list[dict[str, Any]], *, pretty: bool = False) -> Path:
    doc = {"type": "FeatureCollection", "srid": 2913, "features": features}
    path.write_text(json.dumps(doc, indent=2 if pretty else None), encoding="utf-8")
    return path


# The block before and after. Coordinates are feet on a 100 ft grid.
BEFORE = [
    feature("A", square(0, 0)),
    feature("B", square(100, 0), landval=1000),
    feature("C", square(200, 0)),
    feature("D", square(300, 0)),
    feature("E", square(400, 0)),
    feature("F", square(500, 0)),
    feature("G", square(600, 0)),
    feature("I", square(700, 0)),
    feature("J", square(800, 0)),
    feature("L", square(900, 0, w=500)),
    feature("N", square(100, 200)),
    feature("P", square(200, 200)),
    feature("R", None),
    feature("T", square(300, 200, w=100)),  # cut into two, with S and U each taking half
    feature("W", square(0, 400), county="W"),
]
AFTER = [
    feature("A", square(0, 0)),  # unchanged, ring reordered below
    feature("B", square(100, 0), landval=2000),  # attributes only
    feature("C", square(200, 0, w=101)),  # a foot wider: reshape
    feature("D", square(300, 0, w=50)),  # split, parent kept its TLID
    feature("D1", square(350, 0, w=50)),
    feature("E1", square(400, 0, w=50)),  # split, parent renumbered
    feature("E2", square(450, 0, w=50)),
    feature("H", square(500, 0, w=200)),  # F + G merged
    # I vacated: nothing stands on (700, 0) now.
    feature("L", square(800, 0, w=600)),  # L grew over J: J absorbed, L the survivor
    feature("S", square(250, 200, w=100)),  # T's ground, split across two lots that reach beyond it:
    feature("U", square(350, 200, w=100)),  # ... T deleted with no one heir, S and U added
    feature("M", square(0, 200)),  # added from nothing
    feature("N2", square(100, 200)),  # N renumbered in place
    feature("N2", square(100, 200)),  # ... and carried twice by the export
    feature("P", square(200, 200)),
    feature("Q", square(200, 200)),  # a unit stacked on P's unchanged footprint
    feature("R", None),
    feature("W", square(0, 400), county="W"),
]
# The same ground with the ring started elsewhere and a wobble in the eighth decimal.
AFTER[0]["geometry"] = {
    "type": "Polygon",
    "coordinates": [[[100, 100], [0, 100.00000001], [0, 0], [100, 0], [100, 100]]],
}

CHANGE_LOG = [
    {"type": "Feature", "properties": {"TLID": t, "ORTAXLOT": f"26 {t}", "ADDCHANGE": ch}, "geometry": None}
    for t, ch in [
        ("D1", "ADDED"), ("E1", "ADDED"), ("E2", "ADDED"), ("H", "ADDED"), ("M", "ADDED"), ("N2", "ADDED"),
        ("Q", "ADDED"), ("S", "ADDED"), ("U", "ADDED"), ("ZZ", "ADDED"),
        ("E", "DELETED"), ("F", "DELETED"), ("G", "DELETED"), ("I", "DELETED"), ("J", "DELETED"), ("N", "DELETED"),
        ("T", "DELETED"),
        ("B", "CHANGE"), ("C", "CHANGE"), ("D", "CHANGE"),
    ]
] + [
    {"type": "Feature", "properties": {"TLID": "1S1W01AA 00100", "ORTAXLOT": "34 1S1W01AA 00100", "ADDCHANGE": "ADDED"}, "geometry": None},
    {"type": "Feature", "properties": {"TLID": "X", "ORTAXLOT": "26 X", "ADDCHANGE": "MOVED"}, "geometry": None},
]


def _block(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "2026-07-28").mkdir()
    (tmp_path / "2026-09-18").mkdir()
    before = write(tmp_path / "2026-07-28" / "rlis_taxlots.geojson", BEFORE)
    after = write(tmp_path / "2026-09-18" / "rlis_taxlots.geojson", AFTER, pretty=True)
    return before, after


def _rows(changes: list[Change]) -> dict[tuple[str, str | None], Change]:
    out = {}
    for c in changes:
        assert (c.tlid, c.role) not in out, f"two rows for {c.tlid} {c.role}"
        out[(c.tlid, c.role)] = c
    return out


# --- loading ----------------------------------------------------------------


def test_features_are_read_one_at_a_time_whichever_way_the_file_was_written(tmp_path: Path) -> None:
    one_line = write(tmp_path / "a.geojson", BEFORE[:3])
    pretty = write(tmp_path / "b.geojson", BEFORE[:3], pretty=True)
    empty = write(tmp_path / "c.geojson", [])

    assert [f["properties"]["TLID"] for f in iter_features(one_line)] == ["A", "B", "C"]
    assert [f["properties"]["TLID"] for f in iter_features(pretty)] == ["A", "B", "C"]
    assert list(iter_features(empty)) == []


def test_lots_are_keyed_by_county_and_tlid_and_other_counties_are_left_out(tmp_path: Path) -> None:
    before, after = _block(tmp_path)

    prev = load_lots(before)
    new = load_lots(after)

    assert all(county == "multnomah" for county, _ in prev)
    assert ("multnomah", "W") not in prev and ("washington", "W") not in prev
    assert len(prev) == 14
    assert len(new) == 16, "the duplicated N2 was kept once"
    assert prev[("multnomah", "R")].geom is None and prev[("multnomah", "R")].area == 0.0
    assert prev[("multnomah", "A")].geom_hash == new[("multnomah", "A")].geom_hash, (
        "a re-started ring with an eighth-decimal wobble is the same ground"
    )
    assert "TLID" not in prev[("multnomah", "A")].props and "COUNTY" not in prev[("multnomah", "A")].props


def test_values_are_spelled_one_way_whichever_export_they_came_from() -> None:
    assert delta._norm(664050.0) == 664050 and delta._norm(664050) == 664050
    assert delta._norm(" R5 ") == "R5"
    assert delta._norm("") is None and delta._norm(None) is None
    assert delta._norm(float("nan")) is None
    assert delta._norm(1.5) == 1.5


# --- classifying ---------------------------------------------------------------


def test_every_kind_of_change_on_one_block(tmp_path: Path) -> None:
    before, after = _block(tmp_path)
    prev, new = load_lots(before), load_lots(after)

    found = classify(prev, new)
    rows = _rows(found.changes)

    assert found.unchanged == 3, "A (re-ordered ring), P and the shapeless R are unchanged"
    assert found.by_kind() == {
        "added": 4,
        "attr_change": 1,
        "deleted": 1,
        "merge": 5,
        "renumbered": 2,
        "reshape": 1,
        "split": 5,
        "vacated": 1,
    }

    b = rows[("B", None)]
    assert b.kind == "attr_change" and b.attr_diff == {"LANDVAL": [1000, 2000]} and b.iou == 1.0

    c = rows[("C", None)]
    assert c.kind == "reshape" and 0.98 < c.iou < 1.0 and c.area_before == 10_000 and c.area_after == 10_100

    d, d1 = rows[("D", "parent")], rows[("D1", "child")]
    assert d.kind == "split" and d.related_tlids == ["D1"] and d.note == "kept its TLID"
    assert d.area_before == 10_000 and d.area_after == 5_000
    assert d1.kind == "split" and d1.related_tlids == ["D"] and d1.area_after == 5_000

    e = rows[("E", "parent")]
    assert e.kind == "split" and e.related_tlids == ["E1", "E2"] and e.area_after is None and e.note == ""
    assert rows[("E1", "child")].related_tlids == ["E"] and rows[("E2", "child")].related_tlids == ["E"]

    h = rows[("H", "survivor")]
    assert h.kind == "merge" and h.related_tlids == ["F", "G"] and h.area_after == 20_000
    assert rows[("F", "parent")].kind == "merge" and rows[("F", "parent")].related_tlids == ["H"]
    assert rows[("G", "parent")].related_tlids == ["H"]

    assert rows[("I", None)].kind == "vacated" and rows[("I", None)].area_before == 10_000

    j, lot_l = rows[("J", "parent")], rows[("L", "survivor")]
    assert j.kind == "merge" and j.related_tlids == ["L"], "a lot swallowed whole by a neighbour was merged, however big the neighbour"
    assert lot_l.kind == "merge" and lot_l.related_tlids == ["J"] and lot_l.note == "kept its TLID"
    assert lot_l.area_before == 50_000 and lot_l.area_after == 60_000 and 0.8 < lot_l.iou < 0.9

    t = rows[("T", None)]
    assert t.kind == "deleted" and sorted(t.related_tlids) == ["S", "U"] and "partial overlap with S (50%), U (50%)" in t.note
    assert rows[("S", None)].kind == "added" and rows[("S", None)].note == "partial overlap with T (50%)"
    assert rows[("U", None)].kind == "added" and rows[("U", None)].note == "partial overlap with T (50%)"

    assert rows[("M", None)].kind == "added" and rows[("M", None)].note == ""
    assert rows[("Q", None)].kind == "added", "a unit stacked on an unchanged footprint descends from nothing"
    assert rows[("Q", None)].note == ""

    n, n2 = rows[("N", "parent")], rows[("N2", "child")]
    assert n.kind == "renumbered" and n.related_tlids == ["N2"]
    assert n2.kind == "renumbered" and n2.related_tlids == ["N"] and n2.attr_diff == {"SITEADDR": ["N ST", "N2 ST"]}

    assert found.only_new == {("multnomah", t) for t in ["D1", "E1", "E2", "H", "M", "N2", "Q", "S", "U"]}
    assert found.only_prev == {("multnomah", t) for t in ["E", "F", "G", "I", "J", "N", "T"]}


def test_a_merge_survivor_that_kept_its_number_is_one_row(tmp_path: Path) -> None:
    before = write(tmp_path / "a.geojson", [feature("K", square(0, 0)), feature("J", square(100, 0))])
    after = write(tmp_path / "b.geojson", [feature("K", square(0, 0, w=200))])

    found = classify(load_lots(before), load_lots(after))
    rows = _rows(found.changes)

    assert found.by_kind() == {"merge": 2}
    k = rows[("K", "survivor")]
    assert k.related_tlids == ["J"] and k.note == "kept its TLID" and k.area_before == 10_000 and k.area_after == 20_000
    assert rows[("J", "parent")].related_tlids == ["K"]


def test_a_sliver_is_not_lineage(tmp_path: Path) -> None:
    # X's new boundary takes a 2 ft strip off its neighbour Y: Y is reshaped,
    # X is reshaped, and neither is anyone's parent.
    before = write(tmp_path / "a.geojson", [feature("X", square(0, 0)), feature("Y", square(100, 0))])
    after = write(tmp_path / "b.geojson", [feature("X", square(0, 0, w=102)), feature("Y", square(102, 0, w=98))])

    found = classify(load_lots(before), load_lots(after))

    assert found.by_kind() == {"reshape": 2}
    assert all(c.related_tlids == [] for c in found.changes)


# --- the cross-check --------------------------------------------------------------


def test_our_diff_is_graded_against_metros_list_per_county(tmp_path: Path) -> None:
    before, after = _block(tmp_path)
    log = write(tmp_path / "rlis_taxlot_change.geojson", CHANGE_LOG)
    found = classify(load_lots(before), load_lots(after))

    check = crosscheck(found, read_change_log(log))

    m = check["counties"]["multnomah"]
    assert m["added"] == {
        "ours": 9, "metro": 10, "both": 9, "recall": 0.9, "precision": 1.0, "metro_only": ["ZZ"], "ours_only": [],
    }
    assert m["deleted"]["recall"] == 1.0 and m["deleted"]["precision"] == 1.0
    assert m["changed_listed"] == 3
    assert check["counties"]["clackamas"]["added"]["recall"] is None, "no rows, no grade"
    assert check["unknown_rows"] == 1, "a row whose ADDCHANGE is not ADDED / DELETED / CHANGE is counted, not guessed"
    assert check["min_recall"] == 0.9 and check["agrees"] is True
    rows = _rows(found.changes)
    assert rows[("D", "parent")].rlis_change == "CHANGE"
    assert rows[("H", "survivor")].rlis_change == "ADDED"
    assert rows[("I", None)].rlis_change == "DELETED"
    assert rows[("L", "survivor")].rlis_change is None, "Metro listed J deleted, not L changed"


def test_disagreement_is_said_not_smoothed(tmp_path: Path) -> None:
    before, after = _block(tmp_path)
    found = classify(load_lots(before), load_lots(after))
    metro = [
        {"TLID": t, "ORTAXLOT": f"26 {t}", "ADDCHANGE": "ADDED"} for t in ["D1", "E1", "AA", "BB", "CC", "DD", "EE"]
    ]

    check = crosscheck(found, metro)

    assert check["counties"]["multnomah"]["added"]["recall"] == round(2 / 7, 3)
    assert check["agrees"] is False


# --- files and the report ---------------------------------------------------------


def test_the_run_writes_the_three_files_and_the_rows_read_back_typed(tmp_path: Path) -> None:
    before, after = _block(tmp_path)
    log = write(tmp_path / "2026-09-18" / "rlis_taxlot_change.geojson", CHANGE_LOG)
    out = tmp_path / "deltas" / "2026-09-18"

    summary = run(before, after, out, change_log=log, log=lambda _s: None)

    assert summary["from"] == "2026-07-28" and summary["to"] == "2026-09-18"
    assert summary["lots_before"] == 14 and summary["lots_after"] == 16 and summary["unchanged"] == 3
    assert summary["rows"] == 20 and summary["rereview"] == 14, "split, merge, renumbered, deleted and vacated rows need a fresh look"
    assert summary["fields_changed"] == {"LANDVAL": 1, "SITEADDR": 1}
    assert summary["crosscheck"]["agrees"] is True
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == summary

    rows = list(read_changes(out / "changes.csv.gz"))
    assert len(rows) == 20
    by_key = {(r["tlid"], r["role"]): r for r in rows}
    assert by_key[("D", "parent")]["related_tlids"] == ["D1"] and by_key[("D", "parent")]["area_after"] == 5000.0
    assert by_key[("B", None)]["attr_diff"] == {"LANDVAL": [1000, 2000]} and by_key[("B", None)]["iou"] == 1.0
    assert by_key[("I", None)]["area_after"] is None and by_key[("I", None)]["rlis_change"] == "DELETED"

    text = (out / "report.md").read_text(encoding="utf-8")
    assert text.startswith("# County map delta: 2026-07-28 -> 2026-09-18")
    assert "| split | 5 | 5 |" in text
    assert "| multnomah | added | 9 | 10 | 9 | 90% | 100% |" in text
    assert "Verdict: the two accounts agree." in text
    assert "- multnomah D -- parent -- with D1 -- 10,000 -> 5,000 sq ft -- Metro says CHANGE -- kept its TLID (D ST)" in text
    assert "- multnomah B -- 10,000 sq ft -- LANDVAL: 1000 -> 2000 -- Metro says CHANGE (B ST)" in text


def test_the_report_says_when_the_accounts_disagree(tmp_path: Path) -> None:
    before, after = _block(tmp_path)
    found = classify(load_lots(before), load_lots(after))
    check = crosscheck(found, [{"TLID": "AA", "ORTAXLOT": "26 AA", "ADDCHANGE": "ADDED"}])

    text = report(found, check, prev_label="July", new_label="September")

    assert "DISAGREE -- a human reads this before anything is promoted" in text
    assert summarize(found, check, prev_label="July", new_label="September")["crosscheck"]["agrees"] is False


def test_changes_round_trip_through_the_csv(tmp_path: Path) -> None:
    changes = [
        Change("clackamas", "22E22B 01800", "split", role="parent", related_tlids=["22E22B 01801", "22E22B 01802"], area_before=8_000.5, iou=None, note="kept its TLID"),
        Change("multnomah", "1N1E08BD  -02500", "attr_change", area_before=1.0, area_after=1.0, iou=1.0, attr_diff={"YEARBUILT": [1978, None]}),
    ]
    path = tmp_path / "changes.csv.gz"

    assert write_changes(changes, path) == 2
    rows = list(read_changes(path))

    assert rows[0]["related_tlids"] == ["22E22B 01801", "22E22B 01802"] and rows[0]["area_after"] is None and rows[0]["iou"] is None
    assert rows[1]["tlid"] == "1N1E08BD  -02500" and rows[1]["attr_diff"] == {"YEARBUILT": [1978, None]}
    assert rows[1]["role"] is None and rows[1]["rlis_change"] is None
