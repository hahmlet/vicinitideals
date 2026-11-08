"""The historic lists outside Portland (FOLLOWUPS 87,
:mod:`flats.geom.historic_lists`): the rows, what each city's code says a
listing does, the matcher, and the RED and YELLOW they put on a lot."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest
import shapely

from flats.geom import historic_lists as hl

ROOT = Path(__file__).resolve().parents[2]
HISTORIC_DIR = ROOT / "flats" / "config" / "historic"

# Every row of a list that names no lot, per list. A row that names no lot is
# reported, never dropped: move this only with the match run that moved it.
# 2026-11-06: Gresham and Troutdale matched on the local Multnomah table; the
# rest wait on the county tables (the 137 step in the hand-off).
# After the 2026-11-06 match on the full lot table (137).
# 2026-11-06, round 2: Gresham's five placed by the state's own record of each
# (protection.yaml state_points). The state files matched on the local table, so
# their Clackamas and Washington rows wait on the same 137 step.
UNMATCHED: dict[str, int] = {
    "gresham": 0,
    "tigard": 3,
    "troutdale": 3,
    "washington-county": 0,
    "west-linn": 0,
    "nps-2026-11-06": 95,
    "shpo-2026-11-06": 4543,
}

WASHCO_LOT = "1S123AA00100"
# 410 N Main Ave, Carnegie Library: a Gresham Class 1 landmark.
PROTECTED_LOT = "1S3E10BC  -00700"
# 765 SW Walters Rd, listed; the county has 765 SW Walters Dr.
NEAR_ADDRESS_LOT = "1S3E10CC  -04400"
# 23500 SE Stark St, the 13-Mile Marker: an object, on a protected list.
OBJECT_LOT = "1S3E03AB  -00200"
# 726 E Historic CRH, Harlow House: Troutdale, whose 6.515.E is a Type III case.
TROUTDALE_LOT = "1N3E25DB  -00800"
# 3645 SE Harlow Ct, an Oregon white oak: on the list, and not a building.
TROUTDALE_TREE_LOT = "1S3E01BA  -08500"
# 11333 SW Gaarde St: Tigard's Historic Sites map, nothing held shows the overlay.
UNSETTLED_LIST_LOT = "2S103DC01700"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _lines(cite: str) -> str:
    """The stored lines a ``path#Lnn`` or ``path#Lnn-Lmm`` cite names."""
    path, _, span = cite.partition("#")
    got = re.fullmatch(r"L(\d+)(?:-L(\d+))?", span)
    assert got, cite
    low = int(got.group(1))
    high = int(got.group(2) or low)
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    assert high <= len(lines), cite
    return _flat(" ".join(lines[low - 1 : high]))


def _quoted(policy: dict) -> list[tuple[str, str]]:
    out = [(policy["cite"], policy["quote"])]
    if "owner_consent" in policy:
        out.append((policy["owner_consent"], policy["owner_quote"]))
    if "demolition" in policy:
        out.append((policy["demolition"], policy["demolition_quote"]))
    if "applies" in policy:
        out.append((policy["applies"], policy["applies_quote"]))
    if policy.get("not_buildings"):
        out.append((policy["not_buildings"]["cite"], policy["not_buildings"]["quote"]))
    out.extend((x["cite"], x["quote"]) for x in policy.get("also", ()))
    return out


def _state_quotes() -> list[tuple[str, str, str]]:
    state = hl.load_state_policy()
    named: list[tuple[str, dict]] = [*state["classes"].items()]
    named += [(n, p) for n, p in state["places"].items() if "cite" in p]
    named += [(x["note"], x) for x in state["rule"]]
    return [(name, cite, quote) for name, policy in named for cite, quote in _quoted(policy)]


# --- the rows ----------------------------------------------------------------


