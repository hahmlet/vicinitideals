"""An overlay that applies everywhere must be *fetched* everywhere.

`overlays.yaml` declares the FEMA floodway a carve and the SFHA fringe a flag
for `jurisdictions: all`. That declaration was true of the policy and false of
the data for as long as flood has been screened: `s0_acquire.py` pulled the
NFHL with `"DFIRM_ID" = '41051C'`, which is Multnomah County alone, so every
Clackamas lot was measured against a flood layer that stopped at the county
line and passed for want of it.

Nothing caught it because nothing could. A missing overlay does not raise --
it produces a lot with `ovl_fema_sfha = False`, which is the same value a lot
genuinely outside the floodplain gets, and s7 reads them identically. The only
visible symptom was in the aggregate: 70,196 Clackamas lots recorded ONE flood
touch between them, against 1,239 across 180,548 Multnomah lots. That is what
an absent layer looks like, and it looks exactly like good news.

The invariant these tests pin is the one that would have failed on the day:
**every county the screen keeps lots from must appear in the acquisition filter
of every overlay that claims to apply to all of them.** `KEEP_COUNTIES` in
`s0_acquire` is the single source of truth for which counties are screened, so
adding a third county to it fails these tests until its FEMA study ID is added
in the same breath -- which is the whole point, because the failure mode is
silent and the fix is one string.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.unit


#: A countywide FEMA study is the county FIPS code plus C, so the mapping from
#: an RLIS county code to a DFIRM prefix is stable and short. It is not the
#: whole story -- a city can be filed under its own ID (see FEMA_STUDIES below).
#: Washington is here unused -- it is the county a third jurisdiction would most
#: likely come from, and having it written down is what makes the test's failure
#: message actionable rather than a puzzle.
DFIRM_PREFIX = {
    "M": "41051",  # Multnomah
    "C": "41005",  # Clackamas
    "W": "41067",  # Washington
}


def _s0():
    """The quadfit conftest puts the tool directory on the path."""
    import s0_acquire

    return s0_acquire


def _flood_where() -> str:
    s0 = _s0()
    spec = s0.PHASE2_LAYERS["overlay_fema_flood"]
    return spec.get("where", "")


def test_the_flood_layer_is_fetched_for_every_county_the_screen_keeps() -> None:
    """The assertion that was false until 2026-09-01.

    If this fails after a county is added to `KEEP_COUNTIES`, the fix is to add
    that county's DFIRM prefix to the NFHL `where` clause -- not to relax the
    test. A flood layer that stops at a county line does not report an error, it
    reports dry land.
    """
    s0 = _s0()
    where = _flood_where()
    missing = []
    for code in sorted(s0.KEEP_COUNTIES):
        prefix = DFIRM_PREFIX.get(code)
        assert prefix, (
            f"county code {code!r} is screened but has no DFIRM prefix in this "
            f"test's map -- add it, then check the NFHL filter covers it"
        )
        if prefix not in where:
            missing.append((code, prefix))
    assert not missing, (
        f"screened counties absent from the NFHL filter: {missing}. "
        f"where={where!r}"
    )


#: Every jurisdiction in rules.yaml -> the FEMA studies its flood areas are
#: filed under. FEMA files a countywide study under the county FIPS plus C, but
#: a community mapped on its own under its NFIP community ID, and then the county
#: study holds only slivers of it. The City of Portland is one (410183), which
#: the county-prefix test above could not see: until 2026-11-18 every Portland
#: lot was measured against no FEMA data and 13 read GREEN in the 100-year zone.
#:
#: Source: NFHL layer 22 (Political Jurisdictions), queried 2026-11-18,
#: ``where "CO_FIPS" IN ('051', '005', '067') AND "ST_FIPS" = '41'``,
#: ``outFields DFIRM_ID, POL_NAME1, CO_FIPS, CID``: 559 rows, four studies
#: (41005C, 41051C, 41067C, 410183). A row is listed here where layer 22 names
#: the place inside that study; Portland is listed under its own study alone,
#: because the county studies name its boundary but hold almost none of its
#: flood areas (7 marked lots of 183,300).
FEMA_STUDIES = {
    "portland": ("410183",),
    "gresham": ("41051C",),
    "troutdale": ("41051C",),
    "fairview": ("41051C",),
    "wood_village": ("41051C",),
    "multnomah_unincorporated": ("41051C", "410183"),
    "lake_oswego": ("41005C", "41051C", "41067C"),
    "maywood_park": ("41051C", "410183"),
    "clackamas_unincorporated": ("41005C",),
    "happy_valley": ("41005C",),
    "milwaukie": ("41005C", "41051C"),
    "oregon_city": ("41005C",),
    "gladstone": ("41005C",),
    "west_linn": ("41005C",),
    "tualatin": ("41005C", "41067C"),
    "wilsonville": ("41005C", "41067C"),
    "rivergrove": ("41005C", "41067C"),
    "johnson_city": ("41005C",),
    "washington_unincorporated": ("41067C", "41005C", "410183"),
    "hillsboro": ("41067C",),
    "beaverton": ("41067C",),
    "sherwood": ("41067C",),
    "king_city": ("41067C",),
    "durham": ("41067C",),
    "canby": ("41005C",),
    "sandy": ("41005C",),
    "estacada": ("41005C",),
    "tigard": ("41067C",),
    "cornelius": ("41067C",),
}

#: The NFIP community IDs of the jurisdictions that FEMA maps on their own.
#: Layer 22 lists each place's community ID (CID); a CID that is itself a
#: study ID (all 28 Oregon studies, queried 2026-11-18 on layer 28 with
#: ``DFIRM_ID LIKE '41%'``: 27 county studies and 410183) means that place's
#: flood areas live in that study and nowhere else worth the name.
COMMUNITY_STUDIES = {"portland": "410183"}


def _filter_ids(where: str) -> set[str]:
    return set(re.findall(r"'(\d{5}[0-9A-Z])'", where))


def test_every_jurisdiction_is_inside_a_fetched_flood_study() -> None:
    """The invariant the county-prefix test missed: a city filed under its own ID.

    Every jurisdiction rules.yaml names (eligible or not -- switching one on must
    not be the day its flood layer is found missing) has to be in the map above,
    and every study it is filed under has to be in the NFHL filter. A new
    jurisdiction fails here until somebody looks its study up in layer 22.
    """
    from common import load_rules

    named = _filter_ids(_flood_where())
    missing = []
    for key in sorted(load_rules().jurisdictions):
        studies = FEMA_STUDIES.get(key)
        assert studies, (
            f"jurisdiction {key!r} has no FEMA study in FEMA_STUDIES -- look it up in NFHL "
            f"layer 22 (Political Jurisdictions) and add it, then check the NFHL filter"
        )
        missing += [(key, s) for s in studies if s not in named]
    assert not missing, f"jurisdictions whose flood study is not fetched: {missing}"


def test_a_community_mapped_on_its_own_is_fetched_under_its_own_id() -> None:
    """The exact shape of the 2026-11-18 failure, pinned by name."""
    named = _filter_ids(_flood_where())
    for key, study in COMMUNITY_STUDIES.items():
        assert FEMA_STUDIES[key] == (study,), key
        assert study in named, f"{key}'s own FEMA study {study} is not in the NFHL filter"


def test_the_flood_filter_names_no_study_the_screen_does_not_use() -> None:
    """The other direction, so the clause cannot quietly rot into a superset.

    Fetching a study we do not screen is not dangerous, only wasteful -- the
    NFHL download is the slowest acquisition in s0. This is the cheap guard that
    keeps the filter honest when a county or a city is REMOVED from the screen.
    """
    s0 = _s0()
    named = _filter_ids(_flood_where())
    assert named, f"no DFIRM id found in the NFHL filter: {_flood_where()!r}"
    used = {f"{DFIRM_PREFIX[c]}C" for c in s0.KEEP_COUNTIES if c in DFIRM_PREFIX}
    used |= {s for studies in FEMA_STUDIES.values() for s in studies}
    assert named <= used, f"NFHL fetches studies the screen does not use: {named - used}"


def test_an_overlay_declared_for_all_jurisdictions_says_so_explicitly() -> None:
    """Which overlays this invariant has to hold for.

    `jurisdictions: all` is the shape that makes a data gap invisible: a
    city-scoped overlay missing its layer is caught by the coverage grades in
    `overlays.yaml`, but an all-jurisdictions one silently grades every lot
    outside its data as clear. Today that is the two FEMA layers and the two
    state wetland maps (FOLLOWUPS 42(d)), whose fetch-coverage argument is
    :func:`test_the_state_wetland_maps_are_fetched_for_the_whole_run_area`. If
    another appears, it needs the same argument made about it, and this test is
    where somebody finds that out.
    """
    from common import load_overlays

    specs = load_overlays()
    everywhere = sorted(s.key for s in specs.overlays if s.applies_to("a_city_that_does_not_exist"))
    assert everywhere == [
        "dsl_lwi_wetlands", "dsl_nwi_wetlands", "fema_floodway", "fema_sfha",
    ], everywhere


#: Every screened lot's bounding box, measured on the 2026-10-01 run (lon
#: -123.00 to -122.37, lat 45.28 to 45.63), rounded outward.
SCREENED_EXTENT_4326 = (-123.05, 45.25, -122.30, 45.70)


@pytest.mark.parametrize("slug", ["overlay_dsl_lwi_wetlands", "overlay_dsl_nwi_wetlands"])
def test_the_state_wetland_maps_are_fetched_for_the_whole_run_area(slug) -> None:
    """DSL's layers are statewide, so they are asked for by box, not by county.

    A box that stopped short of a city would grade its lots dry the way the
    Multnomah-only NFHL filter did, so the box has to hold every screened lot,
    and the filter may name wetland types but never a place.
    """
    spec = _s0().PHASE2_LAYERS[slug]
    west, south, east, north = spec["bbox"]
    w, s, e, n = SCREENED_EXTENT_4326
    assert west <= w and south <= s and east >= e and north >= n, spec["bbox"]
    assert "COUNTY" not in spec.get("where", "1=1").upper()
