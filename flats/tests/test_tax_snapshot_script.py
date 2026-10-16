"""Pure-function tests for scripts/flats_tax_snapshot.py (no DB, no network)."""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "flats_tax_snapshot.py"


@pytest.fixture(scope="module")
def ts():
    spec = importlib.util.spec_from_file_location("flats_tax_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("raw", [None, "", "abc", "1,000", "NaN-ish"])
def test_dec_blank_or_invalid_is_none(ts, raw):
    assert ts._dec(raw) is None


@pytest.mark.parametrize(
    ("raw", "want"),
    [("123.45", Decimal("123.45")), (7, Decimal("7")), (Decimal("2.5"), Decimal("2.5")), (0, Decimal("0"))],
)
def test_dec_valid(ts, raw, want):
    assert ts._dec(raw) == want


def test_read_taxcodes_with_release_header(ts, tmp_path):
    p = tmp_path / "tc.csv"
    p.write_text(
        "# RLIS release 2026-07, http://example.test/x.zip\n"
        "TLID,TAXCODE,ASSESSVAL\n"
        " 1N1E01 100 ,001,150000\n"
        "1N1E01 200,002,\n",
        encoding="utf-8",
    )
    rows, header = ts.read_taxcodes(p)
    assert header == "RLIS release 2026-07, http://example.test/x.zip"
    assert set(rows) == {"1N1E01 100", "1N1E01 200"}
    assert rows["1N1E01 100"]["TAXCODE"] == "001"
    assert rows["1N1E01 200"]["ASSESSVAL"] == ""


def test_read_taxcodes_without_header(ts, tmp_path):
    p = tmp_path / "tc.csv"
    p.write_text("TLID,TAXCODE\nA1,010\n", encoding="utf-8")
    rows, header = ts.read_taxcodes(p)
    assert header == ""
    assert rows == {"A1": {"TLID": "A1", "TAXCODE": "010"}}


def test_roll_complete(ts):
    roll = ts._roll(
        {"land_value": "100000.4", "building_value": 200000, "total_value": "300000.5", "assessed_value": "250000"}
    )
    assert (roll.land_value, roll.building_value, roll.total_value, roll.assessed_value) == (
        Decimal("100000"),
        Decimal("200000"),
        Decimal("300001"),
        Decimal("250000"),
    )


@pytest.mark.parametrize("missing", ["land_value", "building_value", "total_value", "assessed_value"])
def test_roll_missing_or_blank_field_is_none(ts, missing):
    a = {"land_value": 1, "building_value": 2, "total_value": 3, "assessed_value": 4}
    assert ts._roll({**a, missing: ""}) is None
    del a[missing]
    assert ts._roll(a) is None


def test_roll_empty(ts):
    assert ts._roll({}) is None


def test_flat(ts):
    assert ts._flat({}) == ""
    assert ts._flat({"taxcode": "tlid_not_in_taxcode_file"}) == "taxcode=tlid_not_in_taxcode_file"
    assert ts._flat({"a": 1, "b": None}) == "a=1; b=None"
