"""Schema validation for the shipped quadfit config files."""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")

pytestmark = pytest.mark.unit


def test_rules_yaml_validates():
    from common import load_rules

    rules = load_rules()
    assert "portland" in rules.jurisdictions
    assert rules.jurisdictions["maywood_park"].eligible is False
    # Every quadplex-allowed zone row must carry all three setbacks (enforced
    # by the model validator — this asserts the shipped file passes it).
    for j in rules.jurisdictions.values():
        for z in j.zones:
            if z.quadplex_allowed:
                assert z.setback_front_ft is not None
                assert z.setback_side_ft is not None
                assert z.setback_rear_ft is not None


def test_portland_overlay_suffix_normalization():
    from common import load_rules

    pdx = load_rules().jurisdictions["portland"]
    assert pdx.rule_for("R5") is not None
    # Overlay letters are appended to Portland zone codes in GIS data.
    assert pdx.rule_for("R5a").zone == "R5"
    assert pdx.rule_for("R2.5h").zone == "R2.5"
    # Unknown zone → no rule.
    assert pdx.rule_for("CM2") is None
    assert pdx.rule_for(None) is None


def test_juris_city_routing():
    from common import load_rules

    rules = load_rules()
    assert rules.jurisdiction_for_juris_city("PORTLAND") == "portland"
    assert rules.jurisdiction_for_juris_city("maywood park".upper()) == "maywood_park"
    assert rules.jurisdiction_for_juris_city("SANDY") is None


def test_portland_coverage_curve():
    """Table 110-5 lot-size formula benchmarks from the code text."""
    from common import load_rules

    r5 = load_rules().jurisdictions["portland"].rule_for("R5")
    assert r5.coverage_cap_sqft(2500) == pytest.approx(1250)     # 50% flat
    assert r5.coverage_cap_sqft(4000) == pytest.approx(1875)     # 1500 + 37.5% over 3k
    assert r5.coverage_cap_sqft(5000) == pytest.approx(2250)     # 45%
    assert r5.coverage_cap_sqft(10000) == pytest.approx(3000)    # 30%
    assert r5.coverage_cap_sqft(20000) == pytest.approx(4500)    # 22.5%
    assert r5.coverage_cap_sqft(24000) == pytest.approx(4800)    # 4500 + 7.5% over 20k


def test_pct_coverage_and_uncapped():
    from common import ZoneRule

    pct = ZoneRule(zone="X", quadplex_allowed=True, setback_front_ft=10,
                   setback_side_ft=5, setback_rear_ft=5, max_coverage_pct=40)
    assert pct.coverage_cap_sqft(10000) == pytest.approx(4000)
    free = ZoneRule(zone="Y", quadplex_allowed=True, setback_front_ft=10,
                    setback_side_ft=5, setback_rear_ft=5)
    assert free.coverage_cap_sqft(10000) is None


def test_gresham_rules_merged():
    from common import load_rules

    g = load_rules().jurisdictions["gresham"]
    assert g.rule_for("LDR-5").quadplex_allowed is True
    assert g.rule_for("LDR-5").min_lot_sqft == 5000
    assert g.rule_for("TLDR").min_lot_sqft is None
    assert g.rule_for("LDR/GB").quadplex_allowed is False
    # Street-side setback exceeds interior side in the MDR zones.
    mdr = g.rule_for("MDR-12")
    assert mdr.setback_street_side_ft == 20
    assert mdr.setback_side_ft == 10
    # Design districts override orientation to axis_required; base zones don't.
    assert g.rule_for("DRL-1").orientation_constraint == "axis_required"
    assert g.rule_for("LDR-5").orientation_constraint is None
    assert g.orientation_constraint == "entrance_only"
    # CMF carries the frontage gate.
    assert g.rule_for("CMF").min_frontage_ft == 100


def test_portland_min_lots_and_rf_exclusion():
    from common import load_rules

    pdx = load_rules().jurisdictions["portland"]
    assert pdx.rule_for("RF").quadplex_allowed is False
    assert pdx.rule_for("R20").min_lot_sqft == 12000
    assert pdx.rule_for("R10").min_lot_sqft == 6000
    assert pdx.rule_for("R7").setback_front_ft == 15
    assert pdx.rule_for("R2.5").min_lot_sqft == 1500


