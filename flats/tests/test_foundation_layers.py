"""FD6 foundation model: the two layers (MEASURE once, PRICE many times), the
flat stored rows, and the plain-words classification (style, challenges, easy parts).

No lot file needed: synthetic planes and random six-reading lots only.
"""

from __future__ import annotations

import dataclasses
import random
from decimal import Decimal

import pytest

from flats.tests.foundation_key import key_settings
from flats.foundation import classify, lot, measure, model, rows, settings, support
from flats.foundation import ground as grounds
from flats.foundation.__main__ import TEST_LOTS

#: Arithmetic on the FD6 answer key's dimensions (80 x 25 ft; see foundation_key).
S = key_settings()
TEST = {name: (along, across) for name, along, across in TEST_LOTS}


def _plane(along: float, across: float) -> grounds.Plane:
    return grounds.plane(S, along, across, 0.0)


def _random_six(seed: int, n: int = 12) -> list[tuple[float, ...]]:
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        base = rnd.uniform(-50, 500)
        z = tuple(base + rnd.uniform(-3, 3) for _ in range(6))
        out.append(z + (rnd.choice([0.0, rnd.uniform(0, 8)]),))
    return out


SIX = _random_six(1119)


def _six(vals: tuple[float, ...]) -> grounds.SixReadings:
    *z, relief = vals
    return grounds.six_readings(S, *z, relief_ft=relief if relief else None, cell_m=2.0)


def _cases() -> list[tuple[grounds.Ground, dict]]:
    out: list[tuple[grounds.Ground, dict]] = [(_plane(*v), {"ground_class": "FIRM"}) for v in TEST.values()]
    for i, v in enumerate(SIX):
        cls = ("FIRM", "SOFT", "HAZ-LIQ", "NO-DATA")[i % 4]
        out.append(
            (
                _six(v),
                {
                    "ground_class": cls,
                    "alt_ground_class": "COBBLE" if i % 8 == 3 else "",
                    "relief_input_ft": v[6],
                    "bldg_overlap_share": 0.4,
                    "front_face_turn_deg": 60.0,
                    "frost_register_in": 12.0,
                },
            )
        )
    return out


def _changed() -> settings.Settings:
    """A price, several thresholds and several sizes changed -- none of them geometric."""
    prices = dict(S.prices)
    prices["concrete_yd3"] = settings.Price(Decimal("200"), Decimal("260"), "per cu yd", "test")
    prices["riser"] = settings.Price(Decimal("75"), Decimal("140"), "per riser", "test")
    return S.replace(
        prices=prices,
        guard_over_in=24.0,
        plain_wall_max_in=84.0,
        fill_limit_in=18.0,
        tall_wall_over_ft=5.0,
        long_stair_over_ft=6.0,
        clear_in=24.0,
        riser_in=7.5,
        embed_in=12.0,
        concrete_waste=1.10,
        wall_bands_ft=(2.0, 4.0, 7.0),
    )


# ---------------------------------------------------------------- MEASURE once, PRICE many times


def test_repricing_stored_rows_equals_a_full_recompute() -> None:
    """Change a price and a threshold (and sizes): re-pricing from the stored
    measured rows alone gives exactly what measuring the ground again gives."""
    new = _changed()
    for g, inputs in _cases():
        stored = rows.measured_rows(measure.measure(g, S, tlid="1N1E  -100", inputs=inputs))
        repriced = lot.assess(rows.from_measured_rows(*stored), new)
        full = lot.run_lot(g, new, group=None, tlid="1N1E  -100", inputs=inputs)
        assert rows.assessed_rows(repriced) == rows.assessed_rows(full)
        # ... and the change did change the answer
        old = lot.assess(rows.from_measured_rows(*stored), S)
        assert rows.assessed_rows(repriced) != rows.assessed_rows(old)


def test_the_measured_rows_round_trip_exactly() -> None:
    for g, inputs in _cases():
        m = measure.measure(g, S, tlid="1S2E 10AB -100", county="clackamas", inputs=inputs)
        assert rows.from_measured_rows(*rows.measured_rows(m)) == m


def test_a_record_refuses_prices_under_other_geometric_settings() -> None:
    m = measure.measure(_plane(1, 0), S)
    for change in ({"station_ft": 0.5}, {"door_x_front_ft": (5.0, 25.0, 45.0, 65.0)}, {"fill_bands_in": (6.0,)}):
        with pytest.raises(ValueError, match="re-measure"):
            lot.assess(m, S.replace(**change))
    assert set(measure.GEOMETRIC) <= {f.name for f in dataclasses.fields(settings.Settings)}


