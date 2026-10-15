"""Law adopted with a later effective date, and Portland's RICAP 11 as the case.

Portland Council adopted RICAP 11 on 2026-08-06 (Ordinance 192213), effective
2026-11-01. It turns Table 150-1's N for Household Living in CI1 into a Y and
puts homes there on the RM1 zone's standards (new 33.150.200, new
33.266.100.B). Title 33 as we hold it predates it, and an ordinance governs
from its effective date whether or not the chapter has been reprinted.

So the zone carries an ``amended:`` entry -- the zone as it will read -- and
the loader puts it in place for any date on or after the effective date
(:func:`flats.rules.loader.law_in_force`). Pinned here: (a) before the date a
CI1 lot screens exactly as it does today; (b) from the date it screens under
the new rule, which is RM1's, with nobody editing anything; (c) no other zone
moves; and that the dates, the quotes and the pages are the exhibit's own.
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
EXHIBIT = "or/multnomah/portland/amended/ricap11.txt"
ADOPTED = date(2026, 8, 6)
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


# --- the amendment as encoded --------------------------------------------------


def test_ci1_carries_ricap_11_with_the_exhibit_s_dates(written) -> None:
    (a,) = written[PORTLAND].zones["CI1"].amended
    assert (a.id, a.adopted, a.effective) == ("ricap11", ADOPTED, EFFECTIVE)
    assert a.prov.url == "https://efiles.portlandoregon.gov/record/18006154/file/document"
    assert a.prov.quote.startswith(EXHIBIT + "#")
    assert "RM1" in a.effect


def test_every_quote_in_the_amendment_lands_on_the_exhibit_page_it_names(written) -> None:
    """Page 12 says when, page 77 the Y, page 79 the RM1 sentence, page 95 the
    parking sentence -- and the stored text says the words, not just the lines."""
    from flats.tests.test_frontage_caps import quoted

    (a,) = written[PORTLAND].zones["CI1"].amended
    pages = read_pages(ProvenanceStore(), EXHIBIT)
    assert pages is not None

    def on(quote: str) -> set[int]:
        spans = quote.partition("#")[2].split(",")
        out = set()
        for span in spans:
            start, _, end = span.lstrip("L").partition("-L")
            out |= {p.n for p in pages.span(int(start), int(end or start))}
        return out

    assert on(a.prov.quote) == {12}
    assert "on August 6, 2026" in quoted(a.prov.quote)
    assert "go into effect on November 1, 2026" in quoted(a.prov.quote)

    use = a.zone.values["quadplex_allowed"]
    assert use.value is True
    assert on(use.prov.quote) == {77}
    assert "Household Living NY" in quoted(use.prov.quote)

    like = a.zone.like
    assert (like.zone, like.wins) == ("RM1", "local")
    assert on(like.prov.quote) == {79, 95}
    words = quoted(like.prov.quote)
    assert "subject to the development standards that apply in the RM1 zone" in words
    assert "subject to the regulations in the chapter that apply in the RM1 zone" in words


def test_the_exhibit_s_pages_are_labelled_by_its_own_footer() -> None:
    """The footer prints "Page 77"; a table title near the top of the same
    sheet ("Table 150-1") is not the page."""
    pages = read_pages(ProvenanceStore(), EXHIBIT)
    labelled = [p for p in pages.pages if p.label]
    assert labelled and all(p.label == str(p.n) for p in labelled)
    assert _label(["Table 150-1", "x", "August 2026   RICAP 11-- As-Adopted   Page 77"]) == "77"
    assert _label(["Page 76   RICAP 11--As-Adopted   August 2026", "x", "266 Parking  266-1"]) == "76"




# --- (a) before the date: as today ---------------------------------------------


def test_before_the_date_ci1_is_the_codified_zone(written, before) -> None:
    """The day before, the loader changes nothing: the block is the one Title
    33 prints, the RICAP entry rides along as pending, and the resolution is
    the same as reading the file with no date at all."""
    zone = before[PORTLAND].zones["CI1"]
    assert zone == written[PORTLAND].zones["CI1"]
    assert zone.in_force is None
    assert [a.id for a in zone.pending(DAY_BEFORE)] == ["ricap11"]
    assert [a for a in amendments_in_force(before) if a.startswith(PORTLAND)] == []

    got = RuleSet(before).resolve(PORTLAND, "CI1").values
    assert got["quadplex_allowed"].value is False
    assert (got["setback_front_ft"].value, got["max_far"].value, got["max_height_ft"].value) == (15, 0.5, 75)


def test_a_ci1_lot_before_the_date_screens_as_today(written, before) -> None:
    today = _screen(written, "CI1")
    day_before = _screen(before, "CI1")
    assert _said(day_before) == _said(today)
    # RED at the use gate once signed -- the answer CI1 has always had.
    assert day_before.signed.colour.value == "red"
    assert "USE_PROHIBITED" in day_before.signed.reasons


# --- (b) from the date: the new rule, with no edit -----------------------------


def test_from_the_date_ci1_reads_as_rm1_and_allows_the_use(after) -> None:
    zone = after[PORTLAND].zones["CI1"]
    assert zone.in_force == "ricap11"
    assert [a.id for a in zone.amended] == ["ricap11"]
    assert [a for a in amendments_in_force(after) if a.startswith(PORTLAND)] == [f"{PORTLAND}:CI1:ricap11"]

    rules = RuleSet(after)
    ci1 = rules.resolve(PORTLAND, "CI1")
    rm1 = rules.resolve(PORTLAND, "RM1")
    assert ci1.values["quadplex_allowed"].value is True
    assert ci1.borrowed_from == ("RM1",)
    # Every standard but the use is RM1's, with RM1's own citation and levers:
    # 33.150.200 imports the RM1 standards whole and 33.266.100.B the parking.
    assert ci1.values["quadplex_allowed"].via is None
    assert ci1.values["quadplex_allowed"].prov.quote.startswith(EXHIBIT)
    for name, value in rm1.values.items():
        if name == "quadplex_allowed":
            continue
        mine = ci1.values[name]
        assert (mine.value, mine.levers, mine.prov.quote) == (value.value, value.levers, value.prov.quote), name
    assert set(ci1.values) == set(rm1.values)
    assert ci1.exempted == rm1.exempted
    assert ci1.values["min_lot_sqft"].value == 4000  # RM1's, not 33.150.202's "no minimum"
    assert ci1.values["parking_max_per_unit"].value == 1.35


def test_the_codified_block_s_footnote_caps_do_not_follow_the_amendment(written, after) -> None:
    """Table 150-2 note [3] capped CI1's own figures; a home on RM1 standards
    is not under Table 150-2, and nothing in the exhibit's Table 150-1 row
    carries a bracket. The borrowed values keep RM1's caps."""
    old = RuleSet(written).resolve(PORTLAND, "CI1").values
    assert "site_specific_limitation" in old["max_far"].levers
    new = RuleSet(after).resolve(PORTLAND, "CI1").values
    assert not any("site_specific_limitation" in v.levers for v in new.values())


