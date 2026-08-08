"""Unit tests for the pure logic in app/scripts/overlay_incidence.py.

Network and DB access live in run()/query_point() and are not exercised here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.scripts.overlay_incidence import (
    ParcelResult,
    is_overlay_candidate,
    normalize_jurisdiction,
    pick_value,
    summarize,
)

pytestmark = pytest.mark.unit


class TestIsOverlayCandidate:
    def test_matches_regulatory_overlay_names(self) -> None:
        for name in [
            "Overlay Districts",
            "Downtown Plan District",
            "Historic Resources",
            "Design Review Corridor",
            "Floodplain",
            "Natural Resource Protection",
            "Riparian Buffer 35ft",
            "Airport Overlay Zone",
        ]:
            assert is_overlay_candidate(name), name

    def test_rejects_cartographic_layers(self) -> None:
        for name in [
            "Taxlot Annotation",
            "Street Labels",
            "Map Grid Index",
            "Aerial Imagery",
            "Address Points",
            # regex hit ("overlay"-free) but excluded terms win
            "Historic Labels",
        ]:
            assert not is_overlay_candidate(name), name

    def test_plain_base_layers_not_matched(self) -> None:
        assert not is_overlay_candidate("City Zoning")
        assert not is_overlay_candidate("Taxlots")


class TestPickValue:
    def test_preferred_field_wins(self) -> None:
        attrs = {"ZONE": "R-4", "Labeling": "CC"}
        assert pick_value(attrs, preferred=("Labeling",)) == "CC"

    def test_falls_back_to_generic_candidates(self) -> None:
        assert pick_value({"ZONECLASS": "LDR-7"}) == "LDR-7"

    def test_case_insensitive(self) -> None:
        assert pick_value({"zone": "CM2"}) == "CM2"

    def test_skips_empty_values(self) -> None:
        attrs = {"ZONE": "", "TYPE": "Wetland 40ft buffer"}
        assert pick_value(attrs) == "Wetland 40ft buffer"

    def test_none_when_nothing_usable(self) -> None:
        assert pick_value({"OBJECTID": 12}) is None


class TestNormalizeJurisdiction:
    def test_known_aliases(self) -> None:
        assert normalize_jurisdiction("City of Portland") == "portland"
        assert normalize_jurisdiction("Unincorporated Multnomah") == "multnomah county"
        assert normalize_jurisdiction("Multnomah") == "multnomah county"

    def test_passthrough_lowercases(self) -> None:
        assert normalize_jurisdiction("  Gresham ") == "gresham"
        assert normalize_jurisdiction(None) == ""


def _parcel(name: str, zone: str, overlays: dict[str, str], price: str | None = None) -> ParcelResult:
    return ParcelResult(
        opportunity_id=name,
        name=name,
        jurisdiction="gresham",
        base_zone=zone,
        base_zone_source="gresham:zoning",
        overlays=overlays,
        asking_price=Decimal(price) if price else None,
        lot_sqft=None,
    )


class TestSummarize:
    def test_groups_identical_combos(self) -> None:
        rows = summarize([
            _parcel("a", "CMR", {"gresham:downtown_plan_district": "DT"}, "1000000"),
            _parcel("b", "CMR", {"gresham:downtown_plan_district": "DT"}, "2500000"),
            _parcel("c", "R4", {}),
        ])
        assert len(rows) == 2
        top = rows[0]
        assert top["parcel_count"] == 2
        assert top["base_zone"] == "CMR"
        assert top["total_asking_price"] == "3500000"
        assert "gresham:downtown_plan_district=DT" in top["overlays"]

    def test_overlay_order_does_not_split_combos(self) -> None:
        rows = summarize([
            _parcel("a", "CMR", {"x": "1", "y": "2"}),
            _parcel("b", "CMR", {"y": "2", "x": "1"}),
        ])
        assert len(rows) == 1
        assert rows[0]["parcel_count"] == 2

    def test_no_overlays_reported_as_none(self) -> None:
        rows = summarize([_parcel("a", "R4", {})])
        assert rows[0]["overlays"] == "(none)"

    def test_missing_zone_reported_as_question_mark(self) -> None:
        rows = summarize([_parcel("a", None, {})])  # type: ignore[arg-type]
        assert rows[0]["base_zone"] == "?"

    def test_empty_input(self) -> None:
        assert summarize([]) == []
