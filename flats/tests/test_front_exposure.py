"""Step 3 of Steph's ruling of 2026-09-19 (HUMAN_TODO 21, rulings.yaml
``2026-09-19-orientation-choice-order``): where the code leaves the front to
the applicant and two fronts tie on colour and stall band, the one whose
court is least exposed to a street wins (FOLLOWUPS 6)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flats.geom.edges import EdgeClass
from flats.ingest import quadfit
from flats.ingest.quadfit import court_street_ft, least_exposed


def _edge(cls, x1, y1, x2, y2, alley=False):
    return SimpleNamespace(cls=cls, x1=x1, y1=y1, x2=x2, y2=y2, alley=alley)


#: A 100 x 100 corner lot: streets along the south (y=0) and west (x=0).
CORNER = SimpleNamespace(
    edges=SimpleNamespace(
        edges=[
            _edge(EdgeClass.front, 0, 0, 100, 0),
            _edge(EdgeClass.street_side, 0, 0, 0, 100),
            _edge(EdgeClass.side, 100, 0, 100, 100),
            _edge(EdgeClass.rear, 0, 100, 100, 100, alley=True),
        ]
    )
)


def _screened(front=10.0, street_side=10.0):
    sb = SimpleNamespace(front_ft=front, street_side_ft=street_side)
    return SimpleNamespace(envelope=SimpleNamespace(setbacks=sb))


def _box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def test_a_court_against_the_side_street_setback_scores_its_run() -> None:
    drawing = {"fits": True, "court": _box(10, 60, 40, 90)}
    # The edge at x=10 stands on the side street's 10 ft strip (plus 2 ft),
    # and the ends reach 2 ft into it: within the five-foot comparison step.
    assert court_street_ft(_screened(), drawing, CORNER) == pytest.approx(34.0)


def test_a_court_off_every_street_scores_zero_and_the_alley_never_counts() -> None:
    drawing = {"fits": True, "court": _box(50, 70, 90, 100)}
    assert court_street_ft(_screened(), drawing, CORNER) == 0.0
    assert court_street_ft(_screened(), {"fits": True, "court": None}, CORNER) == 0.0
    assert court_street_ft(_screened(), {"fits": False, "court": _box(0, 0, 1, 1)}, CORNER) is None


def test_least_exposed_breaks_a_tie_on_colour_and_band(monkeypatch) -> None:
    a, b, c = SimpleNamespace(name="a"), SimpleNamespace(name="b"), SimpleNamespace(name="c")
    ranks = {"a": (0, 0, 0, 0, -30.0), "b": (0, 0, 0, 0, -10.0), "c": (1, 0, 0, 0, -50.0)}
    drawn = {
        "a": {"fits": True, "court": _box(10, 60, 40, 90)},   # along the side street
        "b": {"fits": True, "court": _box(50, 70, 90, 100)},  # on no street
        "c": {"fits": True, "court": _box(50, 70, 90, 100)},
    }
    monkeypatch.setattr(quadfit, "_front_rank", lambda s: ranks[s.name])
    monkeypatch.setattr(quadfit, "drawing_for", lambda s, f: drawn[s.name])
    monkeypatch.setattr(quadfit, "court_street_ft",
                        lambda s, d, lot: court_street_ft(_screened(), d, CORNER))
    won, fitter, drawing = least_exposed([(a, "fa"), (b, "fb"), (c, "fc")], CORNER)
    # a has more room to spare, but b's court is on no street; c is a worse colour.
    assert (won.name, fitter) == ("b", "fb")
    assert drawing is drawn["b"]


def test_least_exposed_keeps_the_rank_when_nothing_ties(monkeypatch) -> None:
    a, b = SimpleNamespace(name="a"), SimpleNamespace(name="b")
    ranks = {"a": (0, 0, 0, 1, -30.0), "b": (0, 0, 0, 0, -10.0)}
    monkeypatch.setattr(quadfit, "_front_rank", lambda s: ranks[s.name])

    def no_draw(s, f):
        raise AssertionError("a plan that does not tie is not drawn")

    monkeypatch.setattr(quadfit, "drawing_for", no_draw)
    won, _, drawing = least_exposed([(a, 1), (b, 2)], CORNER)
    assert won.name == "b" and drawing is None


def test_equal_exposure_falls_back_to_room_to_spare(monkeypatch) -> None:
    a, b = SimpleNamespace(name="a"), SimpleNamespace(name="b")
    ranks = {"a": (0, 0, 0, 0, -30.0), "b": (0, 0, 0, 0, -10.0)}
    court = {"fits": True, "court": _box(50, 70, 90, 100)}
    monkeypatch.setattr(quadfit, "_front_rank", lambda s: ranks[s.name])
    monkeypatch.setattr(quadfit, "drawing_for", lambda s, f: court)
    monkeypatch.setattr(quadfit, "court_street_ft", lambda s, d, lot: 0.0)
    won, _, _ = least_exposed([(a, 1), (b, 2)], CORNER)
    assert won.name == "a"
