"""FD6 foundation model, slice 3: the stored record and the lot report's block.

The measured record is stored as one document and priced at read time with the
settings of the moment; a record measured under other geometric settings is never
priced ("needs re-measuring"); the old-building figure never enters a cost; the
bulk re-price reads the same records.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from flats.foundation import ground as grounds
from flats.foundation import lot, measure, oldbuild, record, report, reprice, rows, settings

S = settings.load()
VERSION = record.settings_version()
DRAWING = "test drawings"
WHEN = "2026-11-19T12:00:00+00:00"
INPUTS = {"ground_class": "FIRM", "frost_register_in": 12.0, "year_built": 1925, "relief_input_ft": 3.0}


def _measured(along: float = 3.0, across: float = 1.0, *, old: bool = True, tlid: str = "1S2E08BA  -09500") -> measure.Measured:
    m = measure.measure(grounds.plane(S, along, across), S, tlid=tlid, county="multnomah", inputs=INPUTS)
    box = oldbuild.Outline(((((30.0, -5.0), (55.0, -5.0), (55.0, 12.0), (30.0, 12.0), (30.0, -5.0))),), "B1", 1925)
    return measure.with_old_buildings(m, True, oldbuild.measure_all([box], S) if old else ())


def _doc(m: measure.Measured | None = None) -> dict:
    return record.document(m or _measured(), drawing=DRAWING, measured_at=WHEN)


def _yaml_with(tmp_path: Path, old: str, new: str) -> Path:
    text = settings.PATH.read_text(encoding="utf-8")
    assert old in text
    p = tmp_path / "foundation.yaml"
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return p


# ---------------------------------------------------------------- the stored record


def test_a_document_round_trips_and_prices_the_same() -> None:
    m = _measured()
    doc = json.loads(json.dumps(_doc(m)))  # through JSON, as the JSONB column holds it
    back = record.measured_of(doc)
    assert rows.measured_rows(back) == rows.measured_rows(m)
    assert rows.old_building_rows(back) == rows.old_building_rows(m)
    assert rows.assessed_rows(lot.assess(back, S)) == rows.assessed_rows(lot.assess(m, S))
    assert doc["measured_on"] == {"drawing": DRAWING, "ground_source": "plane", "cell_m": None, "measured_at": WHEN}
    assert doc["geometry_hash"] == record.settings_hash(S)
    # Nothing priced is stored.
    assert "cost" not in json.dumps(doc)


def test_the_flat_tables_and_the_jsonl_give_back_the_same_documents(tmp_path: Path) -> None:
    docs = [_doc(_measured(tlid="A  -1")), _doc(_measured(1.0, 0.0, old=False, tlid="B  -2"))]
    tables: dict[str, list[dict]] = {name: [] for name in record.TABLES}
    for d in docs:
        for name, recs in record.table_rows(d).items():
            tables[name].extend(recs)
    assert [json.loads(json.dumps(d)) for d in record.documents_from_tables(tables)] == [json.loads(json.dumps(d)) for d in docs]
    path = tmp_path / "records.jsonl.gz"
    assert record.write_jsonl(path, docs) == 2
    assert list(record.read_jsonl(path)) == [json.loads(json.dumps(d)) for d in docs]


def test_a_record_under_other_geometric_settings_is_stale() -> None:
    doc = _doc()
    assert record.staleness(doc, S) is None
    assert record.staleness(doc, S.replace(grow_ft=4.0)) == ("grow_ft",)
    assert record.staleness(doc, S.replace(length_ft=81.0)) == ("length_ft",)
    assert record.staleness({**doc, "record_version": 99}, S) == ("record_version",)


# ---------------------------------------------------------------- read-time pricing


def test_the_block_is_priced_at_read_time() -> None:
    block = report.describe(_doc(), S, version=VERSION)
    assert block["status"] == report.PRICED and block["never_a_colour"] is True
    assert block["settings_version"] == VERSION
    res = lot.assess(_measured(), S)
    methods = {m["method"]: m for m in block["methods"]}
    assert list(methods) == ["A dry", "A wet", "B"]  # slab first, then the raised floor
    for name, m in methods.items():
        assert isinstance(m["cost_low"], str) and isinstance(m["cost_high"], str)
        assert Decimal(m["cost_low"]) == res[name].cost.low.quantize(Decimal("0.01"))
        assert Decimal(m["cost_high"]) == res[name].cost.high.quantize(Decimal("0.01"))
        # the cost lines add up to the cost (to the cent per line)
        assert abs(sum(Decimal(ln["low"]) for ln in m["cost_lines"]) - Decimal(m["cost_low"])) <= Decimal("0.01") * len(m["cost_lines"])
        assert len(m["doors"]) == 8 and m["risers_total"] == sum(d["steps"] for d in m["doors"])
        assert m["steps_words"].startswith(f"Steps at the 8 doors: {m['risers_least']} to {m['risers_most']}")
    assert {c["against"] for c in block["cheaper"]} == {"A dry", "A wet"}
    assert all(isinstance(c["by"], str) for c in block["cheaper"])
    assert block["cheaper_words"].startswith("Cheaper: ")
    assert "slab on fill" in block["style"]["words"] and "(A)" not in block["style"]["words"]
    assert {i["code"] for i in block["challenges"]} >= {"wall_over_old_building"}


def test_the_old_building_figure_is_never_in_a_cost() -> None:
    with_old = report.describe(_doc(_measured()), S, version=VERSION)
    without = report.describe(_doc(_measured(old=False)), S, version=VERSION)
    assert [(m["cost_low"], m["cost_high"]) for m in with_old["methods"]] == [
        (m["cost_low"], m["cost_high"]) for m in without["methods"]
    ]
    old = with_old["old_buildings"]
    assert old["in_total"] is False and old["count"] == 1 and old["wall_crossed"]
    assert Decimal(old["if_basement"]["B"]["low"]) > 0 and Decimal(old["if_basement"]["A"]["high"]) > 0
    assert Decimal(old["weighted"]["B"]["low"]) == (
        Decimal(old["if_basement"]["B"]["low"]) * Decimal(str(old["basement_share"]))
    ).quantize(Decimal("0.01"))
    assert old["if_basement_words"].startswith("If a mapped building here had a basement:")
    assert "Not in the cost ranges above" in old["if_basement_words"]
    assert old["weighted_words"].startswith("Weighted by how often a house built 1925 had a basement (80%)")
    assert "mapped building" in old["words"] and "house" in old["words"]
    assert without["old_buildings"]["words"] == "No mapped building stands under the pod."


def test_a_stale_record_shows_no_figure() -> None:
    block = report.describe(_doc(), S.replace(grow_ft=4.0), version=VERSION)
    assert block["status"] == report.NEEDS_REMEASURING
    assert block["remeasure_because"] == ["grow_ft"]
    assert block["status_words"].startswith("Needs re-measuring")
    for key in ("methods", "cheaper", "old_buildings", "challenges", "style"):
        assert key not in block
    broken = report.describe({**_doc(), "lines": [{"line": "front"}]}, S, version=VERSION)
    assert broken["status"] == report.NEEDS_REMEASURING and broken["remeasure_because"] == ["record"]


def test_a_price_change_reprices_without_a_re_measure(tmp_path: Path) -> None:
    doc = _doc()
    before = report.describe(doc, S, version=VERSION)
    p = _yaml_with(tmp_path, "  concrete_yd3:\n    low: 160\n    high: 220", "  concrete_yd3:\n    low: 500\n    high: 600")
    s2 = settings.load(p)
    after = report.describe(doc, s2, version=record.settings_version(p))
    assert after["status"] == report.PRICED and after["settings_version"] != VERSION
    assert Decimal(after["methods"][-1]["cost_high"]) > Decimal(before["methods"][-1]["cost_high"])


# ---------------------------------------------------------------- bulk re-price


def test_reprice_writes_one_flat_row_per_lot(tmp_path: Path) -> None:
    docs = [_doc(_measured(tlid="A  -1")), _doc(_measured(tlid="B  -2"))]
    stale = json.loads(json.dumps(docs[1]))
    geometry = json.loads(stale["lot"]["geometry"])
    geometry["grow_ft"] = 9.0
    stale["lot"]["geometry"] = json.dumps(geometry)
    path = tmp_path / "records.jsonl.gz"
    record.write_jsonl(path, [docs[0], stale])
    table = reprice.reprice(reprice.documents(path), S, VERSION)
    assert [(r["tlid"], r["status"]) for r in table] == [("A  -1", report.PRICED), ("B  -2", report.NEEDS_REMEASURING)]
    priced = table[0]
    assert priced["county"] == "multnomah" and priced["settings_version"] == VERSION
    assert priced["drawing"] == DRAWING and priced["style_words"] and priced["challenges"]
    assert priced["b_cost_low"] == rows.assessed_rows(lot.assess(_measured(tlid="A  -1"), S))[0]["b_cost_low"]
    assert table[1]["remeasure_because"] == "grow_ft" and "b_cost_low" not in table[1]
    out = tmp_path / "priced.csv"
    reprice.write(out, table)
    with out.open(newline="", encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert [r["tlid"] for r in got] == ["A  -1", "B  -2"]  # the TLID's spaces kept


@pytest.mark.parametrize("inches,words", [(8, "8 in"), (12, "1 ft"), (50, "4 ft 2 in"), (0.4, "0 in")])
def test_feet_and_inches(inches: float, words: str) -> None:
    assert report.ft_in(inches) == words
