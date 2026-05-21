"""Tests for grant cap resolution (source.maximum + per-Use eligibility).

Covers:
  - No eligibility → legacy behavior, amount unchanged
  - Cap < eligible sum → grant.amount = cap
  - Cap > eligible sum → grant.amount = eligible sum (under-utilized)
  - Two grants competing for same Use → stack_position breaks tie
  - Consumption order (phase asc, amount desc)
  - Active From/To derivation from covered Uses
  - grant_is_under_utilized helper
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.engines.grant_caps import grant_is_under_utilized, resolve_grant_caps


@dataclass
class _Use:
    id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("0")
    phase: str = "construction"
    eligible_module_ids: list = field(default_factory=list)


@dataclass
class _Module:
    id: UUID = field(default_factory=uuid4)
    stack_position: int = 0
    source: dict = field(default_factory=dict)
    active_phase_start: str | None = None
    active_phase_end: str | None = None


class _FakeSession:
    """Minimal AsyncSession stand-in: ignores execute / flush calls."""

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    async def flush(self) -> None:
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_maximum_leaves_amount_untouched() -> None:
    grant = _Module(source={"amount": "200000"})
    use = _Use(amount=Decimal("100000"))
    await resolve_grant_caps([grant], [use], _FakeSession())
    assert grant.source["amount"] == "200000"
    assert "maximum" not in grant.source


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cap_under_eligible_sum_amount_equals_cap() -> None:
    grant = _Module(source={"maximum": Decimal("250000")})
    u1 = _Use(amount=Decimal("300000"), eligible_module_ids=[grant.id])
    u2 = _Use(amount=Decimal("200000"), eligible_module_ids=[grant.id])
    await resolve_grant_caps([grant], [u1, u2], _FakeSession())
    assert grant.source["amount"] == Decimal("250000")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cap_over_eligible_sum_amount_equals_eligible_sum() -> None:
    grant = _Module(source={"maximum": Decimal("250000")})
    u = _Use(amount=Decimal("180000"), eligible_module_ids=[grant.id])
    await resolve_grant_caps([grant], [u], _FakeSession())
    assert grant.source["amount"] == Decimal("180000")
    assert grant_is_under_utilized(grant)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_grants_stack_position_wins_against_same_use() -> None:
    grant_a = _Module(stack_position=1, source={"maximum": Decimal("250000")})
    grant_b = _Module(stack_position=2, source={"maximum": Decimal("250000")})
    use = _Use(
        amount=Decimal("200000"),
        eligible_module_ids=[grant_a.id, grant_b.id],
    )
    await resolve_grant_caps([grant_a, grant_b], [use], _FakeSession())
    assert grant_a.source["amount"] == Decimal("200000")
    assert grant_b.source["amount"] == Decimal("0")
    assert grant_is_under_utilized(grant_b)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consumption_order_phase_asc_amount_desc() -> None:
    grant = _Module(source={"maximum": Decimal("250000")})
    # Both Uses in same phase — larger consumed first
    u_small = _Use(
        amount=Decimal("200000"),
        phase="construction",
        eligible_module_ids=[grant.id],
    )
    u_large = _Use(
        amount=Decimal("300000"),
        phase="construction",
        eligible_module_ids=[grant.id],
    )
    await resolve_grant_caps([grant], [u_small, u_large], _FakeSession())
    # Cap fills entirely from u_large (300k cap room → 250k taken)
    # Active From/To both point at u_large's phase
    assert grant.source["amount"] == Decimal("250000")
    assert grant.active_phase_start == "construction"
    assert grant.active_phase_end == "construction"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consumption_order_earlier_phase_first() -> None:
    grant = _Module(source={"maximum": Decimal("450000")})
    u_constr = _Use(
        amount=Decimal("200000"),
        phase="construction",
        eligible_module_ids=[grant.id],
    )
    u_acq = _Use(
        amount=Decimal("300000"),
        phase="acquisition",
        eligible_module_ids=[grant.id],
    )
    await resolve_grant_caps([grant], [u_constr, u_acq], _FakeSession())
    # acquisition (rank 1) consumed before construction (rank 2)
    # cap 450k = 300k acq + 150k constr
    assert grant.source["amount"] == Decimal("450000")
    assert grant.active_phase_start == "acquisition"
    assert grant.active_phase_end == "construction"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_phase_caps_at_cap_consumption() -> None:
    grant = _Module(source={"maximum": Decimal("200000")})
    u_acq = _Use(
        amount=Decimal("300000"),
        phase="acquisition",
        eligible_module_ids=[grant.id],
    )
    u_constr = _Use(
        amount=Decimal("200000"),
        phase="construction",
        eligible_module_ids=[grant.id],
    )
    await resolve_grant_caps([grant], [u_acq, u_constr], _FakeSession())
    # Cap (200k) fully consumed by u_acq alone — construction never touched
    assert grant.source["amount"] == Decimal("200000")
    assert grant.active_phase_start == "acquisition"
    assert grant.active_phase_end == "acquisition"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_eligible_uses_grant_contributes_zero() -> None:
    grant = _Module(source={"maximum": Decimal("250000")})
    use = _Use(amount=Decimal("100000"))  # no eligibility
    await resolve_grant_caps([grant], [use], _FakeSession())
    assert grant.source["amount"] == Decimal("0")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zero_dollar_use_does_not_consume_cap() -> None:
    grant = _Module(source={"maximum": Decimal("250000")})
    zero_use = _Use(amount=Decimal("0"), eligible_module_ids=[grant.id])
    real_use = _Use(amount=Decimal("180000"), eligible_module_ids=[grant.id])
    await resolve_grant_caps([grant], [zero_use, real_use], _FakeSession())
    assert grant.source["amount"] == Decimal("180000")


@pytest.mark.unit
def test_grant_is_under_utilized_false_without_maximum() -> None:
    g = _Module(source={"amount": "100000"})
    assert grant_is_under_utilized(g) is False


@pytest.mark.unit
def test_grant_is_under_utilized_true_when_amount_below_max() -> None:
    g = _Module(source={"maximum": Decimal("250000"), "amount": Decimal("180000")})
    assert grant_is_under_utilized(g) is True


@pytest.mark.unit
def test_grant_is_under_utilized_false_when_fully_funded() -> None:
    g = _Module(source={"maximum": Decimal("250000"), "amount": Decimal("250000")})
    assert grant_is_under_utilized(g) is False