def test_historic_list_csvs_parse_with_expected_columns() -> None:
    files = sorted(HISTORIC_DIR.glob("*.csv"))
    assert files
    for path in files:
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            assert tuple(reader.fieldnames or ()) == hl.COLUMNS
            rows = list(reader)
        assert all(row["source"] for row in rows)
        assert all(row["match_method"] in hl.MATCH_METHODS for row in rows)


def test_every_list_has_a_reading_and_every_row_loads() -> None:
    policy = hl.load_policy()
    assert {p.stem for p in HISTORIC_DIR.glob("*.csv")} == set(policy)
    assert sum(x.list_name in policy for x in hl.load_lists()) == 85


def test_a_list_row_with_no_lot_is_reported_not_dropped(tmp_path) -> None:
    by_list: dict[str, int] = dict.fromkeys(UNMATCHED, 0)
    for x in hl.unmatched():
        by_list[x.list_name] += 1
    assert by_list == UNMATCHED

    counts = hl.write_report([{"TLID": PROTECTED_LOT}], tmp_path)
    assert counts["unmatched"] == sum(UNMATCHED.values())
    assert counts["on_lot"] == len(hl.listings_on(PROTECTED_LOT))
    assert sum(counts.values()) == len(hl.load_lists())
    with (tmp_path / hl.REPORT_NAME).open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == len(hl.load_lists())
    assert {r["status"] for r in rows} == {"on_lot", "not_in_run", "unmatched"}


def test_multnomah_listed_tlids_exist_in_the_local_lot_table() -> None:
    local_candidates = (
        ROOT / "data" / "quadfit" / "s1_lots.parquet",
        ROOT.parent.parent / "vicinitideals" / "data" / "quadfit" / "s1_lots.parquet",
    )
    lot_data = next((path for path in local_candidates if path.is_file()), None)
    if lot_data is None:
        pytest.skip("local s1_lots.parquet data is not present in CI")

    # The local table is Multnomah's alone.
    multnomah = {n for n, p in hl.load_policy().items() if p["county"] == "multnomah"}
    lot_ids = {hl.compact(t) for t in pd.read_parquet(lot_data, columns=["TLID"])["TLID"]}
    listed = {hl.compact(t) for x in hl.load_lists() if x.list_name in multnomah for t in x.tlids}
    assert listed and listed <= lot_ids


# --- what the code says ------------------------------------------------------


@pytest.mark.parametrize("name", sorted(hl.load_policy()))
def test_every_cite_quotes_the_stored_code(name) -> None:
    for cite, quote in _quoted(hl.load_policy()[name]):
        assert _flat(quote) in _lines(cite), f"{cite}: {quote}"


@pytest.mark.parametrize(("name", "cite", "quote"), _state_quotes())
def test_every_state_cite_quotes_the_stored_text(name, cite, quote) -> None:
    assert _flat(quote) in _lines(cite), f"{name}: {cite}: {quote}"


def test_west_linn_list_is_the_citys_own_page() -> None:
    page = (ROOT / hl.load_policy()["west-linn"]["also"][0]["cite"].partition("#")[0]).read_text(encoding="utf-8")
    rows = [x for x in hl.load_lists() if x.list_name == "west-linn"]
    assert len(rows) == 25
    for x in rows:
        number, *rest = x.address.split()
        assert re.search(rf"^{number}\s+{re.escape(rest[0])}", page, re.M | re.I), x.address


def test_only_the_codes_that_clearly_protect_read_protected() -> None:
    readings = {n: p["reading"] for n, p in hl.load_policy().items()}
    assert readings == {
        "gresham": hl.PROTECTED,
        "west-linn": hl.PROTECTED,
        "troutdale": hl.PROTECTED,
        "tigard": hl.DOUBTFUL,
        "washington-county": hl.DOUBTFUL,
    }


