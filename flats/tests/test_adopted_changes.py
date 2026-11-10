"""Law adopted with a later effective date, and Portland's RICAP 11 as the case.

Portland Council adopted RICAP 11 on 2026-08-06 (Ordinance 192213), effective
2026-11-01. It turns Table 150-1's N for Household Living in CI1 into a Y and
puts homes there on the RM1 zone's standards (new 33.150.200, new
33.266.100.B). From 2026-10-15 until Title 33 was reprinted the zone carried
an ``amended:`` entry -- the zone as it would read -- and the loader put it
in place from the effective date (:func:`flats.rules.loader.law_in_force`).

The 11/1/26 reprint prints the change, so on 2026-11-09 (pdx-drift, FOLLOWUPS
165) the entry was taken off and the CI1 block now quotes the chapter itself.
Pinned here: CI1 reads as RM1 with the use allowed, quoted from the reprinted
33.150; no entry is left pending, so nothing moves on the effective date any
more; the exhibit stays stored with its pages as the record of the change;
and the mechanism itself, on a layer of its own.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from flats.ingest import batch
from flats.provenance.pages import _label, read as read_pages
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import (
    LAW_ON_ENV,
    amendments_in_force,
    law_in_force,
    law_on,
    load_layer,
    load_rules,
)
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
GLADSTONE = "or/clackamas/gladstone"
EXHIBIT = "or/multnomah/portland/amended/ricap11.txt"
CHAPTER = "or/multnomah/portland/33.150.txt"
EFFECTIVE = date(2026, 11, 1)
DAY_BEFORE = date(2026, 10, 31)


@pytest.fixture(scope="module")
def written():
    return load_rules()


@pytest.fixture(scope="module")
def before(written):
    return law_in_force(written, DAY_BEFORE)


@pytest.fixture(scope="module")
def after(written):
    return law_in_force(written, EFFECTIVE)


def _screen(layers, zone: str):
    """A plain 80 x 120 ft interior Portland lot in ``zone``, screened with the
    catalog pod, as the bridge screens it."""
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_fire import bridge_row, pod

    rules = RuleSet(layers)
    lot = lot_from_row(bridge_row(zone=zone), rules.layers)
    (s,) = screen_lot(
        lot, [pod()], rules=rules, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    return s


def _said(s) -> tuple:
    """What a screen answered, as the map shows it and as it stands today."""
    return (
        s.screening.colour, tuple(s.screening.reasons), s.signed.colour, tuple(s.signed.reasons),
    )


# --- RICAP 11, codified ---------------------------------------------------------


def test_ci1_carries_no_pending_amendment_now_the_chapter_is_reprinted(written, after) -> None:
    zone = written[PORTLAND].zones["CI1"]
    assert zone.amended == ()
    assert zone.in_force is None
    assert [a for a in amendments_in_force(after) if a.startswith(PORTLAND)] == []


def test_ci1_reads_as_rm1_and_allows_the_use_from_the_reprinted_chapter(written) -> None:
    from flats.tests.test_frontage_caps import quoted

    rules = RuleSet(written)
    ci1 = rules.resolve(PORTLAND, "CI1")
    rm1 = rules.resolve(PORTLAND, "RM1")
    use = ci1.values["quadplex_allowed"]
    assert use.value is True and use.via is None
    assert use.prov.quote.startswith(CHAPTER + "#")
    words = quoted(use.prov.quote)
    assert words.startswith("Use Categories CI1 CI2 IR Household Living Y Y Y"), words
    assert ci1.borrowed_from == ("RM1",)
    like = written[PORTLAND].zones["CI1"].like
    assert (like.zone, like.wins) == ("RM1", "local")
    assert like.prov.quote.startswith(CHAPTER + "#")
    assert "subject to the development standards that apply in the RM1 zone" in quoted(like.prov.quote)
    # Every standard but the use is RM1's, with RM1's own citation and levers:
    # 33.150.200 imports the RM1 standards whole and 33.266.100.B the parking.
    for name, value in rm1.values.items():
        if name == "quadplex_allowed":
            continue
        mine = ci1.values[name]
        assert (mine.value, mine.levers, mine.prov.quote) == (value.value, value.levers, value.prov.quote), name
    assert set(ci1.values) == set(rm1.values)
    assert ci1.exempted == rm1.exempted
    assert ci1.values["min_lot_sqft"].value == 4000  # RM1's, not 33.150.202's "no minimum"
    assert ci1.values["parking_max_per_unit"].value == 1.35


def test_the_parking_chapter_says_the_same_for_ci1_homes() -> None:
    """33.266.100.B, cited in the zone's comment beside `like:`."""
    from flats.tests.test_frontage_caps import quoted

    words = quoted("or/multnomah/portland/33.266.txt#L38-L40")
    assert "Household Living and Group Living uses in the CI1 zone" in words
    assert "subject to the regulations in the chapter that apply in the RM1 zone" in words


