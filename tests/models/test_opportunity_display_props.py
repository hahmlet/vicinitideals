"""Opportunity ``display_*`` accessors read its own columns, never a Parcel.

Regression guard for the parcel decommission (DC-5c). The ``display_*`` properties
previously fell back to ``self.parcel.<attr>`` when the Opportunity's own column was
NULL. On an async session without the parcel relationship eager-loaded, that lazy
load raised ``MissingGreenlet`` and 500'd the ``/ui/opportunities/rows/deals``
partial for manual deals (units/sqft = NULL). The parcel relationship and the
``effective_*`` fallback methods were removed entirely in DC-5c-drop.

These tests use transient ``Opportunity()`` instances with no DB session, so any
residual ``self.parcel`` access would raise instead of returning ``None``.
"""
from __future__ import annotations

import pytest

from app.models.opportunity import Opportunity

pytestmark = pytest.mark.unit


def _opp(**kw) -> Opportunity:
    o = Opportunity()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def test_display_props_return_own_columns_when_set():
    opp = _opp(units=12, gba_sqft=8000, year_built=1995, lot_sqft=4000, property_type="Office")
    assert opp.display_units == 12
    assert opp.display_sqft == 8000
    assert opp.display_year_built == 1995
    assert opp.display_lot_sqft == 4000
    assert opp.display_property_type == "Office"


def test_display_props_return_none_when_unset_without_touching_parcel():
    # All own columns NULL — must return None, NOT lazy-load self.parcel and crash.
    opp = _opp()
    assert opp.display_units is None
    assert opp.display_sqft is None
    assert opp.display_year_built is None
    assert opp.display_lot_sqft is None
    assert opp.display_property_type is None
