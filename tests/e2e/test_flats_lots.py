"""The lot pages in a browser — the county run, lot by lot.

The run is loaded into the live database and these pages are the first thing
that reads it, so what is driven here is the two rules the pages exist to
keep: the verdict the screen can stand behind is printed first and the colour
it would take once the rules are signed beside it, never in its place; and a
lot on the list opens to its own page without losing the run it came from.

Nothing is recorded — the pages are read-only. Where no run has been loaded
the tests skip rather than invent one.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_lots.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_the_list_counts_the_run_by_verdict_then_by_colour(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    counts = page.locator("#lot-counts")
    expect(counts).to_be_visible()
    expect(counts.get_by_text("Verdict today")).to_be_visible()
    expect(counts.get_by_text("If signed as read")).to_be_visible()
    text = counts.inner_text()
    assert text.index("Verdict today") < text.index("If signed as read")
    # Four colour buttons, each carrying its count.
    for colour in ("green", "yellow", "unknown", "red"):
        expect(counts.get_by_role("link", name=colour, exact=False)).to_be_visible()


def test_a_green_lot_opens_to_its_page_with_the_verdict_first(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    rows = page.locator("#lot-table tbody tr")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no green lot on this instance")

    first = rows.first.locator("td a").first
    where = first.inner_text()
    first.click()

    expect(page.locator("#lot-verdict")).to_be_visible()
    expect(page.locator("h2")).to_contain_text(where)
    head = page.locator("#lot-verdict").inner_text()
    assert head.index("Verdict today") < head.index("If signed as read")
    # The verdict is the screen's honest word; the colour that got the lot
    # onto the green list is beside it.
    assert "green" in head.split("If signed as read", 1)[1]
    expect(page.locator("#lot-facts")).to_be_visible()
    expect(page.locator("svg polygon").first).to_be_visible()


def test_the_city_filter_narrows_and_offers_that_city_s_zones(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    page.select_option("select[name=jurisdiction]", "or/multnomah/portland")
    page.get_by_role("button", name="Show").click()

    expect(page.locator("select[name=zone]")).to_be_visible()
    expect(page.locator("select[name=zone] option[value='R5']")).to_have_count(1)
    cities = page.locator("#lot-table tbody tr td:nth-child(3)").all_inner_texts()
    assert cities and set(cities) == {"Portland"}


def test_the_county_copy_is_named_on_both_pages_and_a_warning_is_a_bar(
    logged_in_page: Page, base_url: str
) -> None:
    """The footer is always there, so 'no warning' is a statement; a red or
    amber bar, when shown, sits above the page's own heading."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    footer = page.locator("#county-copy")
    expect(footer).to_be_visible()
    expect(footer).to_contain_text("County map copy:")
    for bar in ("#county-copy-red", "#county-copy-amber"):
        if page.locator(bar).count():
            expect(page.locator(bar)).to_be_visible()
            assert page.locator(bar).bounding_box()["y"] < page.locator("h2").first.bounding_box()["y"]

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    page.locator("#lot-table tbody tr td a").first.click()
    expect(page.locator("#lot-verdict")).to_be_visible()
    expect(page.locator("#county-copy")).to_contain_text("County map copy:")


def test_a_tight_fit_is_a_filter_on_the_list_and_a_row_on_the_lot_page(
    logged_in_page: Page, base_url: str
) -> None:
    """Steph 2026-09-25: a fit within 6 inches either way is green with a
    flag the acquisition review sees -- a box on the list that shows only
    those lots, and a line on the lot page that says the survey decides."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    page.get_by_label("Only tight fits").check()
    page.get_by_role("button", name="Show").click()
    expect(page.get_by_label("Only tight fits")).to_be_checked()
    if page.get_by_text("No lots match.").count():
        pytest.skip("no tight fit in this run")

    row = page.locator("#lot-table tbody tr").first
    expect(row.get_by_text("tight fit").first).to_be_visible()
    row.locator("td a").first.click()
    expect(page.locator("#lot-verdict")).to_be_visible()
    flagged = page.locator("tr[id^='tight-']").first
    expect(flagged).to_be_visible()
    expect(flagged).to_contain_text("survey")


#: A Portland R5 corner lot the corner-front re-screen (FOLLOWUPS 4(e))
#: turned green: fronted on its shorter street, parked off the other.
CORNER_LOT = "/flats/lots/multnomah/1S2E20BA%20%20-15600"


def test_a_corner_lot_page_names_its_front_street_and_the_side_street_driveway(
    logged_in_page: Page, base_url: str
) -> None:
    """Steph 2026-09-26: "we need to abide if Portland has guidance on which
    is front and which is side." The lot page says which street the screen
    took as the front and that the driveway comes in off the other."""
    page = logged_in_page
    page.goto(f"{base_url}{CORNER_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the corner lot is not in this run")
    expect(page.locator(".corner-front").first).to_contain_text("corner lot: laid out fronting the street at")
    expect(page.locator(".side-street").first).to_contain_text("the driveway comes in from the side street")


def test_a_lot_page_draws_where_the_building_and_parking_stand(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 5: each design card draws the fit on the lot -- the
    building, its driveway and its parking court over the ground the rules
    leave -- and says in words what the dashed box means."""
    page = logged_in_page
    page.goto(f"{base_url}{CORNER_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the corner lot is not in this run")
    plan = page.locator(".fit-plan").first
    expect(plan).to_be_visible()
    for layer in ("plan-lot", "plan-envelope", "plan-room", "plan-building", "plan-court"):
        expect(plan.locator(f"polygon.{layer}").first).to_be_attached()
    expect(plan).to_contain_text("One way it could stand, not a site plan.")



