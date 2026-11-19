"""Housing-authority land is YELLOW, not red (Steph 2026-11-18, rulings.yaml
``2026-11-18-housing-authority-land-yellow``; FOLLOWUPS 205).

A bare, untaxed lot whose owner of record is a housing authority (Home
Forward, the Housing Authority of Portland) is not ruled out as a
government's is: the bridge keeps it in the scan and marks it
(``with_owner_hold``), and the screen holds it YELLOW with the reason
``HOUSING_AUTHORITY_LAND`` and the flag ``OWNER-HOUSING-AUTHORITY`` -- never
GREEN on its own, and RED only where something else makes it red.
"""

from __future__ import annotations

import dataclasses

import pytest

from flats.geom import roll
from flats.ingest.quadfit import OWNER_HOLD_COLUMNS, S4_COLUMNS, lot_from_row, with_owner_hold
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict
from flats.score import relief, slack
from flats.score.configure import configure
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import HOUSING_AUTHORITY_LAND, screen
from flats.tests.test_center_cores import CORE, FAR, HILLSBORO, PLAIN
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_round2_rulings import DESIGN, facts, fit

pytestmark = pytest.mark.unit

FLAG = "OWNER-HOUSING-AUTHORITY"
#: A Home Forward lot and a City of Portland lot off the checked-in list.
HOUSING_LOT = "1N1E14AA  -06200"
CITY_LOT = "1N1E06DD  -01500"
BARE = {"PROP_CODE": "701", "BLDGVAL": 0.0, "BLDGSQFT": 0.0, "ASSESSVAL": 0.0}
WHY = "multnomah owner of record (a housing authority), with no assessed value and no building on the roll"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


# --- the bridge -----------------------------------------------------------------


def test_the_bridge_reads_what_the_hold_needs_off_the_stage_file() -> None:
    assert set(OWNER_HOLD_COLUMNS) <= set(S4_COLUMNS)


def test_the_bridge_marks_a_bare_housing_authority_lot_and_keeps_it() -> None:
    rows = [row(TLID=HOUSING_LOT, **BARE), row(**BARE), row(TLID=CITY_LOT, **BARE)]
    assert with_owner_hold(rows) == 1
    assert rows[0]["owner_hold"] == WHY
    assert "owner_hold" not in rows[1] and "owner_hold" not in rows[2]
    assert lot_from_row(rows[0]).facts.owner_hold == WHY
    assert lot_from_row(rows[1]).facts.owner_hold == ""


def test_a_parcel_number_is_matched_whole_spaces_and_all() -> None:
    rows = [row(TLID=HOUSING_LOT + "   ", **BARE), row(TLID=HOUSING_LOT.replace(" ", ""), **BARE)]
    assert with_owner_hold(rows) == 1
    assert "owner_hold" in rows[0] and "owner_hold" not in rows[1]


def test_a_built_or_taxed_housing_authority_lot_is_screened_like_any_lot() -> None:
    rows = [
        row(TLID=HOUSING_LOT, **{**BARE, "BLDGVAL": 2_704_790.0, "BLDGSQFT": 48_612.0}),
        row(TLID=HOUSING_LOT, **{**BARE, "ASSESSVAL": 96_000.0}),
    ]
    assert with_owner_hold(rows) == 0


def test_a_row_without_the_roll_columns_is_held() -> None:
    # Unread is the conservative answer: neither taxed nor built.
    rows = [row(TLID=HOUSING_LOT)]
    assert with_owner_hold(rows) == 1


def test_the_same_number_in_another_county_is_not_held() -> None:
    rows = [row(TLID=HOUSING_LOT, jurisdiction="hillsboro", zone="SFR-7", **BARE)]
    assert with_owner_hold(rows) == 0


def test_the_roll_does_not_take_the_lot_out_of_the_scan() -> None:
    record = {"county": "multnomah", "tlid": HOUSING_LOT, "site_address": "1 NE MAIN ST", "LANDVAL": 1.0, "TOTALVAL": 1.0, **BARE}
    assert roll.read(record, roll.load_rules()) is None


# --- the screen -----------------------------------------------------------------


def _screen(corpus: RuleSet, **lot_facts: object):
    """A Hillsboro MU-VTC lot that is GREEN with every fact answered
    (``test_center_cores``), with ``lot_facts`` on top."""
    lot = facts(street_lines_ft=(80.0,), lot_sqft=9000, inside_ugb=True, driveway_spacing="clear", **lot_facts)
    cfg = configure(lot, DESIGN, observed={**PLAIN, CORE: False, FAR: False})
    got = corpus.resolve(HILLSBORO, "MU-VTC", cfg.conditions)
    got = dataclasses.replace(got, verdict=Verdict.trusted, untrusted=())
    return screen(
        got, lot, DESIGN, fit(), policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(), config=cfg,
    )


def test_a_lot_that_would_be_green_is_yellow_with_the_plain_reason(corpus: RuleSet) -> None:
    plain = _screen(corpus)
    assert plain.colour is Colour.green
    assert HOUSING_AUTHORITY_LAND not in plain.reasons and FLAG not in {f.code for f in plain.flags}

    held = _screen(corpus, owner_hold=WHY)
    assert held.colour is Colour.yellow
    assert HOUSING_AUTHORITY_LAND in held.reasons
    (flag,) = [f for f in held.flags if f.code == FLAG]
    assert flag.source == WHY


def test_the_flag_alone_holds_a_lot_yellow() -> None:
    entry = load_registry()[FLAG]
    assert entry.severity >= colour_rules().yellow_at_severity
    assert entry.raised_from == (HOUSING_AUTHORITY_LAND,) or list(entry.raised_from) == [HOUSING_AUTHORITY_LAND]
