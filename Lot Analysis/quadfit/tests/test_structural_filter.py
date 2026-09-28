"""s1's condominium verdict and s3's structural filter: condo records by the
roll's property code, and pockets measured under the layer whose zone they
carry.

FOLLOWUPS 1 (2026-09-28): s1's only condo test was the stack dedupe, so ~2,000
Multnomah unit records drawn as lots of their own (PROP_CODE 102/132/202/122,
1,000-2,000 sq ft) were measured every run and dropped again by FLATS's assign
stage. s1 now runs FLATS's own `check_condo` and s3 drops the `excluded` ones by
name, with the reason.

FOLLOWUPS 8(a): nine pocket lots in permitted zones (Clackamas R-MD, Multnomah
UPA R-10, Happy Valley VR57) stayed NOT_MEASURED because s3 dropped a code the
home jurisdiction's rules do not hold. s3 now reads FLATS's pocket rulings and
measures them under the other jurisdiction's rules.
"""

from __future__ import annotations

import pandas as pd
import pytest
import shapely

from common import load_rules
from s1_normalize import condo_columns
from s3_filter import pocket_rewrites, structural_filter
from s5o_overlays import overlay_reach


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def layers():
    from flats.rules.loader import load_rules as load_layers

    return load_layers()


# -- s1: the condominium verdict ---------------------------------------------


def test_a_multnomah_condominium_code_on_a_small_parcel_is_not_land() -> None:
    for code in ("102", "122", "132", "202", 102):
        got = condo_columns({"area_sqft": 1450.0, "BLDGSQFT": 1100, "PROP_CODE": code, "COUNTY": "M"})
        assert got == {"condo_verdict": "excluded", "condo_reason": "CONDO_AIR_PARCEL"}, code


def test_the_code_is_county_specific_and_the_common_land_is_kept() -> None:
    # Clackamas codes its roll differently: 102 there says nothing.
    assert condo_columns({"area_sqft": 1450.0, "PROP_CODE": "102", "COUNTY": "C"})["condo_verdict"] == "land"
    # The condominium's own ground -- big, condo-coded -- is real land, flagged.
    big = condo_columns({"area_sqft": 40_000.0, "PROP_CODE": "102", "COUNTY": "M"})
    assert big == {"condo_verdict": "suspect", "condo_reason": "SUSPECT_CONDO_COMMON_AREA"}
    # An ordinary house lot.
    assert condo_columns({"area_sqft": 5000.0, "BLDGSQFT": 1400, "PROP_CODE": "101", "COUNTY": "M"}) == {
        "condo_verdict": "land", "condo_reason": None,
    }


def test_s1_and_flats_normalize_read_one_implementation() -> None:
    """No mirror to drift: s1 calls the function the FLATS lot table calls."""
    import s1_normalize

    from flats.ingest import normalize
    from flats.normalize import condo

    assert s1_normalize.check_condo is condo.check_condo is normalize.check_condo


# -- s3: the structural filter ---------------------------------------------


def _lot(tlid: str, juris: str | None, zone_raw: str | None, *, side: float = 100.0, **over) -> dict:
    geom = shapely.box(7_650_000.0, 680_000.0, 7_650_000.0 + side, 680_000.0 + side)
    row = {
        "TLID": tlid, "jurisdiction": juris, "zone_raw": zone_raw, "geom": geom,
        "area_sqft": geom.area, "inside_ugb": True, "stacked": False, "stack_count": 1,
        "condo_verdict": "land", "condo_reason": None, "COUNTY": "M",
    }
    row.update(over)
    return row


def _run(rows: list[dict], rules, layers):
    kept, funnel, gone = structural_filter(pd.DataFrame(rows), rules, layers, say=lambda _m: None)
    return kept.set_index("TLID"), {r["step"]: r for r in funnel}, gone.set_index("TLID")


def test_a_condominium_record_is_dropped_by_name_with_its_reason(rules, layers) -> None:
    rows = [
        _lot("UNIT", "portland", "RM2", condo_verdict="excluded", condo_reason="CONDO_AIR_PARCEL"),
        _lot("COMMON", "portland", "R5", condo_verdict="suspect", condo_reason="SUSPECT_CONDO_COMMON_AREA"),
        _lot("STACK", "portland", "R5", stacked=True, stack_count=3),
        _lot("HOUSE", "portland", "R5"),
    ]
    kept, funnel, gone = _run(rows, rules, layers)
    assert set(kept.index) == {"COMMON", "HOUSE"}, "a suspect is kept for review, never dropped"
    assert gone.loc["UNIT", "step"] == "condo_excluded"
    assert gone.loc["UNIT", "reason"] == "CONDO_AIR_PARCEL"
    assert gone.loc["STACK", "step"] == "condo_stack" and gone.loc["STACK", "reason"] == ""
    assert funnel["condo_excluded"]["dropped"] == 1
    # The condo test runs before the stack test, as FLATS's normalize runs them.
    steps = [s for s in funnel if s != "all_taxlots"]
    assert steps.index("condo_excluded") < steps.index("condo_stack")


def test_a_stage_file_from_before_the_verdict_drops_no_condo_and_says_so(rules, layers) -> None:
    said: list[str] = []
    rows = [_lot("UNIT", "portland", "R5")]
    frame = pd.DataFrame(rows).drop(columns=["condo_verdict", "condo_reason"])
    kept, funnel, _gone = structural_filter(frame, rules, layers, say=said.append)
    assert list(kept["TLID"]) == ["UNIT"]
    assert "condo_excluded" not in {r["step"] for r in funnel}
    assert any("WARNING" in m and "condo_verdict" in m for m in said)


