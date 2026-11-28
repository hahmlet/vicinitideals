"""A building drawn within 100 ft of a Columbia River or Columbia Slough levee
is a closer look (Steph 2026-11-28, rulings.yaml
2026-11-28-levee-review-zone-yellow: "Yellow for a look").

The drainage districts (MCDD and its sister districts) review development in
their 100 ft levee buffer under their own rules, which could not be read
(pdx-flood-left). The contracts:

* a GREEN whose drawn building stands in the buffer is YELLOW with
  LEVEE-REVIEW-ZONE, naming how much of it is inside;
* a GREEN on a lot the buffer reaches with no fitting drawing is YELLOW too;
* a building clear of the buffer, and a lot it does not reach, are untouched;
* a YELLOW or RED keeps its colour (the flag rides along); nothing moves
  toward GREEN;
* the stored buffer is the districts' published layer, in EPSG:2913.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

shapely = pytest.importorskip("shapely")

from flats.geom.drawn import AREAS_ROOT, load_area  # noqa: E402
from flats.ingest.quadfit import (  # noqa: E402
    LEVEE_REVIEW,
    LEVEE_REVIEW_FILE,
    levee_review_checked,
    lot_from_row,
    screen_lot,
)
from flats.score.screen import CLOSER_LOOK_LEVEE_REVIEW, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    corpus,  # noqa: F401  (fixture)
    pod,
    policies,  # noqa: F401  (fixture)
)
from flats.tests.test_split_zone import D, W, big_row  # noqa: E402

pytestmark = pytest.mark.unit


def _coloured(s, triage):
    def paint(x):
        return dataclasses.replace(x, triage=triage, reasons=(), flags=(), binds=())

    return dataclasses.replace(s, screening=paint(s.screening), signed=paint(s.signed))


def _screened(corpus, policies, triage=Triage.green):  # noqa: F811
    lot = lot_from_row(big_row(jurisdiction="portland", zone="R5"), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return lot, _coloured(s, triage)


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [list(p) for p in shapely.box(x0, y0, x1, y1).exterior.coords]


def _drawn(s, building, fits=True):
    drawing = dict(s.drawing or {})
    drawing["fits"] = fits
    drawing["building"] = building
    return dataclasses.replace(s, drawing=drawing)


#: A buffer over the rear 40 ft of the lot (the levee behind it).
REAR = shapely.box(X0 - 50, Y0 + D - 40, X0 + W + 50, Y0 + D + 200)
#: A buffer that stops 30 ft short of the lot.
AWAY = shapely.box(X0 - 50, Y0 + D + 30, X0 + W + 50, Y0 + D + 200)


def levee_flags(s):
    return [f for f in s.signed.flags if f.code == LEVEE_REVIEW]


def test_a_building_drawn_in_the_buffer_is_held_yellow(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies)
    got = levee_review_checked(_drawn(s, _box(X0 + 10, Y0 + 60, X0 + 90, Y0 + 125)), lot, REAR)
    (flag,) = levee_flags(got)
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_LEVEE_REVIEW in got.signed.reasons
    assert "drawn building stands 1,200 sq ft inside" in flag.source


def test_a_building_clear_of_the_buffer_stays_green(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies)
    drawn = _drawn(s, _box(X0 + 10, Y0 + 20, X0 + 90, Y0 + 100))
    assert levee_review_checked(drawn, lot, REAR) is drawn


def test_a_lot_the_buffer_misses_is_not_asked(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies)
    drawn = _drawn(s, None, fits=False)
    assert levee_review_checked(drawn, lot, AWAY) is drawn


def test_no_fitting_building_on_a_lot_the_buffer_reaches_is_held(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies)
    got = levee_review_checked(_drawn(s, None, fits=False), lot, REAR)
    (flag,) = levee_flags(got)
    assert got.signed.triage is Triage.yellow
    assert "no fitting building" in flag.source


@pytest.mark.parametrize("triage", [Triage.yellow, Triage.red])
def test_a_held_lot_keeps_its_colour_and_gains_the_flag(corpus, policies, triage) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, triage)
    got = levee_review_checked(_drawn(s, _box(X0 + 10, Y0 + 60, X0 + 90, Y0 + 125)), lot, REAR)
    assert got.signed.triage is triage and got.screening.triage is triage
    assert len(levee_flags(got)) == 1


def test_the_stored_buffer_is_the_districts_published_layer() -> None:
    data = json.loads((AREAS_ROOT / LEVEE_REVIEW_FILE).read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("2913")
    assert "PPD_Flood_and_Natural_Resources/MapServer/13" in data["source"]["url"]
    assert "2026-11-28-levee-review-zone-yellow" in data["source"]["note"]
    (feature,) = data["features"]
    assert round(feature["properties"]["BUFF_DIST"]) == 100
    area = load_area(LEVEE_REVIEW_FILE)
    x0, y0, x1, y1 = area.bounds
    # The Columbia corridor: north Portland's river front east to Troutdale.
    assert 7_630_000 < x0 < x1 < 7_725_000 and 685_000 < y0 < y1 < 720_000
    assert area.area > 50_000_000