def test_gresham_objects_are_the_rows_its_table_calls_objects() -> None:
    table = (ROOT / hl.load_policy()["gresham"]["cite"].partition("#")[0]).read_text(encoding="utf-8")
    objects = {" ".join(line.split()) for line in table.splitlines() if re.search(r"\bObject\s*$", line)}
    assert len(objects) == 5
    ids = set(hl.load_policy()["gresham"]["not_buildings"]["ids"])
    rows = {x.listing_id: x for x in hl.load_lists() if x.list_name == "gresham"}
    for listing_id in ids:
        assert any(rows[listing_id].name in line for line in objects), listing_id
        assert rows[listing_id].standing == hl.DOUBTFUL


# --- the lots ----------------------------------------------------------------


def test_a_taxlot_is_found_however_its_spaces_fall() -> None:
    assert hl.listings_on("1S3E10BC-00700") == hl.listings_on(PROTECTED_LOT) != ()
    assert hl.listings_on("1S3E10BC  -99999") == ()


@pytest.mark.parametrize(
    ("tlid", "standing"),
    [
        (PROTECTED_LOT, hl.PROTECTED),
        (WASHCO_LOT, hl.DOUBTFUL),
        (NEAR_ADDRESS_LOT, hl.DOUBTFUL),
        (OBJECT_LOT, hl.DOUBTFUL),
        (TROUTDALE_LOT, hl.PROTECTED),
        (TROUTDALE_TREE_LOT, hl.DOUBTFUL),
        (UNSETTLED_LIST_LOT, hl.DOUBTFUL),
    ],
)
def test_the_lots_read_as_the_code_and_the_match_allow(tlid, standing) -> None:
    listing = next(x for x in hl.listings_on(tlid) if x.list_name in hl.load_policy())
    assert listing.standing == standing


def test_a_fuzzy_match_on_a_protected_list_is_never_red() -> None:
    for x in hl.load_lists():
        if x.method in hl.UNSURE_MATCH:
            assert x.standing == hl.DOUBTFUL, x.said()


