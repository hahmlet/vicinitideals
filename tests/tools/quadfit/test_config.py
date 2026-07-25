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
    assert {"25x25", "18x32"} <= names
    sweep = fp.constant_area_sweeps[0]
    widths = sweep.widths()
    assert widths[0] == 14.0
    assert widths[-1] == 35.0
    # Half-foot steps, inclusive endpoints.
    assert len(widths) == 43
    frontier_widths = fp.frontier.widths()
    assert frontier_widths[0] == 12.0
    assert frontier_widths[-1] == 60.0
