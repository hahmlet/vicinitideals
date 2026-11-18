"""The frost-depth register (FOLLOWUPS 197, flats/config/frost_depth.yaml).

A note only -- never a colour. Every place FLATS screens has a row; every
figure is the source's printed token inside its own quote; a silent place
falls back to the county department's figure, else the state's, flagged with
its level (rulings.yaml 2026-11-18-frost-depth-silent-falls-back); a place not
read gets no fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats import frost

PIPELINE = Path(frost.__file__).parent / "config" / "pipeline.yaml"


def _switched_on() -> list[str]:
    jurisdictions = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))["jurisdictions"]
    return [j for j, on in jurisdictions.items() if on]


def test_every_switched_on_place_has_a_row_and_no_row_is_stray() -> None:
    places = frost.load()["places"]
    assert sorted(places) == sorted(_switched_on())


@pytest.mark.parametrize("figure, expected", [('12"', 12), ("12”", 12), ("18e", 18), ("12 inches", 12), ("7.5 in", 7.5)])
def test_inches_are_derived_from_the_printed_token(figure: str, expected: float) -> None:
    assert frost.inches(figure) == expected


def test_a_token_without_a_number_is_refused() -> None:
    with pytest.raises(ValueError):
        frost.inches("Note a")


def test_the_state_table_is_held_as_printed() -> None:
    """2023 ORSC Table R301.2: Multnomah prints 18 with note e (12 below
    2,500 ft); Clackamas and Washington print 12."""
    state = frost.load()["state"]["counties"]
    multnomah = state["multnomah"]["bands"]
    assert [(b["figure"], b["inches"], b["from_ft"], b["below_ft"]) for b in multnomah] == [
        ("12 inches", 12, None, 2500),
        ("18e", 18, 2500, None),
    ]
    assert [b["inches"] for b in state["clackamas"]["bands"]] == [12]
    assert [b["inches"] for b in state["washington"]["bands"]] == [12]


def test_gresham_practice_is_deeper_than_the_state() -> None:
    note = frost.describe("or/multnomah/gresham", "multnomah")
    assert note["never_a_colour"] is True
    assert (note["outcome"], note["level"], note["kind"], note["inches"]) == ("found", "city", "practice", 18)
    assert note["above_state"] is True and note["state"]["inches"] == 12
    assert "18 inches minimum below finished grade" in note["quote"]
    assert note["cite"].endswith("gresham/id=352/doc.pdf#p1")
    assert "Deeper than the state's 12 in." in note["words"]
    assert "Lot elevation is not held." in note["elevation_words"]


def test_a_silent_city_without_a_county_figure_takes_the_state_figure_flagged() -> None:
    note = frost.describe("or/multnomah/troutdale", "multnomah")
    assert (note["outcome"], note["level"], note["inches"], note["below_ft"]) == ("silent", "state", 12, 2500)
    assert "Flagged state level." in note["words"]
    assert note["read"], "a silent place says what was read"
    # The 2,500 ft condition is honoured as a caveat: the higher band is listed.
    assert note["higher_ground"] == [{"from_ft": 2500, "below_ft": None, "inches": 18, "figure": "18e"}]
    assert "holds below 2,500 ft" in note["elevation_words"] and "From 2,500 ft: 18 in." in note["elevation_words"]


def test_a_silent_city_with_a_county_figure_takes_the_county_figure_flagged() -> None:
    note = frost.describe("or/clackamas/milwaukie", "clackamas")
    assert (note["outcome"], note["level"], note["kind"], note["inches"]) == ("silent", "county", "practice", 12)
    assert note["source_name"] == "Clackamas County Building Codes Division"
    assert [b["inches"] for b in note["higher_ground"]] == [18, 24]
    assert "Flagged county level." in note["words"]


def test_a_place_spanning_counties_falls_back_by_the_lots_county() -> None:
    """Tualatin prints its own figure; Lake Oswego is silent, so a Washington
    County lot of it takes Washington's figure and a Clackamas lot Clackamas'."""
    assert frost.describe("or/clackamas/tualatin", "washington")["level"] == "city"
    wash = frost.describe("or/clackamas/lake-oswego", "washington")
    clack = frost.describe("or/clackamas/lake-oswego", "clackamas")
    assert wash["source_name"] == "Washington County Building Services" and wash["below_ft"] == 400
    assert clack["source_name"] == "Clackamas County Building Codes Division" and clack["below_ft"] == 2500
    assert "From 400 ft the Washington County Building Services figure gives no depth." in wash["elevation_words"]


def test_the_unincorporated_counties_read_their_own_department() -> None:
    clack = frost.describe("or/clackamas/_unincorporated", "clackamas")
    assert (clack["outcome"], clack["level"], clack["inches"]) == ("found", "county", 12)
    mult = frost.describe("or/multnomah/_unincorporated", "multnomah")
    assert (mult["outcome"], mult["level"], mult["inches"]) == ("silent", "state", 12)
    assert any("Gresham" in c for c in mult["caveats"])


def test_a_drawn_figure_says_it_is_drawn() -> None:
    note = frost.describe("or/clackamas/estacada", "clackamas")
    assert note["drawn"] is True and note["inches"] == 12
    assert "drawn on its sample plan" in note["words"]


def test_a_place_not_in_the_register_is_not_resolved_and_claims_no_figure() -> None:
    note = frost.describe("juris_city:FOREST GROVE", "washington")
    assert note["outcome"] == "not_read"
    assert note["inches"] is None and note["level"] is None and note["above_state"] is False
    assert note["words"].startswith("Not resolved:")
    assert note["reference"]["level"] == "county" and note["reference"]["inches"] == 12
    assert "For reference only, the county figure (Washington County Building Services) is 12 in." in note["words"]


def test_a_not_read_place_in_a_silent_county_shows_the_state_figure_for_reference() -> None:
    note = frost.describe("juris_city:MAYWOOD PARK", "multnomah")
    assert note["outcome"] == "not_read" and note["inches"] is None
    assert note["reference"]["level"] == "state"
    assert "For reference only, the state figure for this county is 12 in." in note["words"]


def test_a_city_whose_chapter_was_not_read_is_not_called_silent() -> None:
    # 2026-11-18 coordinator: silent only where the chapter itself was read.
    for jid, county, county_name in (
        ("or/clackamas/oregon-city", "clackamas", "Clackamas County Building Codes Division"),
        ("or/washington/sherwood", "washington", "Washington County Building Services"),
    ):
        note = frost.describe(jid, county)
        assert note["outcome"] == "not_read" and note["inches"] is None and note["level"] is None
        assert note["read"] and note["caveats"]
        assert f"the county figure ({county_name}) is 12 in." in note["words"]
    for jid in ("or/washington/king-city", "or/washington/durham", "or/washington/cornelius"):
        note = frost.describe(jid, "washington")
        assert note["outcome"] == "silent" and note["level"] == "county" and note["inches"] == 12
        assert len(note["read"]) >= 2


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "frost_depth.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def _doc() -> dict:
    return yaml.safe_load(frost.PATH.read_text(encoding="utf-8"))


def test_a_figure_missing_from_its_quote_fails_the_load(tmp_path: Path) -> None:
    doc = _doc()
    doc["places"]["or/multnomah/gresham"]["bands"][0]["figure"] = "24 inches"
    with pytest.raises(ValueError, match="not in its quote"):
        frost.load(_write(tmp_path, doc))


def test_a_silent_place_must_say_what_was_read(tmp_path: Path) -> None:
    doc = _doc()
    doc["places"]["or/multnomah/troutdale"]["read"] = []
    with pytest.raises(ValueError, match="silent needs what was read"):
        frost.load(_write(tmp_path, doc))


def test_bands_must_meet_end_to_start(tmp_path: Path) -> None:
    doc = _doc()
    doc["counties"]["clackamas"]["bands"][1]["from_ft"] = 3000
    with pytest.raises(ValueError, match="meet end to start"):
        frost.load(_write(tmp_path, doc))


def test_the_note_never_reaches_the_screen() -> None:
    """Nothing under flats/ that screens a lot reads the register."""
    root = Path(frost.__file__).parent
    readers = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if "tests" not in p.parts and p.name != "frost.py" and "frost_depth" in p.read_text(encoding="utf-8")
    ]
    readers += [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if "tests" not in p.parts and p.name != "frost.py" and "from flats.frost" in p.read_text(encoding="utf-8")
    ]
    assert readers == []