@lru_cache(maxsize=1)
def _corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def _screened(tlid: str, zone: str = "R-5", jurisdiction: str | None = None):
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_quadfit_bridge import pod, row

    corpus = _corpus()
    side = 300.0
    lot = shapely.box(0, 0, side, side)
    fields = {"TLID": tlid, "zone": zone, "area_sqft": side * side, "lot_wkb": shapely.to_wkb(lot)}
    if jurisdiction is not None:
        fields["jurisdiction"] = jurisdiction
    r = row(**fields)
    (s,) = screen_lot(
        lot_from_row(r, corpus.layers),
        [pod()],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s


def test_a_protected_listing_is_red_and_says_why() -> None:
    from flats.score.flags import Colour

    s = _screened(PROTECTED_LOT, zone="R-5", jurisdiction="gresham")
    assert s.signed.colour is Colour.red
    assert hl.LISTED_REASON in s.signed.reasons
    bind = next(b for b in s.signed.binds if b.check == hl.LISTED_CHECK)
    assert "5.0300" in bind.source and "Carnegie Library" in bind.source
    # Run over its own answer, nothing is added twice.
    again = hl.checked(s, PROTECTED_LOT)
    assert again.signed.binds == s.signed.binds and again.signed.reasons == s.signed.reasons


def test_the_known_washington_county_lot_is_never_green() -> None:
    """1S123AA00100, the live case FOLLOWUPS 87 names: GREEN in run 99."""
    from flats.score.flags import Colour

    s = _screened(WASHCO_LOT, zone="R-5", jurisdiction="washington_unincorporated")
    assert s.signed.colour is not Colour.green
    flag = next(f for f in s.signed.flags if f.code == hl.UNSETTLED_FLAG)
    assert "373" in flag.source and "L9100610" in flag.source
    assert hl.UNSETTLED_REASON in s.signed.reasons


def test_a_lot_on_no_list_is_left_as_it_was() -> None:
    s = _screened("1S3E10BC  -99999", zone="R-5", jurisdiction="gresham")
    assert hl.checked(s, "1S3E10BC  -99999") is s
    assert not any(b.check == hl.LISTED_CHECK for b in s.signed.binds)
    assert not any(f.code == hl.UNSETTLED_FLAG for f in s.signed.flags)


def test_doubtful_alone_turns_green_to_yellow_and_never_to_red() -> None:
    """On a screen that was green, whatever the rest of the corpus says today."""
    import dataclasses

    from flats.score.flags import Colour
    from flats.score.screen import Triage

    s = _screened("1S3E10BC  -99999", zone="R-5", jurisdiction="gresham")
    clean = dataclasses.replace(
        s.signed, triage=Triage.green, binds=(), flags=(), reasons=()
    )
    s = dataclasses.replace(s, signed=clean, screening=clean)
    assert s.signed.colour is Colour.green

    yellow = hl.checked(s, WASHCO_LOT)
    assert yellow.signed.colour is Colour.yellow and yellow.signed.triage is Triage.yellow
    red = hl.checked(s, PROTECTED_LOT)
    assert red.signed.colour is Colour.red and red.signed.triage is Triage.red


# --- the matcher -------------------------------------------------------------


def _lots(*rows: tuple[str, str]) -> dict:
    frame = {
        "TLID": [r[0] for r in rows],
        "SITEADDR": [r[1] for r in rows],
        "SITECITY": ["GRESHAM"] * len(rows),
        "JURIS_CITY": ["GRESHAM"] * len(rows),
    }
    return hl.lots_by_street(frame, ["Gresham"])


def test_the_matcher_grades_how_sure_it_is() -> None:
    lots = _lots(
        ("A", "410 N MAIN AVE"),
        ("B", "722-876 NE 162ND AVE"),
        ("C", "765 SW WALTERS DR"),
        ("D", "6920 SE 77TH AVE UNIT #A"),
    )
    assert hl.match_address("410 N Main Ave.", lots)[:2] == (("A",), "address-exact")
    assert hl.match_address("722 NE 162nd Ave.", lots)[:2] == (("B",), "address-range")
    assert hl.match_address("765 SW Walters Rd.", lots)[:2] == (("C",), "address-fuzzy")
    assert hl.match_address("6920 S.E. 77th Avenue", lots)[:2] == (("D",), "address-exact")
    assert hl.match_address("999 N Main Ave.", lots)[:2] == ((), "none")


def test_a_number_on_the_far_side_of_the_street_is_not_in_a_range() -> None:
    """1420 SE Roberts: the 2005 apartments at 1411-1429 SE Roberts Dr are not it;
    the 1895 house at 1420 SE Roberts Ave is, on a suffix that disagrees."""
    lots = _lots(("APTS", "1411-1429 SE ROBERTS DR"), ("HOUSE", "1420 SE ROBERTS AVE"))
    assert hl.match_address("1420 SE Roberts Dr.", lots)[:2] == (("HOUSE",), "address-fuzzy")


def test_an_address_two_lots_share_names_both() -> None:
    lots = _lots(
        ("A", "101-111 N MAIN AVE"),
        ("B", "115-117 N MAIN AVE"),
        ("C", "112 N MAIN AVE"),
        ("D", "101 S MAIN AVE"),
        ("E", "103 WI/ N MAIN AVE"),
    )
    tlids, method, _ = hl.match_address("101-117 N Main Ave.", lots)
    assert tlids == ("A", "B") and method == "address-ambiguous"


def test_an_intersection_is_no_address() -> None:
    assert hl.parse_address("I-84 & NE 169th Ave.") is None
    assert hl.parse_address("Stark & Troutdale Rd.") is None
    assert hl.match_address("121ST AND KATHERINE ST", _lots(("A", "1 N MAIN AVE")))[1] == "none"


def test_a_second_address_in_brackets_is_tried() -> None:
    lots = _lots(("A", "15020 SW 100TH AVE"))
    assert hl.match_address("9890 SW PEPPERTREE LN (15020 SW 100TH AVE)", lots)[:2] == (("A",), "address-exact")


def test_a_taxlot_the_source_names_is_not_overruled_by_an_address() -> None:
    row = {
        "tlid": WASHCO_LOT,
        "address_listed": "410 N Main Ave.",
        "name": "",
        "listing_id_or_row": "L1",
        "source": "x",
        "match_method": "taxlot",
        "match_note": "named",
    }
    (got,) = hl.match_rows([row], _lots(("A", "410 N MAIN AVE")))
    assert got["tlid"] == WASHCO_LOT and got["match_method"] == "taxlot"


def test_a_taxlot_with_spaces_survives_the_cell() -> None:
    assert hl.split_tlids("1S3E10BC  -02300;1S3E10BC  -04700") == ("1S3E10BC  -02300", "1S3E10BC  -04700")


# --- the state's lists -------------------------------------------------------


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ({"nrStat": "Individually Listed", "elig": "eligible/significant", "origUse": "Single Dwelling"}, "nr-individual"),
        ({"nrStat": "Listed Individually & in Hist", "elig": "eligible/contributing", "origUse": "School"}, "nr-individual"),
        ({"nrStat": "Part of listing (Indiv Listed", "elig": "", "origUse": "Church"}, "nr-individual"),
        ({"nrStat": "Natl Hist Landmark", "elig": "", "origUse": "Library"}, "nr-individual"),
        ({"nrStat": "Individually Listed", "elig": "eligible/significant", "origUse": "Cemetery"}, "nr-object"),
        ({"nrStat": "Individually Listed", "elig": "eligible/significant", "origUse": ""}, "nr-object"),
        ({"nrStat": "Listed in Historic District", "elig": "eligible/contributing"}, "nr-district-contributing"),
        ({"nrStat": "Listed in Historic District", "elig": "not eligible/non-contributing"}, "nr-district-noncontributing"),
        ({"nrStat": "Listed in Historic District", "elig": "not eligible/out of period"}, "nr-district-noncontributing"),
        ({"nrStat": "Formally Determined Eligible", "elig": "eligible/significant"}, "determined-eligible"),
        ({"nrStat": "", "elig": "eligible/contributing"}, "surveyed-eligible"),
        ({"nrStat": None, "elig": "eligible/significant"}, "surveyed-eligible"),
        ({"nrStat": "", "elig": "undetermined"}, "surveyed-undetermined"),
        ({"nrStat": "", "elig": ""}, "surveyed-undetermined"),
        ({"nrStat": "", "elig": "not eligible/non-contributing"}, "surveyed-not-eligible"),
        ({"nrStat": "", "elig": "not eligible/out of period"}, "surveyed-not-eligible"),
        ({"nrStat": "Individually Listed", "elig": "demolished"}, "demolished"),
        ({"nrStat": "Delisted", "elig": "eligible/significant"}, "delisted"),
    ],
)
def test_the_layer_fields_tell_listed_from_surveyed(attrs, expected) -> None:
    assert hl.shpo_class(attrs) == expected