#: The three pockets FOLLOWUPS 8(a) named: a zone FLATS rules is another
#: layer's, that quadfit holds -- and permits the building in -- over there.
NAMED_POCKETS = {
    ("clackamas_unincorporated", "R-MD"): ("milwaukie", "R-MD", "or/clackamas/milwaukie"),
    ("happy_valley", "VR57"): ("clackamas_unincorporated", "VR57", "or/clackamas/_unincorporated"),
    ("multnomah_unincorporated", "UPAR-10"): ("troutdale", "LDR-1", "or/multnomah/troutdale"),
}


def test_the_named_pockets_are_measured_under_the_layer_whose_zone_they_carry(rules, layers) -> None:
    got = pocket_rewrites(list(NAMED_POCKETS), rules, layers)
    assert got == NAMED_POCKETS
    for (_home, _code), (slug, zone, _lid) in got.items():
        assert rules.jurisdictions[slug].rule_for(zone).quadplex_allowed


def test_every_pocket_ruling_is_followed_exactly_where_quadfit_can_measure_it(rules, layers) -> None:
    """The mechanism, over the whole corpus: a pocket ruling rewrites its code
    iff it names a block (not `zone: map`) and quadfit holds that block in
    the `of` jurisdiction; nothing that is not a pocket is ever rewritten."""
    from flats.encode.port_quadfit import layer_id_for

    slug_of = {}
    for slug in rules.jurisdictions:
        try:
            slug_of[layer_id_for(slug)] = slug
        except KeyError:
            pass
    pairs, expected = [], {}
    for lid, layer in layers.items():
        home = slug_of.get(lid)
        if home is None:
            continue
        for code, ruling in layer.zone_rulings.items():
            pairs.append((home, code))
            if ruling.outcome != "pocket" or ruling.pocket_code(code) is None:
                continue
            of = slug_of.get(ruling.of or "")
            held = layers[ruling.of].holds(ruling.pocket_code(code)) if ruling.of in layers else None
            if of and held and rules.jurisdictions[of].rule_for(held) is not None \
                    and rules.jurisdictions[home].rule_for(code) is None:
                expected[(home, code)] = (of, held, ruling.of)
    # And a zone every layer holds is left alone.
    pairs += [("portland", "R5"), ("milwaukie", "R-MD")]
    assert pocket_rewrites(pairs, rules, layers) == expected
    assert set(NAMED_POCKETS) <= set(expected)


def test_a_pocket_lot_survives_s3_under_the_other_jurisdiction_and_keeps_its_own(rules, layers) -> None:
    rows = [
        _lot("POCKET", "clackamas_unincorporated", "R-MD", COUNTY="C"),
        _lot("UPA", "multnomah_unincorporated", "UPAR-10"),
        _lot("NEVER", "portland", "NOT-A-ZONE"),
        _lot("HOUSE", "portland", "R5"),
    ]
    kept, _funnel, gone = _run(rows, rules, layers)
    assert set(kept.index) == {"POCKET", "UPA", "HOUSE"}
    assert gone.loc["NEVER", "step"] == "zone_not_in_rules"
    p = kept.loc["POCKET"]
    assert (p["jurisdiction"], p["zone_raw"], p["zone"]) == ("milwaukie", "R-MD", "R-MD")
    assert (p["home_jurisdiction"], p["home_zone_raw"], p["pocket_of"]) == (
        "clackamas_unincorporated", "R-MD", "or/clackamas/milwaukie",
    )
    u = kept.loc["UPA"]
    assert (u["jurisdiction"], u["zone_raw"], u["home_zone_raw"]) == ("troutdale", "LDR-1", "UPAR-10")
    h = kept.loc["HOUSE"]
    assert (h["jurisdiction"], h["home_jurisdiction"], h["pocket_of"]) == ("portland", "portland", None)


def test_a_pocket_is_gated_by_the_other_jurisdictions_growth_boundary(rules, layers) -> None:
    """The gates after the rewrite are the rules layer's: FLATS gates a pocket
    lot under the other layer the same way."""
    # Happy Valley asks no boundary test of its own lots; the county does.
    assert not rules.jurisdictions["happy_valley"].require_inside_ugb
    assert rules.jurisdictions["clackamas_unincorporated"].require_inside_ugb
    rows = [
        _lot("OUTSIDE", "happy_valley", "VR57", inside_ugb=False, COUNTY="C"),
        _lot("INSIDE", "happy_valley", "VR57", COUNTY="C"),
    ]
    kept, _funnel, gone = _run(rows, rules, layers)
    assert list(kept.index) == ["INSIDE"]
    assert gone.loc["OUTSIDE", "step"] == "outside_ugb"


def test_a_pocket_lot_is_carved_by_both_jurisdictions_overlays() -> None:
    lots = pd.DataFrame({
        "jurisdiction": ["milwaukie", "portland"],
        "home_jurisdiction": ["clackamas_unincorporated", "portland"],
    })
    assert overlay_reach(lots) == [("milwaukie", "clackamas_unincorporated"), ("portland",)]
    # A stage file from before the column reads the lot's own only.
    assert overlay_reach(lots.drop(columns=["home_jurisdiction"])) == [("milwaukie",), ("portland",)]