def test_table_150_2_s_caps_do_not_reach_a_ci1_home(written) -> None:
    """Table 150-2's notes capped CI1's own figures; a home on RM1 standards
    is not under Table 150-2. The borrowed values keep RM1's caps."""
    got = RuleSet(written).resolve(PORTLAND, "CI1").values
    assert not any(
        "site_specific_limitation" in v.levers for name, v in got.items() if name != "quadplex_allowed"
    )


def test_a_ci1_lot_screens_as_the_same_lot_in_rm1(written) -> None:
    ci1 = _screen(written, "CI1")
    rm1 = _screen(written, "RM1")
    assert "USE_PROHIBITED" not in ci1.signed.reasons
    assert _said(ci1) == _said(rm1)


def test_the_exhibit_stays_stored_with_its_pages() -> None:
    """The record of the change: page 12 says when, page 77 the Y."""
    from flats.tests.test_frontage_caps import quoted

    pages = read_pages(ProvenanceStore(), EXHIBIT)
    assert pages is not None
    assert {p.n for p in pages.span(344, 349)} == {12}
    words = quoted(EXHIBIT + "#L344-L346,L348-L349")
    assert "on August 6, 2026" in words and "go into effect on November 1, 2026" in words
    assert "Household Living NY" in quoted(EXHIBIT + "#L1987,L1989,L1991")


def test_the_exhibit_s_pages_are_labelled_by_its_own_footer() -> None:
    """The footer prints "Page 77"; a table title near the top of the same
    sheet ("Table 150-1") is not the page."""
    pages = read_pages(ProvenanceStore(), EXHIBIT)
    labelled = [p for p in pages.pages if p.label]
    assert labelled and all(p.label == str(p.n) for p in labelled)
    assert _label(["Table 150-1", "x", "August 2026   RICAP 11-- As-Adopted   Page 77"]) == "77"
    assert _label(["Page 76   RICAP 11--As-Adopted   August 2026", "x", "266 Parking  266-1"]) == "76"


def test_the_date_comes_from_the_calendar_or_the_pin(monkeypatch) -> None:
    monkeypatch.delenv(LAW_ON_ENV, raising=False)
    assert law_on(DAY_BEFORE) == DAY_BEFORE
    monkeypatch.setenv(LAW_ON_ENV, "2026-11-01")
    assert law_on(DAY_BEFORE) == EFFECTIVE
    layers = load_rules(on=law_on())
    assert layers[GLADSTONE].zones["R7.2"].in_force == "ord1545"