def test_only_a_national_register_building_reads_protected() -> None:
    classes = hl.load_state_policy()["classes"]
    assert {n for n, c in classes.items() if c["standing"] == hl.PROTECTED} == {
        "nr-individual",
        "nr-district-contributing",
    }
    assert not (set(classes) & hl.LEFT_OUT)


def test_a_national_register_district_point_marks_no_lot() -> None:
    assert hl.nps_class({"ResType": "district"}) is None
    assert hl.nps_class({"ResType": "building"}) == "nr-individual"
    assert hl.nps_class({"ResType": "object"}) == "nr-object"


def _state_row(kind: str, place: str, method: str = "address-exact", tlid: str = "1S1E01AA00100") -> dict[str, str]:
    return {
        "tlid": "" if method == "none" else tlid,
        "address_listed": "1 N Main St",
        "name": "x",
        "listing_id_or_row": "shpo-1",
        "source": "shpo",
        "match_method": method,
        "match_note": "",
        "place": place,
        "class": kind,
        "county": "Washington",
        "city": "x",
        "lon": "",
        "lat": "",
    }


def _read(row: dict[str, str], own: dict[str, set[str]] | None = None):
    return hl._state_listing("shpo-x", row, hl.load_state_policy(), own or {})


def test_a_surveyed_entry_is_yellow_and_never_red() -> None:
    for kind in ("surveyed-eligible", "surveyed-undetermined", "determined-eligible", "nr-object"):
        for method in ("address-exact", "point-in-lot", "address-fuzzy", "point-only"):
            assert _read(_state_row(kind, "sandy", method)).standing == hl.DOUBTFUL