def test_a_lot_page_says_how_far_it_is_from_transit(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 17(b2), Steph 2026-09-30: "show it, don't screen it". The
    facts table says whether the state parking reform's transit reach covers
    the lot and how far the nearest station, frequent line and stop are
    (run 48: 7,117 / 2,095 / 886 ft for this lot)."""
    page = logged_in_page
    page.goto(f"{base_url}{CORNER_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the corner lot is not in this run")
    facts = page.locator("#lot-facts")
    expect(facts).to_contain_text("Near transit: no parking can be required")
    expect(facts).to_contain_text("yes -- within 3/4 mile of rail or 1/2 mile of a frequent line")
    for label in ("Nearest MAX / streetcar / WES station", "Nearest frequent bus or rail line", "Nearest transit stop"):
        row = facts.locator("tr", has_text=label)
        expect(row).to_contain_text(" ft")

#: a county-zoned island inside Happy Valley's line (FOLLOWUPS 8, run 33):
#: RRFF5 is Clackamas County's code, so it is screened under the county's rules.
POCKET_LOT = "/flats/lots/clackamas/12E35D%2000900"


def test_a_pocket_lot_page_says_whose_zoning_it_was_screened_under(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 8: a lot whose zone code belongs to a neighbouring map is
    screened under that map's rules, and the page says so beside the zone."""
    page = logged_in_page
    page.goto(f"{base_url}{POCKET_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the pocket lot is not in this run")
    expect(page.locator("#lot-zoned-by")).to_contain_text("under ")
    expect(page.locator("#lot-zoned-by")).to_contain_text(" zoning")

#: fits with room to spare, but the far wall is 176 ft of hose from the street
#: (FOLLOWUPS 28, run 55): RED on the fire code alone.
FIRE_LOT = "/flats/lots/multnomah/1N1E06DB%20%20-00800"


def test_a_lot_page_says_how_far_a_fire_hose_walks_and_when_that_is_too_far(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 28, Steph 2026-10-01: "RED stands". The design row says how
    far the hose walks from the truck's street to the farthest wall, and past
    the fire code's 150 ft it says that is what turns the lot red."""
    page = logged_in_page
    page.goto(f"{base_url}{FIRE_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the fire lot is not in this run")
    row = page.locator("tr#fire-pod80x25-2")
    expect(row).to_contain_text("Fire truck reach")
    expect(row).to_contain_text("ft from the street to the farthest wall, walked around the building")
    expect(row.locator(".badge-red")).to_have_text("farther than the fire code allows (150 ft)")


#: King City Kingston Terrace, Town Center: a minimum density per net acre
#: (KCMC 16.114.050 B), so the lot card names its net-land list.
NET_LAND_LOT = "/flats/lots/washington/2S1170000400"


def test_a_lot_page_names_what_net_land_takes_off_and_what_was_assumed_absent(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 30, Steph's option A: what the code subtracts and nothing
    maps is assumed absent -- and the page says so, by name, so a site visit
    knows what to look for."""
    page = logged_in_page
    page.goto(f"{base_url}{NET_LAND_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the net-land lot is not in this run")
    net = page.locator("#net-land-1")
    expect(net).to_contain_text("Net land")
    expect(net).to_contain_text("May come off (not certain)")
    expect(net.locator("tr.net-assumed")).to_contain_text("storm facilities")


#: SW Portland's West Hills: a lot that ran GREEN before the slope was read,
#: its whole area steeper than 15% on the 1 m lidar (FOLLOWUPS 38).
STEEP_LOT = "/flats/lots/multnomah/1S1E09CB%20%20-00600"


def test_a_lot_page_says_how_steep_the_ground_is(logged_in_page: Page, base_url: str) -> None:
    """Steph 2026-10-04: ground over 15% is kept out of where the building
    and its parking can go, and the page says how much of the lot that is
    and which elevation map read it. A run screened before the slope was
    read carries no row (FOLLOWUPS 38: green from the first run after it)."""
    page = logged_in_page
    page.goto(f"{base_url}{STEEP_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the steep lot is not in this run")
    rows = page.locator("tr.plan-slope")
    if rows.count() == 0:
        pytest.skip("this run was screened before the slope was read")
    first = rows.first
    expect(first).to_contain_text("Slope")
    expect(first.locator(".slope-steep")).to_contain_text("steeper than 15%")
    expect(first.locator(".slope-steep")).to_contain_text("1 m lidar map")


#: A Gresham corner lot: its street setbacks are measured from a sidewalk
#: easement nothing maps (Table 4.0131 note 1), taken at its worst.
SIDEWALK_LOT = "/flats/lots/multnomah/1N3E33CC%20%20-00400"


def test_a_gresham_lot_page_says_how_deep_a_sidewalk_easement_was_assumed(
    logged_in_page: Page, base_url: str
) -> None:
    """FOLLOWUPS 41(iii), Steph 2026-10-05: "measure exact, fallback to
    pessimistic". The facts table says how far in the street setbacks were
    taken to start -- 7 ft on a local street, 20 ft on any other. A run
    screened before the depth was carried has no row."""
    page = logged_in_page
    page.goto(f"{base_url}{SIDEWALK_LOT}")
    if page.locator("#lot-verdict").count() == 0:
        pytest.skip("the Gresham lot is not in this run")
    row = page.locator("#lot-facts tr", has_text="Sidewalk easement assumed")
    if row.count() == 0:
        pytest.skip("this run was screened before the sidewalk depth was carried")
    expect(row).to_contain_text(" ft")
