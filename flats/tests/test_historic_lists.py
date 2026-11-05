from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[2]
HISTORIC_DIR = ROOT / "flats" / "config" / "historic"
CSV_COLUMNS = (
    "tlid",
    "address_listed",
    "name",
    "listing_id_or_row",
    "source",
    "match_method",
    "match_note",
)
MATCH_METHODS = {"address-exact", "address-fuzzy", "point-in-lot", "none"}


def _historic_rows() -> list[tuple[Path, list[dict[str, str]]]]:
    files = sorted(HISTORIC_DIR.glob("*.csv"))
    assert files
    result = []
    for path in files:
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            assert tuple(reader.fieldnames or ()) == CSV_COLUMNS
            rows = list(reader)
        assert all(row["source"] for row in rows)
        assert all(row["match_method"] in MATCH_METHODS for row in rows)
        result.append((path, rows))
    return result


def test_historic_list_csvs_parse_with_expected_columns() -> None:
    _historic_rows()


def test_nonempty_historic_tlids_exist_in_available_lot_data() -> None:
    local_candidates = (
        ROOT / "data" / "quadfit" / "s1_lots.parquet",
        ROOT.parent.parent / "vicinitideals" / "data" / "quadfit" / "s1_lots.parquet",
    )
    lot_data = next((path for path in local_candidates if path.is_file()), None)
    if lot_data is None:
        pytest.skip("local s1_lots.parquet data is not present in CI")

    lot_ids = {
        re.sub(r"[\s-]", "", str(tlid))
        for tlid in pd.read_parquet(lot_data, columns=["TLID"])["TLID"]
    }
    listed_ids = {
        re.sub(r"[\s-]", "", row["tlid"])
        for _, rows in _historic_rows()
        for row in rows
        if row["tlid"]
    }
    assert listed_ids <= lot_ids