def test_a_ci1_lot_from_the_date_screens_under_the_new_rule(after) -> None:
    ci1 = _screen(after, "CI1")
    rm1 = _screen(after, "RM1")
    assert "USE_PROHIBITED" not in ci1.signed.reasons
    # The same lot in RM1, the same answer: the zone IS RM1 for this building.
    assert _said(ci1) == _said(rm1)


def test_the_date_comes_from_the_calendar_or_the_pin(monkeypatch) -> None:
    monkeypatch.delenv(LAW_ON_ENV, raising=False)
    assert law_on(DAY_BEFORE) == DAY_BEFORE
    monkeypatch.setenv(LAW_ON_ENV, "2026-11-01")
    assert law_on(DAY_BEFORE) == EFFECTIVE
    layers = load_rules(on=law_on())
    assert layers[PORTLAND].zones["CI1"].in_force == "ricap11"


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


# --- (c) nothing else moves ----------------------------------------------------


def test_no_other_zone_moves_on_the_date(before, after) -> None:
    moved = {
        (layer_id, code)
        for layer_id in after
        for code in after[layer_id].zones
        if after[layer_id].zones[code] != before[layer_id].zones.get(code)
    }
    assert moved == {(PORTLAND, "CI1")}
    # Every other layer is the same on both days. (Equal, not identical: a
    # layer with an amendment already in force on both sides -- Gladstone's
    # Ordinance 1545 -- is rebuilt each time.)
    assert all(after[k] == before[k] for k in after if k != PORTLAND)


def test_no_other_portland_zone_resolves_differently(before, after) -> None:
    old, new = RuleSet(before), RuleSet(after)
    for code in sorted(after[PORTLAND].zones):
        if code == "CI1":
            continue
        a, b = old.resolve(PORTLAND, code), new.resolve(PORTLAND, code)
        assert {k: (v.value, v.levers) for k, v in a.values.items()} == {
            k: (v.value, v.levers) for k, v in b.values.items()
        }, code
        assert (a.verdict, a.reason) == (b.verdict, b.reason), code


def test_a_neighbouring_zone_s_lot_screens_the_same_on_both_sides_of_the_date(before, after) -> None:
    for zone in ("CI2", "RM1", "R5"):
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