def test_a_yellow_carries_what_the_local_code_says() -> None:
    assert "City Council" in _read(_state_row("surveyed-eligible", "sandy")).why
    assert "suspends" in _read(_state_row("surveyed-eligible", "milwaukie")).why


def test_a_national_register_building_is_red_on_a_sure_match_only() -> None:
    for method in ("address-exact", "address-range", "point-in-lot"):
        assert _read(_state_row("nr-individual", "milwaukie", method)).standing == hl.PROTECTED
        assert _read(_state_row("nr-district-contributing", "beaverton", method)).standing == hl.PROTECTED
    for method in ("address-fuzzy", "address-ambiguous", "point-only"):
        assert _read(_state_row("nr-individual", "milwaukie", method)).standing == hl.DOUBTFUL
    assert _read(_state_row("nr-district-noncontributing", "beaverton")).standing == hl.DOUBTFUL


def test_a_city_list_held_stays_the_authority() -> None:
    assert _read(_state_row("surveyed-eligible", "gresham")) is None
    assert _read(_state_row("nr-district-noncontributing", "west-linn")) is None
    # On the National Register, not on the city's list: yellow.
    assert _read(_state_row("nr-individual", "tigard")).standing == hl.DOUBTFUL
    assert "own list does not carry" in _read(_state_row("nr-individual", "tigard")).why
    # And on the city's list, red, the state rule answering for what the list leaves open.
    on_list = _read(_state_row("nr-individual", "tigard", tlid="1S1E01AA  -00100"), {"tigard": {"1S1E01AA00100"}})
    assert on_list.standing == hl.PROTECTED


def test_troutdales_own_code_reaches_the_national_register() -> None:
    assert _read(_state_row("nr-individual", "troutdale")).standing == hl.PROTECTED
    assert _read(_state_row("surveyed-eligible", "troutdale")) is None


def test_portlands_map_answers_there() -> None:
    assert _read(_state_row("nr-individual", "portland")) is None
    assert _read(_state_row("surveyed-eligible", "portland")) is None


def test_every_state_file_row_reads_and_nothing_but_a_national_register_building_is_red() -> None:
    assert hl.state_files()
    for path in hl.state_files():
        assert tuple(hl.read_rows(path)[0]) == hl.STATE_COLUMNS
        assert (path.parent / "SOURCE.json").is_file()
    for x in hl.load_lists():
        if x.listing_class and x.standing == hl.PROTECTED and x.tlids:
            assert x.listing_class in ("nr-individual", "nr-district-contributing"), x.said()
            assert x.method in hl.SURE_MATCH, x.said()


def test_the_state_rows_do_not_land_portlands_map() -> None:
    assert not [x for x in hl.load_lists() if x.place == "portland"]


def _streets(*rows: tuple[str, str]) -> dict:
    return _lots(*rows)


