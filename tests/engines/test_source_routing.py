from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.engines.source_routing import eligible_sources_for_use, route_use_to_sources


@dataclass
class _Use:
    eligible_module_ids: list = field(default_factory=list)
    cost_category: str = ""


@dataclass
class _Module:
    id: UUID = field(default_factory=uuid4)
    stack_position: int = 0
    eligible_use_tags: list = field(default_factory=list)


@pytest.mark.unit
def test_permissive_both_empty_returns_all_modules() -> None:
    use = _Use()
    mods = [_Module(), _Module(), _Module()]
    result = eligible_sources_for_use(use, mods)
    assert result == mods


@pytest.mark.unit
def test_use_level_whitelist_returns_only_specified_modules() -> None:
    m1 = _Module()
    m2 = _Module()
    m3 = _Module()
    use = _Use(eligible_module_ids=[m1.id, m3.id])
    result = eligible_sources_for_use(use, [m1, m2, m3])
    assert m1 in result
    assert m3 in result
    assert m2 not in result
    assert len(result) == 2


@pytest.mark.unit
def test_module_tag_whitelist_matches_on_cost_category() -> None:
    m_land = _Module(eligible_use_tags=["land"])
    m_hard = _Module(eligible_use_tags=["hard_costs"])
    m_open = _Module()
    use = _Use(cost_category="land")
    result = eligible_sources_for_use(use, [m_land, m_hard, m_open])
    assert m_land in result
    assert m_hard not in result


@pytest.mark.unit
def test_module_tags_present_use_has_no_category_is_permissive_for_that_use() -> None:
    m_tagged = _Module(eligible_use_tags=["hard_costs"])
    use = _Use(cost_category="")
    result = eligible_sources_for_use(use, [m_tagged])
    assert m_tagged in result


@pytest.mark.unit
def test_no_eligible_matches_falls_back_to_all_modules() -> None:
    m1 = _Module(eligible_use_tags=["land"])
    m2 = _Module(eligible_use_tags=["hard_costs"])
    use = _Use(cost_category="soft_costs")
    result = eligible_sources_for_use(use, [m1, m2])
    assert result == [m1, m2]


@pytest.mark.unit
def test_route_use_to_sources_returns_stable_order_by_stack_position_then_id() -> None:
    id_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    id_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    id_c = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    m_pos2_a = _Module(id=id_a, stack_position=2)
    m_pos1_b = _Module(id=id_b, stack_position=1)
    m_pos2_c = _Module(id=id_c, stack_position=2)
    use = _Use()
    result = route_use_to_sources(use, [m_pos2_a, m_pos1_b, m_pos2_c])
    assert result[0] is m_pos1_b
    assert result[1] is m_pos2_a
    assert result[2] is m_pos2_c


@pytest.mark.unit
def test_route_use_to_sources_empty_eligible_ids_returns_all_sorted_by_stack_position() -> None:
    m3 = _Module(stack_position=3)
    m1 = _Module(stack_position=1)
    m2 = _Module(stack_position=2)
    use = _Use()
    result = route_use_to_sources(use, [m3, m1, m2])
    positions = [m.stack_position for m in result]
    assert positions == [1, 2, 3]
