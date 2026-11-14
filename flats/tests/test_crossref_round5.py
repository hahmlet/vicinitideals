"""FOLLOWUPS 105 round 5 (2026-11-13): the binding references left open, followed.

Four targets fetched and read, none of them a new standard on the pod:

* Gresham 9.0700, Future Street Plans: a plan required of land divisions,
  design reviews D/E (C at the Manager's call), Special Use Review and three
  townhouse districts; reservation or dedication of a mapped future street is
  the Manager's condition, never a stated distance. No future-street map held.
* Hillsboro Subchapter 12.70, Procedures: review types and the transportation
  studies, whose thresholds (20 trips in an hour, 50 peak-hour trips) four
  homes do not reach.
* Clackamas ZDO 825: redevelopment of a manufactured dwelling park waits on a
  relocation plan and a per-space payment -- money, not ground.
* ORS 197A.140-146 (formerly 197.360-197.380): expedited land division.

The rest are misreads (Gresham "4.115 2", Tigard figure captions, Canby
history notes) or other buildings and paths (signs, child care, stormwater,
the multi-dwelling zones, an inclusionary housing bonus).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.rules.loader import load_rules

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

FETCHED = {
    "or/multnomah/gresham": "9.0700.future-street-plans",
    "or/washington/hillsboro": "cdc.12.70.procedures",
    "or/clackamas/_unincorporated": "zdo.825",
    "or": "ors.197a.140-146",
}

RULED = (
    ("or/multnomah/gresham", "4.115", "misread"),
    ("or/multnomah/gresham", "4.114", "misread"),
    ("or/clackamas/sandy", "197.360", "other_path"),
    ("or/clackamas/milwaukie", "329A", "other_building"),
    ("or/multnomah/_unincorporated", "17.38", "other_path"),
    ("or/multnomah/_unincorporated", "33.120", "other_path"),
    ("or/washington/cornelius", "18.175", "other_building"),
    ("or/washington/tigard", "18.40.10", "misread"),
    ("or/washington/tigard", "18.40.11", "misread"),
    ("or/washington/tigard", "18.40.12", "misread"),
    ("or/washington/tigard", "18.435", "other_building"),
    ("or/clackamas/canby", "10.1.20", "misread"),
    ("or/multnomah/portland", "33.245.040", "narrows_only"),
)


@pytest.fixture(scope="module")
def layers():
    return load_rules(strict=True)


def _lines(path: str) -> list[str]:
    return (DOCS / path).read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize(("layer", "doc_id"), sorted(FETCHED.items()))
def test_each_fetched_target_is_declared_and_stored(layers, layer: str, doc_id: str) -> None:
    path = layers[layer].document_path(doc_id)
    assert path in layers[layer].documents()
    meta = json.loads((DOCS / (path + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["retrieved"] == "2026-11-13"
    assert len(meta["sha256"]) == 64


@pytest.mark.parametrize(("layer", "ref", "outcome"), RULED)
def test_each_reference_is_ruled_with_its_shape(layers, layer: str, ref: str, outcome: str) -> None:
    assert layers[layer].crossrefs[ref].outcome == outcome


def test_the_retired_rulings_are_gone_now_their_sections_are_held(layers) -> None:
    for ref in ("12.70.040", "12.70.110", "12.70.120", "12.70.140", "12.70.150"):
        assert ref not in layers["or/washington/hillsboro"].crossrefs
    assert "9.0700" not in layers["or/multnomah/gresham"].crossrefs


def test_gresham_future_street_plans_reach_land_divisions_and_reviews_not_a_distance() -> None:
    text = _lines("or/multnomah/gresham/9.0700.future-street-plans.txt")
    assert "Type II and Type III tentative partition and subdivision plans" in text[40]
    assert "level D and E" in text[44]
    assert "Townhouse projects in the MDR-24, THR-SW, and HDR-PV" in text[47]
    # Reservation of a future street is the Manager's condition.
    assert "the Manager may require modification" in text[104]
    # And the design districts that also cite it do not take a quadplex.
    downtown = _lines("or/multnomah/gresham/4/4.1102.txt")
    assert "quadplexes" in downtown[13]


def test_hillsboro_studies_start_well_above_four_homes() -> None:
    text = _lines("or/washington/hillsboro/cdc.12.70.procedures.txt")
    assert "20 or more trips in any hour" in text[1861]
    assert "more than 50 peak hour vehicle trips" in text[1920]


def test_clackamas_park_redevelopment_is_a_plan_and_a_payment() -> None:
    text = _lines("or/clackamas/_unincorporated/zdo.825.txt")
    assert text[12] == "825.02 Redevelopment"
    assert "$11,000 for a single-wide" in text[23]


def test_the_expedited_land_division_is_the_renumbered_197_360() -> None:
    text = _lines("or/ors.197a.140-146.txt")
    assert text[0].startswith("197A.140 Expedited land division")
    assert "[Formerly 197.360]" in text[52]


def test_multnomah_maps_no_multi_dwelling_zone(layers) -> None:
    # The 33.120 ruling's premise: the layer's Portland-code districts are all single-dwelling.
    zones = layers["or/multnomah/_unincorporated"].zones
    assert not [z for z in zones if z.startswith(("RM", "RH", "RX"))]
