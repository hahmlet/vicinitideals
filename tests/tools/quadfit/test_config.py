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
