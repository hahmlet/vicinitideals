"""Price per home (FOLLOWUPS 66): pods, the road share, the zone's density cap,
the min-one rule, the price-source seam and the adjustable defaults.

Pure arithmetic -- no database. The SQL form that drives the Lots page filter
is held to these same answers in ``tests/api/test_ui_flats_price.py``.
"""

from __future__ import annotations

from decimal import Decimal

from flats.score import price as p

CFG = p.settings()
ROLL = {"assessor": {"total_value": 360_000, "sale_price": 100_000, "sale_date": "20190305"}}


def test_the_defaults_are_the_rulings():
    assert CFG.pod_sqft == 4500
    assert CFG.road_share_pct == 25
    assert CFG.road_from_pods == 3
    assert CFG.homes_per_pod == 4
    assert CFG.default_per_home_max == 30000


def test_a_one_pod_lot_takes_no_road_share_and_is_not_an_estimate():
    got = p.price_per_home(5000, ROLL, CFG, county_as_of="RLIS 2026_08")
    assert (got.pods, got.homes, got.roads_taken, got.estimate) == (1, 4, False, False)
    assert got.per_home == Decimal(360_000) / 4


def test_a_two_pod_lot_still_takes_no_road_share():
    # 13,000 sf is 2.89 pods gross: under the 3-pod threshold, so no roads.
    got = p.price_per_home(13_000, ROLL, CFG)
    assert (got.pods, got.roads_taken, got.estimate) == (2, False, True)


def test_a_three_pod_lot_pays_the_road_share_and_is_an_estimate():
    # 13,500 sf is exactly 3 pods gross; 25% for roads leaves 10,125 sf = 2 pods.
    got = p.price_per_home(13_500, ROLL, CFG)
    assert (got.pods, got.homes, got.roads_taken, got.estimate) == (2, 8, True, True)
    assert got.per_home == Decimal(360_000) / 8
    # A big lot: 90,000 sf -> 67,500 usable -> 15 pods -> 60 homes.
    big = p.price_per_home(90_000, ROLL, CFG)
    assert (big.pods, big.homes) == (15, 60)


def test_a_lot_under_one_pod_holds_none_unless_it_is_green_or_yellow():
    assert p.price_per_home(3000, ROLL, CFG).pods == 0
    assert p.price_per_home(3000, ROLL, CFG).per_home is None
    kept = p.price_per_home(3000, ROLL, CFG, keep_one=True)
    assert (kept.pods, kept.homes) == (1, 4)
    assert kept.per_home == Decimal(90_000)


def test_the_density_cap_binds_and_names_itself():
    # 90,000 sf would be 15 pods; 10 homes an acre on 2.066 acres is 20 homes = 5 pods.
    cap = p.ZoneCap(du_per_acre=Decimal(10))
    got = p.price_per_home(90_000, ROLL, CFG, cap=cap)
    assert (got.pods, got.homes, got.capped_by) == (5, 20, "density")
    # A cap that is not the tighter limit changes nothing.
    loose = p.price_per_home(90_000, ROLL, CFG, cap=p.ZoneCap(du_per_acre=Decimal(100)))
    assert (loose.pods, loose.capped_by) == (15, None)


def test_the_smallest_townhouse_lot_also_caps_and_the_tighter_limit_wins():
    # 1,500 sf lots on 90,000 sf = 60 homes = 15 pods: not binding.
    assert p.price_per_home(90_000, ROLL, CFG, cap=p.ZoneCap(unit_lot_sqft=Decimal(1500))).pods == 15
    # 7,000 sf lots = 12 homes = 3 pods.
    got = p.price_per_home(90_000, ROLL, CFG, cap=p.ZoneCap(unit_lot_sqft=Decimal(7000)))
    assert (got.pods, got.capped_by) == (3, "unit lot")
    # Both stated: density 10/acre (20 homes) is tighter than 1,500 sf lots (60).
    both = p.ZoneCap(du_per_acre=Decimal(10), unit_lot_sqft=Decimal(1500))
    assert p.price_per_home(90_000, ROLL, CFG, cap=both).capped_by == "density"


def test_a_cap_never_takes_a_green_lot_below_one_pod():
    cap = p.ZoneCap(du_per_acre=Decimal(1))
    assert p.price_per_home(9_000, ROLL, CFG, cap=cap).pods == 0
    assert p.price_per_home(9_000, ROLL, CFG, cap=cap, keep_one=True).pods == 1


def test_a_missing_or_zero_value_is_no_price_not_zero():
    for facts in (None, {}, {"assessor": {}}, {"assessor": {"total_value": None}}, {"assessor": {"total_value": 0}}):
        got = p.price_per_home(5000, facts, CFG)
        assert got.quote is None and got.per_home is None and got.pods == 1


def test_the_quote_carries_its_source_and_as_of_date():
    got = p.price_per_home(5000, ROLL, CFG, county_as_of="RLIS 2026_08 release")
    assert got.quote is not None
    assert got.quote.source == "County real market value"
    assert got.quote.as_of == "RLIS 2026_08 release"
    assert got.quote.amount == 360_000


def test_a_second_source_slots_in_ahead_of_the_county_roll():
    feed = p.PriceSource(
        name="Paid feed", amount_path=("price_feed", "price"), as_of_path=("price_feed", "as_of"), basis="vendor AVM"
    )
    facts = {**ROLL, "price_feed": {"price": 500_000, "as_of": "2026-12-01"}}
    got = p.price_per_home(5000, facts, CFG, sources=(feed, *p.PRICE_SOURCES))
    assert got.quote is not None and got.quote.source == "Paid feed" and got.quote.as_of == "2026-12-01"
    assert got.per_home == Decimal(125_000)
    # The feed has nothing on a lot -> the roll answers, under its own name.
    other = p.price_per_home(5000, ROLL, CFG, sources=(feed, *p.PRICE_SOURCES))
    assert other.quote is not None and other.quote.source == "County real market value"


def test_adjusted_defaults_change_the_count_and_bad_input_is_ignored():
    wide = CFG.adjusted(pod_sqft="9000", road_share_pct="0")
    got = p.price_per_home(13_500, ROLL, wide)
    assert (got.pods, got.roads_taken) == (1, False)
    kept = CFG.adjusted(pod_sqft="banana", road_share_pct="400")
    assert (kept.pod_sqft, kept.road_share_pct) == (CFG.pod_sqft, CFG.road_share_pct)
    assert CFG.adjusted(pod_sqft="", road_share_pct=None) == CFG
    half = CFG.adjusted(road_share_pct="50")
    assert p.price_per_home(90_000, ROLL, half).pods == 10


def test_the_real_rules_state_caps_for_a_known_zone():
    from flats.encode.load import load_trusted
    from flats.rules.resolver import RuleSet

    layers = load_trusted(strict=False).layers
    caps = p.zone_caps(RuleSet(layers), layers)
    assert len(caps) > 50
    assert caps[("or/clackamas/happy-valley", "R5")].du_per_acre == Decimal(25)
    assert caps[("or/clackamas/estacada", caps_zone("or/clackamas/estacada", caps))].unit_lot_sqft is not None


def caps_zone(layer: str, caps: dict) -> str:
    return next(z for (lid, z), c in caps.items() if lid == layer and c.unit_lot_sqft is not None)