def test_the_measured_record_holds_the_ground_facts() -> None:
    g = _plane(3, 1)
    m = measure.measure(g, S, inputs={"relief_input_ft": 4.0, "frost_register_in": 12.0})
    assert m.fall_along_ft == pytest.approx(3.0) and m.fall_across_ft == pytest.approx(1.0)
    assert m.relief_sampled_ft == pytest.approx(4.0) and m.low_drop_in == pytest.approx(48.0)
    assert m.relief_input_ft == 4.0 and m.frost_register_in == 12.0
    assert m.ground_source == "plane" and m.readings is None and m.lump_ft == 0.0
    assert len(m.doors) == 8 and len(m.lines) == 7
    assert sum(len(ln.drops_in) for ln in m.lines) == 285
    for d in m.doors:
        y = 0.0 if d.face == "front" else S.width_ft
        assert d.drop_in == pytest.approx(-g(d.x_ft, y) * 12)
    # fill over 12 / 24 / 48 in on a plane falling 4 ft along (1 ft cells)
    pm = measure.measure(_plane(4, 0), S)
    expect = [25.0 * sum(1 for i in range(80) if 48 * (i + 0.5) / 80 > band) for band in (12, 24, 48)]
    assert list(pm.fill_area_over_sf) == pytest.approx(expect)
    assert pm.fill_area_over_sf[2] == 0.0
    assert pm.fill_volume_ft3 == pytest.approx(4 / 2 * 80 * 25)
    six = measure.measure(_six(SIX[0]), S)
    assert six.readings == SIX[0][:6] and six.ground_source == "six readings" and six.cell_m == 2.0


def test_quantities_are_kept_before_and_after_their_factors() -> None:
    for along, across in TEST.values():
        for r in (model.raised(_plane(along, across), S), model.slab(_plane(along, across), S)):
            assert r.concrete_yd3 == pytest.approx(r.concrete_net_yd3 * r.concrete_waste)
            assert r.bars_lb == pytest.approx((r.level_bar_ft_net * r.lap + r.upright_bar_ft) * r.bar_lb_per_ft)
            assert r.concrete_waste == S.concrete_waste and r.lap == S.lap


def test_wall_band_lengths_add_up_to_the_line() -> None:
    b = model.raised(_plane(6, 0), S)
    for ln in b.lines:
        assert len(ln.band_length_ft) == len(S.wall_bands_ft) + 1
        assert sum(ln.band_length_ft) == pytest.approx(ln.length_ft)
        assert ln.shortest_in <= ln.average_in <= ln.tallest_in
    front = next(ln for ln in b.lines if ln.name == "front")
    # wall = 29 in + 72 in * x / 80 along the front, at 1 ft stations
    assert front.band_length_ft[0] == pytest.approx(8.0)  # 3 ft or under: x up to 7.5
    assert front.band_length_ft[-1] == pytest.approx(6.0)  # over 8 ft: x from 74.5


# ---------------------------------------------------------------- plain-words classification


def _codes(items) -> set[tuple[str, str]]:
    return {(i.code, i.method) for i in items}


def test_a_flat_lot_is_all_easy_parts() -> None:
    r = lot.run_lot(_plane(0, 0), S)
    assert r.challenges == ()
    assert _codes(r.easy) == {
        (classify.NEAR_FLAT, ""),
        (classify.ORDINARY, ""),
        (classify.LOW_WALLS, "B"),
        (classify.NO_GUARDS, "B"),
        (classify.NO_GUARDS, "A"),
        (classify.SHALLOW_FILL, "A"),
    }
    assert r.style.standard == ("A", "B")
    assert r.style.cheaper_low in ("A", "B") and r.style.cheaper_high in ("A", "B")
    assert r.style.words.startswith("Ordinary footing")