def test_a_point_and_an_address_are_checked_against_each_other() -> None:
    streets = _streets(("A", "410 N MAIN AVE"), ("B", "412 N MAIN AVE"))
    assert hl.place_state_row("410 N Main Ave", ["A"], streets)[:2] == (("A",), "point-in-lot")
    # The address fixes a lot and the point falls on the neighbour: the address stands.
    tlids, method, note = hl.place_state_row("410 N Main Ave", ["B"], streets)
    assert (tlids, method) == (("A",), "address-exact") and "B" in note
    # No address, a point: only ever yellow.
    assert hl.place_state_row("Near the old mill", ["B"], streets)[:2] == (("B",), "point-only")
    assert "point-only" in hl.UNSURE_MATCH
    assert hl.place_state_row("Near the old mill", [], streets)[:2] == ((), "none")


def test_a_place_is_spelled_as_protection_yaml_spells_it() -> None:
    assert hl.place_of("WEST LINN", "clackamas") == "west-linn"
    assert hl.place_of("UNINCORPORATED", "clackamas") == "clackamas-unincorporated"
    assert hl.place_of(None, "washington") == "washington-unincorporated"
    assert hl.place_of("", "multnomah") == "multnomah-unincorporated"


def _local_lot_table():
    for path in (
        ROOT / "data" / "quadfit" / "s1_lots.parquet",
        ROOT.parent.parent / "vicinitideals" / "data" / "quadfit" / "s1_lots.parquet",
    ):
        if path.is_file():
            return path
    pytest.skip("local s1_lots.parquet data is not present in CI")


def test_a_state_point_lands_on_the_right_lot() -> None:
    """Harlow House, in the state's own degrees: holds the lot table's coordinates."""
    columns = ["TLID", "SITEADDR", "SITECITY", "JURIS_CITY", "COUNTY", "wkb"]
    frame = pd.read_parquet(_local_lot_table(), columns=columns)
    frame = frame[frame["JURIS_CITY"] == "TROUTDALE"]
    table = hl.LotTable(frame, [("M", "TROUTDALE")])
    row = next(
        r
        for path in hl.state_files()
        for r in hl.read_rows(path)
        if r["address_listed"].upper().startswith("726 E") and r["city"].upper() == "TROUTDALE"
    )
    (under,) = table.under_points([float(row["lon"])], [float(row["lat"])])
    assert [hl.compact(table.tlids[i]) for i in under] == [hl.compact(TROUTDALE_LOT)]
    (got,) = hl.match_state_rows([row], table)
    # The state prints 726 E Columbia St, the road's old name: the point alone.
    assert got["match_method"] == "point-only" and hl.compact(got["tlid"]) == hl.compact(TROUTDALE_LOT)
    assert got["place"] == "troutdale"


def test_a_row_of_a_county_the_table_does_not_hold_is_left_as_it_is() -> None:
    frame = pd.DataFrame(
        {
            "TLID": ["A"],
            "SITEADDR": ["1 N MAIN ST"],
            "SITECITY": ["GRESHAM"],
            "JURIS_CITY": ["GRESHAM"],
            "COUNTY": ["M"],
            "wkb": [shapely.to_wkb(shapely.box(0, 0, 1, 1))],
        }
    )
    row = _state_row("nr-individual", "tigard", "none")
    row.update(lon="-122.7", lat="45.4")
    table = hl.LotTable(frame, [("W", "X")])
    assert hl.match_state_rows([row], table) == [row]


def test_a_landmark_the_address_cannot_fix_borrows_the_states_record_and_stays_yellow() -> None:
    rows = {x.listing_id: x for x in hl.load_lists() if x.list_name == "gresham"}
    giese = rows["class1-22"]
    assert giese.tlids and giese.method == "point-only"
    assert giese.standing == hl.DOUBTFUL and "shpo-52816" in giese.note
    state = {r["listing_id_or_row"] for path in hl.state_files() for r in hl.read_rows(path)}
    for policy in hl.load_policy().values():
        assert set((policy.get("state_points") or {}).values()) <= state


def test_the_known_washington_county_lot_is_never_red_on_a_surveyed_entry() -> None:
    listings = hl.listings_on(WASHCO_LOT)
    assert listings and all(x.standing == hl.DOUBTFUL for x in listings)
