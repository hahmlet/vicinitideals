"""Portland's planted strip beside a residential lot (FOLLOWUPS 171, 2026-11-09).

33.130.215.B.2.b: the 10 ft setback from a lot line that abuts an RF through
RM4, RMP or IR zone "must be landscaped to the L3 standard", and only areas
"paved for pedestrian or bicycle use" may stand in it. Table 130-2 prints the
same strip in all six commercial/mixed use zones. The screen let the rear
court share that yard, so a CM2 corner lot backing onto RM1 (1S1E26AB  -01200,
the blind read fg-rate-A) stood GREEN on a court that ran through the planted
ground. Table 140-3 keeps a 5 ft L3 buffer in EX, and Table 150-2 a 10 ft one
in IR.

The strip reuses ``parking_lot_line_buffer_ft`` and the lot-level neighbour
fact the side and rear setbacks already turn on (``abuts_nonresidential_zone``):
0 only where every non-street line is read and nothing across it is
residential.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import box

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
FIELD = "parking_lot_line_buffer_ft"
FACT = "abuts_nonresidential_zone"
COMMERCIAL = ("CR", "CM1", "CM2", "CM3", "CE", "CX")
TLID = "1S1E26AB  -01200"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


@pytest.mark.parametrize(
    ("zone", "beside_a_house", "all_commercial"),
    [*((z, 10, 0) for z in COMMERCIAL), ("EX", 5, 0), ("IR", 10, 10)],
)
def test_the_strip_is_the_one_the_code_prints(corpus, zone, beside_a_house, all_commercial) -> None:
    rules = RuleSet(corpus)
    assert rules.resolve(PORTLAND, zone).values[FIELD].value == beside_a_house
    assert rules.resolve(PORTLAND, zone, {FACT}).values[FIELD].value == all_commercial


def test_the_quotes_say_planted_and_name_the_zones(corpus) -> None:
    store = ProvenanceStore()
    cm = corpus[PORTLAND].zones["CM2"].values[FIELD]
    text = " ".join(store.quote(cm.prov.quote).split())
    assert "Landscape Buffer Abutting an RF – RM4 or" in text
    assert "10 ft. @ L3" in text
    via = " ".join(store.quote(cm.prov.via).split())
    assert "RF through RM4, RMP, or IR zone is 10 feet" in via
    assert "must be landscaped to the L3 standard" in via
    assert "Areas paved for pedestrian or bicycle use" in via
    # Neither exception lifts the strip: (2) is for buildings 15 ft or less,
    # and (3) keeps the first 10 ft landscaped under both.
    assert "15 feet or less in height" in via
    assert "For both exceptions" in via
    assert "no minimum setback required from a lot line that abuts an OS, RX, C, E or CI zone" in (
        store.quote(cm.variants[0].prov.quote)
    )
    ex = corpus[PORTLAND].zones["EX"].values[FIELD]
    assert "10 ft. / 5 ft. @ L3" in store.quote(ex.prov.quote)
    assert "at least the L3 standard" in " ".join(store.quote(ex.prov.via).split())
    ir = corpus[PORTLAND].zones["IR"].values[FIELD]
    assert "10 ft. @L3" in store.quote(ir.prov.quote)
    assert "Landscaping is required in minimum" in store.quote(ir.prov.via)


# --- through the bridge -------------------------------------------------------

X0, Y0 = 7_650_000.0, 670_000.0
QUIET = {
    "constrained_sites_overlay": False,
    "pdx_johnson_creek_impervious": False,
    "pdx_johnson_creek_unmeasured": False,
    "pdx_special_building_setback": False,
    "pdx_plan_district_unmeasured": False,
    "civic_corridor": False,
    "civic_corridor_setback": False,
    "civic_corridor_setback_all_streets": False,
}


def _corner(rear_zone: str | None, layers):
    """1S1E26AB  -01200's arrangement: a CM2 corner lot, streets on two
    sides, one shared side line (CM2) and the rear line behind. Sized up
    from its 50 x 100 ft to 60 x 130 so the pod fits at this sweep's
    30-degree step when the strip is lifted (the control below)."""
    from flats.ingest.quadfit import lot_from_row

    w, d = 60.0, 130.0
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "F"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    rear = {"z": [], "none": 5} if rear_zone is None else {"z": [["portland", rear_zone]]}
    row = {
        "TLID": TLID,
        "jurisdiction": "portland",
        "zone": "CM2",
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w + d,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[178.0, 88.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(X0 + 10, Y0, X0 + w, Y0 + d - 10)),
        "lot_wkb": shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
        "neighbour_zones_json": json.dumps([None, None, rear, {"z": [["portland", "CM2"]]}]),
    }
    lot = lot_from_row(row, layers)
    return dataclasses.replace(lot, observed={**lot.observed, **QUIET})


def _screen(lot, trusted, *, without: tuple[str, ...] = ()):
    from flats.designs.model import load_catalog
    from flats.ingest.quadfit import screen_lot
    from flats.score import relief, slack

    from flats.ingest.quadfit import _Waived

    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=_Waived(trusted, without) if without else trusted,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s


@pytest.fixture(scope="module")
def trusted():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def test_the_corner_lot_backing_onto_rm1_is_not_green(trusted) -> None:
    from flats.score import flags as flag_plan

    lot = _corner("RM1", trusted.layers)
    s = _screen(lot, trusted)
    assert s.lot.observed.get(FACT) is False
    assert s.rules.get(FIELD) == 10
    assert s.signed.colour is not flag_plan.Colour.green
    # The control: the same lot with the planted strip lifted is the GREEN
    # the live map showed, so the strip is what moves it.
    assert _screen(lot, trusted, without=(FIELD,)).signed.colour is flag_plan.Colour.green


def test_an_unread_rear_line_keeps_the_strip(trusted) -> None:
    from flats.score import flags as flag_plan

    s = _screen(_corner(None, trusted.layers), trusted)
    assert FACT not in s.lot.observed
    assert s.rules.get(FIELD) == 10
    assert s.signed.colour is not flag_plan.Colour.green


def test_the_same_lot_among_commercial_lots_owes_no_strip(trusted) -> None:
    from flats.score import flags as flag_plan

    s = _screen(_corner("CM2", trusted.layers), trusted)
    assert s.lot.observed.get(FACT) is True
    assert not s.rules.get(FIELD)
    assert s.signed.colour is flag_plan.Colour.green
