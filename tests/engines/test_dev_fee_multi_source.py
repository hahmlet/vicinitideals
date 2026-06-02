"""Multi-source Developer Fee engine tests.

Covers binding-constraint pipeline, acquisition treatments, custom-Use
inclusion decisions, and Vehicle Type defaults inheritance for the engine
introduced in migration 0103. See docs/feature-plans/developer-fee-multi-
source.md.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.dev_fee import recompute_auto_dev_fee
from app.models.capital import CapitalModule
from app.models.deal import OperationalInputs, UseLine, UseLinePhase
from app.models.source_vehicle import SourceVehicle


def _ul(
    *,
    label: str,
    amount: Decimal,
    cost_category: str = "soft_costs",
    phase: UseLinePhase = UseLinePhase.construction,
    is_auto_dev_fee: bool = False,
    is_auto_acquisition_fee: bool = False,
    dev_fee_pct: Decimal | None = None,
    dev_fee_basis: str | None = None,
    dev_fee_acquisition_treatment: str | None = None,
    dev_fee_acquisition_pct: Decimal | None = None,
    acquisition_fee_pct: Decimal | None = None,
) -> UseLine:
    return UseLine(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        label=label,
        phase=phase,
        amount=amount,
        timing_type="first_day",
        is_deferred=False,
        cost_category=cost_category,
        is_auto_dev_fee=is_auto_dev_fee,
        is_auto_acquisition_fee=is_auto_acquisition_fee,
        dev_fee_pct=dev_fee_pct,
        dev_fee_basis=dev_fee_basis,
        dev_fee_acquisition_treatment=dev_fee_acquisition_treatment,
        dev_fee_acquisition_pct=dev_fee_acquisition_pct,
        acquisition_fee_pct=acquisition_fee_pct,
    )


def _module(
    *,
    label: str,
    vehicle_type: str = "debt",
    equity_role: str | None = None,
    fee_terms: dict | None = None,
    fee_terms_inherited_from_type: bool = False,
    source_vehicle_id: uuid.UUID | None = None,
) -> CapitalModule:
    return CapitalModule(
        id=uuid.uuid4(),
        scenario_id=uuid.uuid4(),
        label=label,
        vehicle_type=vehicle_type,
        equity_role=equity_role,
        fee_terms=fee_terms or {},
        fee_terms_inherited_from_type=fee_terms_inherited_from_type,
        source_vehicle_id=source_vehicle_id,
    )


def _inputs(
    *,
    purchase_price: Decimal | None = None,
    units: int = 100,
) -> OperationalInputs:
    return OperationalInputs(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        unit_count_new=units,
        purchase_price=purchase_price,
    )


# ---------------------------------------------------------------------------
# Binding constraint pipeline.
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_single_vehicle_max_pct_with_basis_exclusion(session):
    """5.5% × (TPC − land) caps the fee."""
    use_lines = [
        _ul(label="Land", amount=Decimal("1000000"), cost_category="acquisition"),
        _ul(label="Hard", amount=Decimal("2000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("10.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    module = _module(
        label="Bond",
        vehicle_type="debt",
        fee_terms={"max_pct": "5.5", "basis_exclusions": ["acquisition"]},
    )
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[module]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    # 5.5% × $2M hard (acquisition excluded) = $110k cap.
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("110000.000")
    assert ctx["binding_source_id"] == str(module.id)
    # Elected $10% × $2M (acquisition excluded under excluded treatment) = $200k.
    assert Decimal(ctx["overage"]) == Decimal("90000.00")


@pytest.mark.unit
async def test_two_vehicles_min_binds(session):
    """Two Vehicles with different caps — strictest binds."""
    use_lines = [
        _ul(label="Hard", amount=Decimal("4000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    # Bond allows up to 5% × $4M = $200k.
    bond = _module(label="Bond", fee_terms={"max_pct": "5.0"})
    # LIHTC allows up to 3% × $4M = $120k. LIHTC binds.
    lihtc = _module(label="LIHTC", fee_terms={"max_pct": "3.0"})
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[bond, lihtc]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    assert ctx["binding_source_id"] == str(lihtc.id)
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("120000.000")


@pytest.mark.unit
async def test_per_unit_cap_caps_fee(session):
    """Vehicle with per_unit_cap=25_000 × 100 units = $2.5M ceiling."""
    use_lines = [
        _ul(label="Hard", amount=Decimal("100000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    hud = _module(label="HUD", fee_terms={"per_unit_cap": "25000"})
    await recompute_auto_dev_fee(
        use_lines, _inputs(units=100), session, modules=[hud]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("2500000")


@pytest.mark.unit
async def test_absolute_cap_caps_fee(session):
    """Vehicle with absolute_cap=$2M ceilings the fee at $2M."""
    use_lines = [
        _ul(label="Hard", amount=Decimal("50000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    mod = _module(label="Private", fee_terms={"absolute_cap": "2000000"})
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[mod]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("2000000")


@pytest.mark.unit
async def test_no_constrained_vehicles_no_binding(session):
    """When no Vehicle has fee_terms set, binding_source_id is None."""
    use_lines = [
        _ul(label="Hard", amount=Decimal("4000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    module = _module(label="No-cap")
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[module]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert auto.dev_fee_binding_context["binding_source_id"] is None
    # No overage when nothing constrains.
    assert Decimal(auto.dev_fee_binding_context["overage"]) == Decimal("0")


# ---------------------------------------------------------------------------
# Elected fee always wins.
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_elected_fee_above_cap_reports_overage(session):
    """User elected % above binding cap — elected wins, overage reported."""
    use_lines = [
        _ul(label="Hard", amount=Decimal("2000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("10.0"),  # $200k elected
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    # Cap at $100k.
    mod = _module(label="Cap", fee_terms={"absolute_cap": "100000"})
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[mod]
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    # Elected fee is still on the UseLine amount.
    assert Decimal(auto.amount) == Decimal("200000")
    # Overage reported.
    assert Decimal(ctx["overage"]) == Decimal("100000")


# ---------------------------------------------------------------------------
# Acquisition treatment variants.
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_excluded_treatment_removes_acquisition_from_basis(session):
    """`excluded` treatment removes acquisition cost_category from Dev Fee basis."""
    use_lines = [
        _ul(label="Land", amount=Decimal("1000000"), cost_category="acquisition"),
        _ul(label="Hard", amount=Decimal("3000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(), session)
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    # 5% × $3M hard (land excluded) = $150k.
    assert Decimal(auto.amount) == Decimal("150000")


@pytest.mark.unit
async def test_split_rate_treatment_partitions_basis(session):
    """`split_rate` treatment: full pct on construction, reduced pct on acquisition."""
    use_lines = [
        _ul(label="Land", amount=Decimal("5000000"), cost_category="acquisition"),
        _ul(label="Hard", amount=Decimal("20000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("4.0"),
            dev_fee_acquisition_treatment="split_rate",
            dev_fee_acquisition_pct=Decimal("1.5"),
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(), session)
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    # 4% × $20M + 1.5% × $5M = $800k + $75k = $875k.
    assert Decimal(auto.amount) == Decimal("875000")


@pytest.mark.unit
async def test_separate_fee_treatment_computes_acquisition_fee_row(session):
    """`separate_fee` treatment uses a parallel auto Acquisition Fee UseLine."""
    acq_row = _ul(
        label="Acquisition Fee",
        amount=Decimal("0"),
        is_auto_acquisition_fee=True,
        acquisition_fee_pct=Decimal("2.0"),
    )
    use_lines = [
        _ul(label="Land", amount=Decimal("8000000"), cost_category="acquisition"),
        _ul(label="Hard", amount=Decimal("15000000"), cost_category="hard_costs"),
        acq_row,
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="separate_fee",
        ),
    ]
    await recompute_auto_dev_fee(
        use_lines, _inputs(purchase_price=Decimal("8000000")), session
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    # Dev Fee: 5% × $15M construction = $750k.
    assert Decimal(auto.amount) == Decimal("750000")
    # Acquisition Fee: 2% × $8M purchase = $160k.
    assert Decimal(acq_row.amount) == Decimal("160000")


@pytest.mark.unit
async def test_legacy_treatment_includes_acquisition_in_basis(session):
    """Treatment=None preserves pre-0103 behavior (includes acquisition)."""
    use_lines = [
        _ul(label="Land", amount=Decimal("1000000"), cost_category="acquisition"),
        _ul(label="Hard", amount=Decimal("3000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment=None,  # legacy
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(), session)
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    # 5% × ($1M + $3M) = $200k under legacy mode.
    assert Decimal(auto.amount) == Decimal("200000")


# ---------------------------------------------------------------------------
# Source Vehicle preset inheritance.
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_inheritance_reads_source_vehicle_preset(session):
    """When ``fee_terms_inherited_from_type=True``, engine reads
    ``fee_terms`` directly from the SourceVehicle preset referenced by
    ``CapitalModule.source_vehicle_id``."""
    from tests.conftest import seed_org
    org, user = await seed_org(session)
    org_id = org.id
    preset = SourceVehicle(
        id=uuid.uuid4(),
        scope="org",
        owner_id=org_id,
        label="LIHTC Bond",
        vehicle_type="debt",
        fee_terms={"max_pct": "4.0"},
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(preset)
    await session.flush()

    use_lines = [
        _ul(label="Hard", amount=Decimal("5000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("8.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    module = _module(
        label="Bond",
        vehicle_type="debt",
        fee_terms={},
        fee_terms_inherited_from_type=True,
        source_vehicle_id=preset.id,
    )
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[module], org_id=org_id
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    # Inherited 4% × $5M hard = $200k cap. 8% elected = $400k overage.
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("200000.000")
    assert Decimal(ctx["overage"]) == Decimal("200000.00")


@pytest.mark.unit
async def test_override_ignores_source_vehicle_preset(session):
    """When ``fee_terms_inherited_from_type=False``, the instance fee_terms
    wins regardless of the linked preset's fee_terms."""
    from tests.conftest import seed_org
    org, user = await seed_org(session)
    org_id = org.id
    preset = SourceVehicle(
        id=uuid.uuid4(),
        scope="org",
        owner_id=org_id,
        label="LIHTC Bond",
        vehicle_type="debt",
        fee_terms={"max_pct": "3.0"},  # Preset: tight cap.
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(preset)
    await session.flush()

    use_lines = [
        _ul(label="Hard", amount=Decimal("1000000"), cost_category="hard_costs"),
        _ul(
            label="Dev Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_acquisition_treatment="excluded",
        ),
    ]
    # Override flag False -> use instance terms only.
    module = _module(
        label="Bond",
        vehicle_type="debt",
        fee_terms={"max_pct": "10.0"},  # Override: loose cap.
        fee_terms_inherited_from_type=False,
        source_vehicle_id=preset.id,
    )
    await recompute_auto_dev_fee(
        use_lines, _inputs(), session, modules=[module], org_id=org_id
    )
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    ctx = auto.dev_fee_binding_context
    # Override 10% × $1M = $100k — instance terms used, preset ignored.
    assert Decimal(ctx["binding_dollar_cap"]) == Decimal("100000.000")
