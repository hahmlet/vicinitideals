"""Gresham's 9.0100 buffers, held against the drawn plan (FOLLOWUPS 222; fg5
round 5, F1: a CMF lot's drawn lane and court 4-5 ft off a multi-family line
that is owed a 10 ft standard-A buffer).

The contracts (:mod:`flats.geom.lot_line_buffer`):

* a GREEN whose drawn court stands inside 10 ft of a line across from a zone
  that permits a buffered use (MDR-24 here) is YELLOW with
  MEASURE-LOT-LINE-BUFFER;
* the same plan with only LDR-5/LDR-7/TR/TLDR across every non-street line,
  or with the court 10 ft off the owed line, is untouched;
* a line whose neighbour was not read (split, unzoned, another city, no
  record) owes the buffer, so the plan is held;
* street lines are not measured; other places are untouched; nothing moves
  toward GREEN;
* the config holds the printed figure, and its quotes print it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

shapely = pytest.importorskip("shapely")

from flats.geom import lot_line_buffer as llb  # noqa: E402
from flats.ingest.quadfit import lot_from_row, screen_lot  # noqa: E402
from flats.score.screen import CLOSER_LOOK_LOT_LINE_BUFFER, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    across,
    corpus,  # noqa: F401  (fixture)
    pod,
    policies,  # noqa: F401  (fixture)
    zoned,
)
from flats.tests.test_split_zone import big_row  # noqa: E402

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"
LDR = ("gresham", "LDR-7")
MDR = ("gresham", "MDR-24")


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [list(p) for p in shapely.box(x0, y0, x1, y1).exterior.coords]


#: Building at the street (south) end, lane up the west side, court behind
#: the building running to 4 ft off the EAST line (the 100 x 150 fixture lot).
NEAR_EAST = {
    "fits": True,
    "building": _box(X0 + 20, Y0 + 10, X0 + 76, Y0 + 50),
    "lane": _box(X0 + 8, Y0, X0 + 18, Y0 + 60),
    "court": _box(X0 + 20, Y0 + 60, X0 + 96, Y0 + 100),
}


def _screened(corpus, policies, east, rear=LDR, west=LDR, *, jurisdiction="gresham", zone="CMF", drawing=NEAR_EAST):  # noqa: F811
    e = east if isinstance(east, dict) else zoned(east)
    r = rear if isinstance(rear, dict) else zoned(rear)
    w = west if isinstance(west, dict) else zoned(west)
    lot = lot_from_row(
        big_row(jurisdiction=jurisdiction, zone=zone, neighbour_zones_json=across(e, r, w)),
        corpus.layers,
    )
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)

    def green(x):
        return dataclasses.replace(x, triage=Triage.green, reasons=(), flags=(), binds=())

    s = dataclasses.replace(s, screening=green(s.screening), signed=green(s.signed), drawing=drawing)
    return lot, s


def _held(s) -> bool:
    return (
        s.signed.triage is Triage.yellow
        and CLOSER_LOOK_LOT_LINE_BUFFER in s.signed.reasons
        and any(f.code == llb.FLAG for f in s.signed.flags)
    )


def test_a_court_inside_the_buffer_owed_a_multi_family_line_is_not_green(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, MDR)
    out = llb.checked(s, lot)
    assert _held(out)
    assert out.screening.triage is Triage.yellow
    (flag,) = [f for f in out.signed.flags if f.code == llb.FLAG]
    assert "court 4.0 ft off a side line (beside MDR-24)" in flag.source


def test_the_same_plan_beside_houses_only_is_untouched(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, LDR, ("gresham", "TR"), ("gresham", "LDR-5"))
    assert llb.checked(s, lot) is s


def test_a_court_ten_feet_off_the_owed_line_is_untouched(corpus, policies) -> None:  # noqa: F811
    clear = dict(NEAR_EAST, court=_box(X0 + 20, Y0 + 60, X0 + 90, Y0 + 100))
    lot, s = _screened(corpus, policies, MDR, drawing=clear)
    assert llb.checked(s, lot) is s


@pytest.mark.parametrize(
    "east",
    [
        zoned(LDR, split=1),  # a split-zone neighbour
        zoned(none=5),  # no zoned private land read
        zoned(("portland", "R5")),  # another city's code
        zoned(("gresham", "XYZ")),  # a code on no list
    ],
)
def test_an_unread_neighbour_owes_the_buffer(corpus, policies, east) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, east)
    assert _held(llb.checked(s, lot))


def test_no_fitting_drawing_beside_an_owed_line_is_held(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, MDR, drawing=None)
    assert _held(llb.checked(s, lot))
    lot, s = _screened(corpus, policies, LDR, drawing=None)
    assert llb.checked(s, lot) is s


def test_the_street_line_is_not_measured(corpus, policies) -> None:  # noqa: F811
    # The building stands 10 ft off the south (street) line, the court 4 ft
    # off the east: only the east line's neighbour matters.
    lot, s = _screened(corpus, policies, LDR)
    assert llb.checked(s, lot) is s


def test_other_places_and_held_lots_are_untouched(corpus, policies) -> None:  # noqa: F811
    lot, s = _screened(corpus, policies, ("oregon_city", "R-6"), jurisdiction="oregon_city", zone="R-6")
    assert llb.checked(s, lot) is s
    lot, s = _screened(corpus, policies, MDR)
    yellow = dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, triage=Triage.yellow),
        signed=dataclasses.replace(s.signed, triage=Triage.yellow),
    )
    assert llb.checked(yellow, lot) is yellow
    red = dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, triage=Triage.red),
        signed=dataclasses.replace(s.signed, triage=Triage.red),
    )
    assert llb.checked(red, lot) is red


def _quoted(quote: str) -> str:
    path, lines = quote.split("#")
    text = (DOCS / path).read_text(encoding="utf-8").splitlines()
    out = []
    for part in lines.split(","):
        a, _, b = part.lstrip("L").partition("-L")
        out.extend(text[int(a) - 1 : int(b or a)])
    return "\n".join(out)


def test_the_config_holds_the_printed_figure() -> None:
    place = llb.places()["or/multnomah/gresham"]
    assert place.width_ft == 10
    assert set(place.keeps_out) == {"building", "lane", "court"}
    assert place.not_owed_beside == {"LDR-5", "LDR-7", "TR", "TLDR"}
    assert "10 ft." in _quoted(place.quote)
    row = " ".join(_quoted("or/multnomah/gresham/9/9.0100.buffering.txt#L224-L228").split())
    assert row.startswith("Single Detached Dwellings - A A A A A A A A")
    uses = _quoted("or/multnomah/gresham/4/4.0120.txt#L12,L20")
    assert "LDR-5" in uses and "TLDR" in uses
    # Multi-family: NP in the first four columns (LDR-5, LDR-7, TR, TLDR).
    assert uses.split("\n")[1].split("Facility")[1].split()[:4] == ["NP", "NP", "NP", "NP"]
