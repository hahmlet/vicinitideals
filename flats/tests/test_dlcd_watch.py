"""Offline tests for the DLCD weekly notice watch."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.watch.dlcd import (
    LEDGER_KEYS,
    load_jurisdictions,
    load_ledger,
    new_notices,
    parse,
    render_markdown,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dlcd_adopted.csv"
PROPOSED_FIXTURE = Path(__file__).parent / "fixtures" / "dlcd_proposed.csv"


def _ledger_entry(notice_id: str, **overrides: str | None) -> dict[str, str | None]:
    entry: dict[str, str | None] = {
        "id": notice_id,
        "kind": "adopted",
        "jurisdiction": "or/clackamas/_unincorporated",
        "received": "2026-08-11",
        "read_on": "2026-10-15",
        "read_by": "test",
        "verdict": "no_effect",
        "note": None,
        "followup": None,
    }
    entry.update(overrides)
    return entry


def test_parse_skips_boilerplate_and_retains_csv_fields_and_multiline_cells():
    notices = parse(FIXTURE)

    assert len(notices) == 4
    portland = next(notice for notice in notices if notice.jurisdiction == "City of Portland")
    assert portland.kind == "adopted"
    assert portland.received == "August 25, 2026"
    assert portland.local_file_number == "RICAP 11"
    assert portland.dlcd_file_number == "001-26"
    assert portland.local_phone == "503-823-6046"
    assert portland.local_email == "jason.mcneil@portlandoregon.gov"
    assert "parking, exterior areas, and regulatory improvement" in portland.summary

    beaverton = next(
        notice for notice in notices if notice.jurisdiction == "City of Beaverton"
    )
    assert "\n\n" in beaverton.summary
    assert beaverton.other_fields == ()


def test_jurisdiction_mapping_covers_city_and_county_and_drops_unknowns():
    jurisdictions = load_jurisdictions()
    assert len(jurisdictions) == 55
    assert jurisdictions["City of Portland"] == "or/multnomah/portland"
    assert jurisdictions["Portland"] == "or/multnomah/portland"
    assert jurisdictions["Clackamas County"] == "or/clackamas/_unincorporated"
    config_root = Path(__file__).parents[2] / "flats" / "config" / "jurisdictions"
    assert all(
        (config_root / f"{slug}.yaml").is_file()
        for slug in set(jurisdictions.values())
    )

    notices = parse(FIXTURE)
    kept = new_notices(notices, [])
    assert [notice.jurisdiction for notice in kept] == [
        "Clackamas County",
        "City of Portland",
        "City of Beaverton",
    ]
    assert all(notice.jurisdiction != "City of Albany" for notice in kept)


def test_proposed_export_retains_plain_city_names_and_hearing_dates():
    notice = parse(PROPOSED_FIXTURE)[0]

    assert notice.kind == "proposed"
    assert notice.jurisdiction == "Happy Valley"
    assert notice.local_file_number == "LU-0028-2025"
    assert notice.first_hearing_date == "November 10, 2026"
    assert notice.final_hearing_date == "November 10, 2026"
    assert ("RegionalRepresentitive", "Kelly Reid") in notice.other_fields
    assert new_notices([notice], []) == [notice]


def test_ledger_diff_suppresses_reviewed_notice_and_orders_oldest_first():
    notices = parse(FIXTURE)
    county = next(notice for notice in notices if notice.jurisdiction == "Clackamas County")

    fresh = new_notices(notices, [_ledger_entry(county.id)])

    assert [notice.jurisdiction for notice in fresh] == [
        "City of Portland",
        "City of Beaverton",
    ]


def test_committed_ledger_is_valid_and_encodes_name_a_followup():
    ledger = load_ledger()
    for entry in ledger:
        if entry["verdict"] == "encode":
            assert entry["kind"] == "adopted", entry["id"]
            assert entry["note"] and entry["followup"], entry["id"]


def test_ledger_loader_accepts_unquoted_yaml_dates(tmp_path):
    path = tmp_path / "ledger.yaml"
    path.write_text(
        "- id: adopted:Portland:001-26\n"
        "  kind: adopted\n"
        "  jurisdiction: or/multnomah/portland\n"
        "  received: 2026-08-25\n"
        "  read_on: 2026-10-15\n"
        "  read_by: test\n"
        "  verdict: watch\n"
        "  note: null\n"
        "  followup: null\n",
        encoding="utf-8",
    )

    entry = load_ledger(path)[0]

    assert entry["received"] == "2026-08-25"
    assert entry["read_on"] == "2026-10-15"


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([_ledger_entry("x", extra="not allowed")], "unknown keys"),
        ([_ledger_entry("x", verdict="maybe")], "invalid verdict"),
        (
            [_ledger_entry("x"), _ledger_entry("x")],
            "Duplicate ledger id",
        ),
    ],
)
def test_ledger_loader_rejects_invalid_entries(tmp_path, entries, message):
    path = tmp_path / "ledger.yaml"
    path.write_text(yaml.safe_dump(entries), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_ledger(path)


def test_ledger_schema_has_exactly_the_documented_keys():
    assert LEDGER_KEYS == {
        "id",
        "kind",
        "jurisdiction",
        "received",
        "read_on",
        "read_by",
        "verdict",
        "note",
        "followup",
    }


def test_markdown_includes_every_new_notice_summary_and_links():
    notices = new_notices(parse(FIXTURE), [])
    markdown = render_markdown(notices)

    for notice in notices:
        assert notice.summary in markdown
        assert notice.summary2 in markdown
        assert notice.link in markdown
    assert "`or/clackamas/_unincorporated`" in markdown
    assert "`or/multnomah/portland`" in markdown