def test_a_steep_lot_names_its_challenges_with_their_values() -> None:
    r = lot.run_lot(_plane(6, 0), S)
    by = {(i.code, i.method): i for i in r.challenges}
    b, a = r["B"], r["A dry"]
    assert by[(classify.TALL_WALL, "B")].value == pytest.approx(b.tallest_wall_in / 12)
    assert (classify.WALL_OVER_STANDARD, "B") in by
    assert by[(classify.DEEP_FILL, "A")].value == pytest.approx(a.fill_max_in)
    assert by[(classify.RETAINED_EDGE, "A")].value == pytest.approx(a.tallest_wall_in - S.edge_d_in)
    assert by[(classify.GUARDS, "B")].value == b.guards > 0
    assert by[(classify.GUARDS, "A")].value == a.guards > 0
    assert by[(classify.LONG_STAIR, "B")].value == pytest.approx(b.longest_stair_in / 12)
    assert not any(i.code == classify.NEAR_FLAT for i in r.easy)
    assert not any(i.code == classify.LOW_WALLS for i in r.easy)


def test_a_threshold_moves_a_challenge_without_re_measuring() -> None:
    m = measure.measure(_plane(2, 0), S)  # tallest wall 29 + 24 = 53 in
    assert (classify.TALL_WALL, "B") not in _codes(lot.assess(m, S).challenges)
    lowered = lot.assess(m, S.replace(tall_wall_over_ft=4.0))
    assert (classify.TALL_WALL, "B") in _codes(lowered.challenges)
    assert (classify.LOW_WALLS, "B") not in _codes(lot.assess(m, S).easy)
    assert (classify.LOW_WALLS, "B") in _codes(lot.assess(m, S.replace(low_wall_max_ft=4.5)).easy)


def test_ground_and_lot_challenges() -> None:
    g = grounds.six_readings(S, 0, 0, 0, 0, 0, 0, relief_ft=0.0, cell_m=10.0)
    inputs = {"ground_class": "SOFT", "bldg_overlap_share": 0.3, "front_face_turn_deg": 70.0}
    r = lot.run_lot(g, S, group=None, inputs=inputs)
    assert r.group == support.PILES and r.style.standard == ("B+P",) and r.style.cheaper_low is None
    codes = _codes(r.challenges)
    assert {(classify.PILES, ""), (classify.COARSE, ""), (classify.FRONT_GUESS, "")} <= codes
    # The share of the pod over a building no longer raises a challenge on its own:
    # only a measured wall over an old outline does (slice 2, test_foundation_old_buildings).
    assert (classify.WALL_OVER_OLD, "") not in codes
    assert not any(i.method == "A" for i in r.challenges + r.easy), "no slab on piles ground"
    own = lot.run_lot(g, S, group=None, inputs={"ground_class": "NO-DATA", "alt_ground_class": "FLOOD"})
    assert own.group == support.OWN_LOOK and (classify.OWN_LOOK, "") in _codes(own.challenges)
    unsorted = lot.run_lot(g, S, group=None, inputs={"ground_class": "NO-DATA"})
    assert unsorted.group == support.NOT_SORTED and (classify.NOT_SORTED, "") in _codes(unsorted.challenges)
    small = lot.run_lot(g, S, group=None, inputs={"ground_class": "FIRM", "bldg_overlap_share": 0.2})
    assert (classify.WALL_OVER_OLD, "") not in _codes(small.challenges)
    assert (classify.ORDINARY, "") in _codes(small.easy)


def test_every_classification_threshold_is_a_labelled_setting() -> None:
    for name in settings.SECTIONS["classify"]:
        assert S.sources[f"classify.{name}"].strip()
    est = [n for n in settings.SECTIONS["classify"] if "[est]" in S.sources[f"classify.{n}"]]
    assert est, "the classification thresholds are mine and say so"


def test_assessed_rows_are_flat() -> None:
    r = lot.run_lot(_plane(2, 1), S, tlid="1S1E  -9")
    one, lines, doors = rows.assessed_rows(r)
    assert one["tlid"] == "1S1E  -9" and one["group"] == support.ORDINARY
    assert len(doors) == 4 * 8 and {d["method"] for d in doors} == {"B", "B+P", "A dry", "A wet"}
    assert {ln["method"] for ln in lines} == {"B", "B+P", "A dry", "A wet"}
    assert one["b_cost_low"] == str(r["B"].cost.low)
    for row in [one, *lines, *doors]:
        assert all(v is None or isinstance(v, (str, int, float, bool)) for v in row.values()), row
    m_lot, m_lines, m_doors = rows.measured_rows(r.measured)
    assert all(not isinstance(v, (list, tuple, dict)) for v in m_lot.values())
    assert len(m_lines) == 7 and len(m_doors) == 8