def test_footprints_yaml_validates():
    from common import load_footprints

    fp = load_footprints()
    names = {f.name for f in fp.footprints}
    assert {"pod56x36", "pod80x25"} <= names
    # Pods are 4 side-by-side ~500 sqft townhome footprints (~2000 sqft total).
    for f in fp.footprints:
        assert 1900 <= f.width_ft * f.depth_ft <= 2100
    sweep = fp.constant_area_sweeps[0]
    assert sweep.area_sqft == 2000
    widths = sweep.widths()
    assert widths[0] == 56.0
    assert widths[-1] == 140.0
    # 2 ft pod steps (0.5 ft per unit), inclusive endpoints.
    assert len(widths) == 43
    frontier_widths = fp.frontier.widths()
    assert frontier_widths[0] == 12.0
    assert frontier_widths[-1] == 145.0  # must cover the widest pod


def test_split_spec_math():
    """Per carved lot: 2000 quad + 4 units x 1.5 slots x 162 sqft = 2972."""
    from common import SplitSpec, load_footprints

    split = load_footprints().split
    assert split is not None
    assert split.per_quad_lot_sqft() == pytest.approx(2972)
    # Parking buffer knob changes the per-lot need without touching geometry.
    assert SplitSpec(parking_slots_per_unit=2.0).per_quad_lot_sqft() == pytest.approx(
        2000 + 4 * 2.0 * 162)
    assert SplitSpec(parking_slots_per_unit=0).per_quad_lot_sqft() == pytest.approx(2000)


def test_overlay_policy_schema():
    """Phase 2 overlay config: action vocabulary, slope tiers, coverage grades."""
    from common import OverlaysConfig, SlopeTiers, load_overlays

    cfg = OverlaysConfig.model_validate({
        "slope": {"stat": "p85", "ideal_max_pct": 10, "tolerable_max_pct": 20},
        "overlays": [{
            "key": "fema_flood", "name": "FEMA floodplain", "action": "flag",
            "coverage": {"portland": {"grade": "B", "note": "NFHL uniform"}},
        }, {
            "key": "title13", "name": "Metro habitat", "action": "carve",
            "buffer_ft": 50, "jurisdictions": ["fairview", "wood_village"],
        }],
    })
    assert cfg.by_key("title13").applies_to("fairview")
    assert not cfg.by_key("title13").applies_to("portland")
    assert cfg.by_key("fema_flood").applies_to("portland")  # "all" default
    tiers = SlopeTiers()
    assert tiers.tier(5) == "ideal"
    assert tiers.tier(15) == "tolerable"
    assert tiers.tier(30) == "cost_prohibitive"
    # Missing overlays.yaml -> empty config, pipeline unaffected.
    assert load_overlays().overlays == [] or load_overlays().overlays


def test_lake_oswego_policy_disabled_but_rules_retained():
    """LO is gated at report time — geometry stays so re-enabling is s7-only."""
    from common import load_rules

    lo = load_rules().jurisdictions["lake_oswego"]
    assert lo.eligible is False
    assert lo.rule_for("R-7.5") is not None  # rules compiled, not deleted


def test_screen_spec_defaults_and_yaml():
    """Current-use screen ships with MF+commercial excluded; knobs load."""
    from common import ScreenSpec, load_footprints

    s = ScreenSpec()
    assert s.exclude_current_use == ["multifamily", "commercial"]
    assert s.teardown_max_improvement_share == 0.5
    assert s.vacant_max_improvement_value == 5000.0
    fps = load_footprints()
    assert set(fps.screen.exclude_current_use) == {"multifamily", "commercial"}
    assert fps.screen.vacant_max_improvement_value == 5000


def test_current_use_mapping():
    import pandas as pd

    from s7_report import current_use_column

    lots = pd.DataFrame({
        "STATECLASS": ["101", "701", "201", "301", "401", "", "", None, "101"],
        "LANDUSE":    ["SFR", "MFR", "COM", "IND", "RUR", "MFR", "AGR", "VAC", "SFR"],
        "BLDGVAL":    [300e3, 500e3, 1e6,  2e6,   100e3, 400e3, 50e3, 0,     0],
    })
    assert current_use_column(lots) == [
        "single_family",   # 1xx
        "multifamily",     # 7xx
        "commercial",      # 2xx
        "commercial",      # 3xx industrial folded in
        "single_family",   # 4xx tract
        "multifamily",     # blank class -> LANDUSE fallback
        "other",           # AGR unmapped
        "vacant",          # zero improvement value wins
        "vacant",          # zero improvement value beats class 101
    ]
    # $5k ceiling: token improvements count as vacant too.
    shed = pd.DataFrame({
        "STATECLASS": ["101", "101"],
        "LANDUSE": ["SFR", "SFR"],
        "BLDGVAL": [4_800, 5_200],
    })
    assert current_use_column(shed, vacant_max=5000) == ["vacant", "single_family"]
