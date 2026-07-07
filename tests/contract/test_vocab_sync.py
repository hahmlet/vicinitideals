"""Cross-surface vocabulary sync guard.

Asserts every surface that enumerates a model vocabulary — Pydantic Literals,
Jinja2 template dropdowns, settings guards/labels, phase-map keys — matches the
canonical constants in ``app/schemas/vocab.py``. If this test fails after you
added an enum value, it is telling you which surface you forgot to update.

All checks here are DB-free (pure imports + template file parsing). The
DB-dependent counterparts (import-template XLSX data validation, settings 400
detail text over HTTP) live in ``tests/api/test_cross_surface_sync_fixes.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from app.schemas import vocab
from app.schemas.vocab import (
    ACTIVE_PHASE_KEYS,
    CARRY_TYPES,
    DAY_COUNTS,
    EQUITY_ROLES,
    PHASE_CARRY_TYPES,
    VEHICLE_TYPES,
    CarryTypeLiteral,
    DayCountLiteral,
    EquityRoleLiteral,
    VehicleTypeLiteral,
)

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "templates"


def _template(rel: str) -> str:
    return (TEMPLATES / rel).read_text(encoding="utf-8")


def _jinja_dict_keys(source: str, var_name: str) -> set[str]:
    """Keys of a ``{% set var = { 'key': 'Label', ... } %}`` literal."""
    m = re.search(re.escape(var_name) + r"\s*=\s*\{(.*?)\}\s*%?\}?", source, re.DOTALL)
    assert m, f"{var_name} dict literal not found"
    return set(re.findall(r"['\"]([a-z_0-9]+)['\"]\s*:", m.group(1)))


def _jinja_list_values(source: str, var_name: str) -> list[str]:
    """Values of a ``{% set var = ['a','b'] %}`` literal."""
    m = re.search(re.escape(var_name) + r"\s*=\s*\[(.*?)\]", source, re.DOTALL)
    assert m, f"{var_name} list literal not found"
    return re.findall(r"['\"]([a-z_0-9]+)['\"]", m.group(1))


def _select_option_values(source: str, select_name: str) -> list[str]:
    """Option values of the ``<select name=...>`` block (static options or
    a ``{% for x in [...] %}`` loop)."""
    m = re.search(
        r'<select[^>]*name="' + re.escape(select_name) + r'"(.*?)</select>',
        source,
        re.DOTALL,
    )
    assert m, f'<select name="{select_name}"> not found'
    block = m.group(1)
    loop = re.search(r"\{%\s*for\s+\w+\s+in\s+\[(.*?)\]", block, re.DOTALL)
    if loop:
        return re.findall(r"['\"]([a-z_0-9]+)['\"]", loop.group(1))
    return re.findall(r'<option value="([a-z_0-9]+)"', block)


# ---------------------------------------------------------------------------
# vocab.py self-consistency: Literal aliases match companion tuples
# ---------------------------------------------------------------------------


def test_literal_aliases_match_tuples():
    assert set(get_args(VehicleTypeLiteral)) == set(VEHICLE_TYPES)
    assert set(get_args(CarryTypeLiteral)) == set(CARRY_TYPES)
    assert set(get_args(DayCountLiteral)) == set(DAY_COUNTS)
    assert set(get_args(EquityRoleLiteral)) == set(EQUITY_ROLES)
    assert PHASE_CARRY_TYPES == CARRY_TYPES + ("converts_to_permanent",)


def test_vehicle_types_has_all_six():
    assert set(VEHICLE_TYPES) == {
        "equity",
        "debt",
        "forgivable_loan",
        "grant",
        "float_earnings",
        "deferred_developer_fee",
    }


# ---------------------------------------------------------------------------
# Pydantic schema Literals derive from vocab
# ---------------------------------------------------------------------------


def _field_literal_args(model, field: str) -> set[str]:
    """String args of a ``Literal[...] | None`` (or bare Literal) annotation."""
    ann = model.model_fields[field].annotation
    args = get_args(ann)
    # Optional unwrap: Literal[...] | None → (Literal[...], NoneType)
    literal_args = {a for a in args if isinstance(a, str)}
    if not literal_args:
        for a in args:
            literal_args |= {x for x in get_args(a) if isinstance(x, str)}
    return literal_args


def test_source_vehicle_schemas_use_canonical_literals():
    from app.schemas.source_vehicle import (
        SourceVehicleCreate,
        SourceVehicleUpdate,
        VehicleCarryConfig,
    )

    for model in (SourceVehicleCreate, SourceVehicleUpdate):
        assert _field_literal_args(model, "vehicle_type") == set(VEHICLE_TYPES)
        assert _field_literal_args(model, "carry_type") == set(CARRY_TYPES)
        assert _field_literal_args(model, "equity_role") == set(EQUITY_ROLES)
        assert _field_literal_args(model, "day_count_convention") == set(DAY_COUNTS)
    assert _field_literal_args(VehicleCarryConfig, "carry_type") == set(CARRY_TYPES)
    assert _field_literal_args(VehicleCarryConfig, "day_count") == set(DAY_COUNTS)


def test_capital_carry_schema_uses_canonical_literals():
    from app.schemas.capital import CapitalCarrySchema

    assert _field_literal_args(CapitalCarrySchema, "carry_type") == set(CARRY_TYPES)
    assert _field_literal_args(CapitalCarrySchema, "day_count") == set(DAY_COUNTS)


# ---------------------------------------------------------------------------
# Settings router guard + labels
# ---------------------------------------------------------------------------


def test_settings_guard_matches_vehicle_types():
    from app.api.routers.settings import _CANONICAL_VEHICLE_TYPES, _VEHICLE_TYPE_ERR

    assert set(_CANONICAL_VEHICLE_TYPES) == set(VEHICLE_TYPES)
    for vt in VEHICLE_TYPES:
        assert vt in _VEHICLE_TYPE_ERR, f"400 detail omits {vt}"


def test_ui_settings_labels_match_vehicle_types():
    from app.api.routers.ui_settings import _VEHICLE_TYPE_LABELS

    assert set(_VEHICLE_TYPE_LABELS) == set(VEHICLE_TYPES)


# ---------------------------------------------------------------------------
# Templates: vehicle-type dropdowns
# ---------------------------------------------------------------------------


def test_vehicle_form_dropdown_matches_vehicle_types():
    src = _template("partials/vehicle_form.html")
    assert set(_select_option_values(src, "vehicle_type")) == set(VEHICLE_TYPES)


def test_settings_templates_vt_labels_match_vehicle_types():
    assert _jinja_dict_keys(_template("settings_user.html"), "_vt_labels") == set(
        VEHICLE_TYPES
    )
    assert _jinja_dict_keys(
        _template("settings_organization.html"), "_vt_labels_org"
    ) == set(VEHICLE_TYPES)


def test_model_builder_all_types_matches_vehicle_types():
    src = _template("partials/model_builder_line_form.html")
    assert set(_jinja_list_values(src, "_ALL_TYPES")) == set(VEHICLE_TYPES)
    # _FT_LABELS carries legacy funder-type labels too, but must at minimum
    # label every canonical vehicle type.
    ft_labels = _jinja_dict_keys(src, "_FT_LABELS")
    assert set(VEHICLE_TYPES) <= ft_labels


# ---------------------------------------------------------------------------
# Templates: carry-type dropdowns
# ---------------------------------------------------------------------------


def test_carry_dropdowns_within_canonical_carry_types():
    src = _template("partials/model_builder_line_form.html")
    constr = set(_select_option_values(src, "construction_carry_type"))
    ops = set(_select_option_values(src, "operation_carry_type"))
    sched = set(_select_option_values(src, "carry_phase_type[]"))

    # Construction (pre-ops) may offer the phase-only converts_to_permanent
    # sentinel; operations and custom-schedule rows must stay flat-canonical.
    assert constr <= set(PHASE_CARRY_TYPES), constr - set(PHASE_CARRY_TYPES)
    assert ops <= set(CARRY_TYPES), ops - set(CARRY_TYPES)
    assert sched <= set(CARRY_TYPES), sched - set(CARRY_TYPES)


# ---------------------------------------------------------------------------
# active_phase_start maps: every consumer key must be canonical
# ---------------------------------------------------------------------------


def test_phase_maps_within_active_phase_keys():
    from app.api.routers.ui_model_builder import _CM_PHASE_TO_MS
    from app.engines.cashflow_compile import _APS_TO_RANK
    from app.services.model_builder_forms.capital_module import _APS_TO_MS

    canonical = set(ACTIVE_PHASE_KEYS)
    for name, mapping in (
        ("_CM_PHASE_TO_MS", _CM_PHASE_TO_MS),
        ("_APS_TO_MS", _APS_TO_MS),
        ("_APS_TO_RANK", _APS_TO_RANK),
    ):
        extra = set(mapping) - canonical
        assert not extra, f"{name} keys not in ACTIVE_PHASE_KEYS: {extra}"


# ---------------------------------------------------------------------------
# Enum-derived tuples stay wired to their ORM enums
# ---------------------------------------------------------------------------


def test_enum_derived_tuples_match_orm_enums():
    from app.models.capital import EquityRole, VehicleType, WaterfallTierType
    from app.models.deal import (
        IncomeStreamType,
        ProjectType,
        UseLinePhase,
        UseLineTiming,
    )
    from app.models.opportunity import OpportunitySource

    pairs = [
        (vocab.VEHICLE_TYPES, VehicleType),
        (vocab.EQUITY_ROLES, EquityRole),
        (vocab.WATERFALL_TIER_TYPES, WaterfallTierType),
        (vocab.USE_LINE_PHASES, UseLinePhase),
        (vocab.USE_LINE_TIMINGS, UseLineTiming),
        (vocab.INCOME_STREAM_TYPES, IncomeStreamType),
        (vocab.PROJECT_TYPES, ProjectType),
        (vocab.OPPORTUNITY_SOURCES, OpportunitySource),
    ]
    for tup, enum_cls in pairs:
        assert tup == tuple(v.value for v in enum_cls)