def test_the_answer_cache_does_not_replay_old_law_under_new(tmp_path: Path) -> None:
    """Nothing in the code or the rule files changes on November 1, so the
    run key has to: the first run under the new law must screen afresh."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    old = batch.run_key(step_deg=1.0, inputs={}, package=pkg, law=[])
    new = batch.run_key(step_deg=1.0, inputs={}, package=pkg, law=[f"{PORTLAND}:CI1:ricap11"])
    assert old != new
    assert batch.run_key(step_deg=1.0, inputs={}, package=pkg) == old


# --- nothing moves on the date any more ---------------------------------------


def test_nothing_moves_on_ricap_11_s_date_now_it_is_codified(before, after) -> None:
    # Equal, not identical: a layer with an amendment already in force on both
    # sides -- Gladstone's Ordinance 1545 -- is rebuilt each time.
    assert all(after[k] == before[k] for k in after)


def test_no_portland_zone_resolves_differently_across_the_date(before, after) -> None:
    old, new = RuleSet(before), RuleSet(after)
    for code in sorted(after[PORTLAND].zones):
        a, b = old.resolve(PORTLAND, code), new.resolve(PORTLAND, code)
        assert {k: (v.value, v.levers) for k, v in a.values.items()} == {
            k: (v.value, v.levers) for k, v in b.values.items()
        }, code
        assert (a.verdict, a.reason) == (b.verdict, b.reason), code


def test_a_lot_screens_the_same_on_both_sides_of_the_date(before, after) -> None:
    for zone in ("CI1", "CI2", "RM1", "R5"):
        assert _said(_screen(before, zone)) == _said(_screen(after, zone)), zone


# --- the mechanism, on a layer of its own -------------------------------------


def _layer(tmp_path: Path, amended: list[dict]) -> tuple[object, list[str]]:
    import yaml

    root = tmp_path / "jurisdictions"
    path = root / "or" / "test" / "town.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "cite_default": {"cite": "TC 1", "url": "https://town.example/code", "retrieved": "2026-01-01"},
                "zones": {
                    "R1": {"quadplex_allowed": {"value": False, "quote": "or/test/tc.txt#L1"}},
                    "R2": {"quadplex_allowed": {"value": True, "quote": "or/test/tc.txt#L2"}},
                    "C1": {"quadplex_allowed": {"value": False, "quote": "or/test/tc.txt#L3"}, "amended": amended},
                },
            }
        ),
        encoding="utf-8",
    )
    problems: list[str] = []
    return load_layer(path, root, problems), problems


def _entry(**over) -> dict:
    base = {
        "id": "ord1",
        "label": "Ordinance 1",
        "adopted": date(2026, 1, 1),
        "effective": date(2026, 2, 1),
        "url": "https://town.example/ord1.pdf",
        "cite": "Ordinance 1, p. 2",
        "quote": "or/test/ord1.txt#L5",
        "effect": "Homes allowed in C1, on R2's standards.",
        "zone": {
            "like": {"zone": "R2", "quote": "or/test/ord1.txt#L6"},
            "quadplex_allowed": {"value": True, "quote": "or/test/ord1.txt#L7"},
        },
    }
    base.update(over)
    return base


def test_an_amendment_is_parsed_the_day_it_is_written(tmp_path: Path) -> None:
    layer, problems = _layer(tmp_path, [_entry()])
    assert problems == []
    (a,) = layer.zones["C1"].amended
    assert a.zone.like.zone == "R2"
    # Its block cites the adopting text by default, not the codified chapter.
    assert a.zone.values["quadplex_allowed"].prov.url == "https://town.example/ord1.pdf"
    assert layer.zones["C1"].values["quadplex_allowed"].value is False
    switched = law_in_force({"t": layer}, date(2026, 2, 1))["t"]
    assert switched.zones["C1"].values["quadplex_allowed"].value is True
    assert switched.zones["R1"] is layer.zones["R1"]


@pytest.mark.parametrize(
    ("over", "said"),
    [
        ({"quote": None}, "quote the adopting text"),
        ({"effective": date(2025, 12, 1)}, "cannot take effect before it was adopted"),
        ({"zone": {"quadplex_allowed": {"value": True}}}, "must be quoted"),
        ({"zone": None}, "expected the zone block"),
        ({"when": "soon"}, "unknown key"),
    ],
)
def test_an_amendment_that_cannot_be_defended_is_a_load_problem(
    tmp_path: Path, over: dict, said: str
) -> None:
    entry = {k: v for k, v in _entry(**over).items() if v is not None}
    _layer_obj, problems = _layer(tmp_path, [entry])
    assert any(said in p for p in problems), problems


def test_the_latest_amendment_in_force_wins(tmp_path: Path) -> None:
    second = _entry(
        id="ord2",
        adopted=date(2026, 3, 1),
        effective=date(2026, 4, 1),
        zone={"quadplex_allowed": {"value": False, "quote": "or/test/ord2.txt#L1"}},
    )
    layer, problems = _layer(tmp_path, [second, _entry()])
    assert problems == []
    assert [a.id for a in layer.zones["C1"].amended] == ["ord1", "ord2"]
    on = {d: law_in_force({"t": layer}, d)["t"].zones["C1"] for d in (date(2026, 1, 31), date(2026, 2, 1), date(2026, 4, 1))}
    assert [z.in_force for z in on.values()] == [None, "ord1", "ord2"]
    assert json.dumps([z.values["quadplex_allowed"].value for z in on.values()]) == "[false, true, false]"
