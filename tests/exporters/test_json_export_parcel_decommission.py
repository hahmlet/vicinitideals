"""JSON deal export sources address/APN/physical attrs from the Opportunity
itself, not from a linked Parcel.

Guards the parcel-intelligence decommission (DC-5c): after the Parcel table is
detached, ``_build_project_payload`` and ``_export_opportunity`` must read
``apn`` / ``address`` / ``lot_sqft`` / ``year_built`` / ``building_sqft`` /
``property_type`` straight off the Opportunity. A regression that re-introduced
``opp.parcel.*`` access would raise once the relationship/table is dropped.
"""
from __future__ import annotations

import pytest

from app.exporters.deal_export import _export_opportunity
from app.exporters.json_export import _build_project_payload
from app.models.opportunity import Opportunity

pytestmark = pytest.mark.unit


def _opp(**kw) -> Opportunity:
    o = Opportunity()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def test_build_project_payload_reads_opportunity_fields():
    opp = _opp(
        name="Test Bldg",
        apn="R123456",
        address_normalized="100 Main St, Gresham, OR 97030",
        lot_sqft=4000,
        year_built=1990,
        gba_sqft=12000,
        property_type="Office",
    )
    payload = _build_project_payload(opp)
    assert payload["ParcelNumber"] == "R123456"
    assert payload["UnparsedAddress"] == "100 Main St, Gresham, OR 97030"
    assert payload["LotSizeSquareFeet"] == 4000
    assert payload["YearBuilt"] == 1990
    assert payload["BuildingAreaTotal"] == 12000
    assert payload["PropertyType"] == "Office"


def test_build_project_payload_handles_none_project():
    payload = _build_project_payload(None)
    assert payload["ParcelNumber"] is None
    assert payload["UnparsedAddress"] is None


def test_build_project_payload_falls_back_to_address_raw():
    opp = _opp(name="X", address_raw="55 Oak Ave")
    payload = _build_project_payload(opp)
    assert payload["UnparsedAddress"] == "55 Oak Ave"


def test_export_opportunity_parcel_block_uses_own_apn():
    opp = _opp(name="Deal", apn="R999", address_normalized="5 Oak Ave")
    out = _export_opportunity(opp)
    assert out["parcels"] == [{"apn": "R999", "address": "5 Oak Ave"}]


def test_export_opportunity_no_apn_yields_no_parcel_block():
    opp = _opp(name="Deal", apn=None)
    out = _export_opportunity(opp)
    assert out["parcels"] == []
