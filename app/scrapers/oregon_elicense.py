"""Scraper for the Oregon Real Estate Agency public license lookup.

Source: https://orea.elicense.micropact.com/Lookup/LicenseLookup.aspx

The site is ASP.NET WebForms wrapped in Cavu's ``CurrentFilter`` /
``LicenseLookup`` JavaScript layer. Submitting the form fires a
``ClickSearchLicenses(0)`` JS function that builds an EVENTARGUMENT filter
description and triggers an UpdatePanel postback — none of which runs from a
plain httpx POST (we tried; the panel comes back empty). So we drive a real
headless Chromium via Playwright:

  1. ``goto`` the lookup form
  2. Fill the License Number field, click Submit, wait for the results panel
     to populate (or stay empty if not found)
  3. Scrape the rendered HTML and extract the credential ID from the Detail
     link's ``DisplayLicenceDetail('…')`` call
  4. ``goto`` ``/Lookup/licensedetail.aspx?id={cred_id}`` directly — this is
     a plain page render, no JS dance — and parse the four fixed-id tables:
     ``Grid0`` (name+address), ``Grid1`` (license info), ``Grid2``
     (affiliated firm), ``Grid3`` (disciplinary actions).

We use Playwright (in worker extras) for the form submit and stdlib regex /
``html.unescape`` for parsing the resulting markup — page structure is rigid
(fixed IDs, fixed column order) so the parser stays small.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

LOOKUP_URL = "https://orea.elicense.micropact.com/Lookup/LicenseLookup.aspx"
DETAIL_URL = "https://orea.elicense.micropact.com/Lookup/licensedetail.aspx"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class OregonAddress:
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


@dataclass
class OregonDisciplinaryAction:
    case_number: str | None
    order_signed_date: str | None
    resolution: str | None
    found_issues: str | None


@dataclass
class OregonBrokerRecord:
    license_number: str
    name: str | None
    license_type: str | None
    status: str | None  # e.g. 'ACTIVE', 'INACTIVE', 'EXPIRED'
    expiration_date: str | None  # MM/DD/YYYY as displayed by the site
    personal_address: OregonAddress | None
    affiliated_firm_name: str | None
    affiliated_firm_address: OregonAddress | None
    disciplinary_actions: list[OregonDisciplinaryAction] = field(default_factory=list)
    detail_url: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_proxy_url() -> str | None:
    """Return a ProxyOn residential proxy URL if configured, else None."""
    try:
        from app.config import settings  # local import keeps tests light
        user = settings.proxyon_residential_username
        pw = settings.proxyon_residential_password
        host = settings.proxyon_residential_host
        port = settings.proxyon_residential_port
    except Exception:
        return None
    if not user or not pw:
        return None
    return f"http://{user}:{pw}@{host}:{port}"


def _extract_hidden(html: str, name: str) -> str:
    """Return the value of a hidden ASP.NET form field, or empty string."""
    pat_a = rf'<input[^>]*\bname="{re.escape(name)}"[^>]*\bvalue="([^"]*)"'
    m = re.search(pat_a, html)
    if m:
        return html_lib.unescape(m.group(1))
    pat_b = rf'<input[^>]*\bvalue="([^"]*)"[^>]*\bname="{re.escape(name)}"'
    m = re.search(pat_b, html)
    if m:
        return html_lib.unescape(m.group(1))
    return ""


_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")
_DETAIL_HREF_RE = re.compile(r"DisplayLicenceDetail\(\s*'([^']+)'\s*\)", re.IGNORECASE)
_ADDR_LINE2_RE = re.compile(r"^(.*?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$")


def _parse_grid(html: str, table_id: str) -> list[list[str]]:
    """Extract ``<tbody>`` rows from a table by ID. <br> → newline; tags stripped."""
    body_pat = re.compile(
        rf'<table[^>]*\bid="{re.escape(table_id)}"[^>]*>.*?<tbody[^>]*>(.*?)</tbody>',
        re.IGNORECASE | re.DOTALL,
    )
    body_m = body_pat.search(html)
    if not body_m:
        return []
    tbody = body_m.group(1)
    rows: list[list[str]] = []
    for row_m in _ROW_RE.finditer(tbody):
        cells: list[str] = []
        for cell_m in _CELL_RE.finditer(row_m.group(1)):
            content = cell_m.group(1)
            content = _BR_RE.sub("\n", content)
            content = _TAG_RE.sub("", content)
            content = html_lib.unescape(content)
            # Collapse runs of spaces/tabs but preserve newlines
            content = "\n".join(_WS_RE.sub(" ", line).strip() for line in content.split("\n"))
            content = content.strip()
            cells.append(content)
        if cells:
            rows.append(cells)
    return rows


def _parse_address(raw: str | None) -> OregonAddress | None:
    """Parse a two-line ``street\\nCity, ST  Zip`` block."""
    if not raw:
        return None
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    if not lines:
        return None
    street = lines[0]
    city_state_zip = lines[1] if len(lines) > 1 else ""
    m = _ADDR_LINE2_RE.match(city_state_zip)
    if m:
        return OregonAddress(
            street=street,
            city=m.group(1).strip(),
            state=m.group(2),
            zip=m.group(3),
        )
    return OregonAddress(street=street, city=city_state_zip or None)


def _extract_detail_id(result_html: str) -> str | None:
    """Extract the credential ID from the first ``DisplayLicenceDetail('…')`` call."""
    table_m = re.search(
        r'<table[^>]*\bid="ctl00_MainContentPlaceHolder_ucLicenseLookup_gvSearchResults"[^>]*>'
        r"(.*?)</table>",
        result_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not table_m:
        return None
    m = _DETAIL_HREF_RE.search(table_m.group(1))
    if not m:
        return None
    return html_lib.unescape(m.group(1))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_LICENSE_INPUT_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_ctl03_tbCredentialNumber_Credential"
_FIRST_NAME_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_ctl03_tbFirstName_Contact"
_LAST_NAME_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_ctl03_tbLastName_Contact"
_SUBMIT_BUTTON_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_btnLookup"
_RESULTS_PANEL_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_UpdtPanelGridLookup"
_RESULTS_TABLE_SELECTOR = "#ctl00_MainContentPlaceHolder_ucLicenseLookup_gvSearchResults"


def _count_result_rows(html: str) -> int:
    """Count ``CavuGridRow`` rows inside the lookup results table."""
    table_m = re.search(
        r'<table[^>]*\bid="ctl00_MainContentPlaceHolder_ucLicenseLookup_gvSearchResults"[^>]*>'
        r"(.*?)</table>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not table_m:
        return 0
    return len(re.findall(r'<tr[^>]*\bclass="[^"]*\bCavuGridRow\b', table_m.group(1)))


async def _record_from_detail_html(detail_html: str, detail_url: str) -> "OregonBrokerRecord":
    """Parse the four detail-page grids into an OregonBrokerRecord."""
    grid0 = _parse_grid(detail_html, "Grid0")
    grid1 = _parse_grid(detail_html, "Grid1")
    grid2 = _parse_grid(detail_html, "Grid2")
    grid3 = _parse_grid(detail_html, "Grid3")

    license_number = grid1[0][0] if grid1 and len(grid1[0]) > 0 else ""
    name = grid0[0][0] if grid0 and len(grid0[0]) > 0 else None
    personal_address = _parse_address(
        grid0[0][2] if grid0 and len(grid0[0]) > 2 else None
    )
    license_type = grid1[0][1] if grid1 and len(grid1[0]) > 1 else None
    expiration = grid1[0][2] if grid1 and len(grid1[0]) > 2 else None
    status = grid1[0][3] if grid1 and len(grid1[0]) > 3 else None
    firm_name = grid2[0][0] if grid2 and len(grid2[0]) > 0 else None
    firm_address = _parse_address(
        grid2[0][1] if grid2 and len(grid2[0]) > 1 else None
    )
    actions: list[OregonDisciplinaryAction] = []
    for row in grid3:
        actions.append(
            OregonDisciplinaryAction(
                case_number=row[0] if len(row) > 0 else None,
                order_signed_date=row[1] if len(row) > 1 else None,
                resolution=row[2] if len(row) > 2 else None,
                found_issues=row[3] if len(row) > 3 else None,
            )
        )

    return OregonBrokerRecord(
        license_number=license_number,
        name=name,
        license_type=license_type,
        status=status,
        expiration_date=expiration,
        personal_address=personal_address,
        affiliated_firm_name=firm_name,
        affiliated_firm_address=firm_address,
        disciplinary_actions=actions,
        detail_url=detail_url,
    )


async def _open_browser_and_search(
    fill_form: "Callable[[Page], Awaitable[None]]",
    *,
    proxy: str | None = "auto",
    timeout_ms: int = 30_000,
) -> tuple[str, "Browser"] | None:
    """Internal helper — opens a browser, runs the fill_form callback, clicks
    Submit, and returns (results_html, browser_handle). Caller is responsible
    for closing the browser via the handle once done with the detail page.

    Returns None if the page never rendered (transport failure).
    """
    from playwright.async_api import async_playwright  # noqa: PLC0415

    proxy_url = _build_proxy_url() if proxy == "auto" else proxy
    launch_kwargs: dict[str, Any] = {"headless": True}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context(user_agent=_USER_AGENT)
    page = await context.new_page()
    page.set_default_timeout(timeout_ms)
    try:
        await page.goto(LOOKUP_URL, wait_until="networkidle")
        await fill_form(page)
        await page.click(_SUBMIT_BUTTON_SELECTOR)
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        await page.wait_for_timeout(500)
        results_html = await page.content()
    except Exception:
        await browser.close()
        await pw.stop()
        raise

    return results_html, browser, page, pw  # type: ignore[return-value]


async def _fetch_detail(
    browser_state: tuple[str, Any, Any, Any],
    detail_id: str,
) -> str:
    """Navigate the existing browser to the detail page and return its HTML."""
    _, _browser, page, _pw = browser_state
    detail_url = f"{DETAIL_URL}?id={urllib.parse.quote(detail_id, safe='')}"
    await page.goto(detail_url, wait_until="domcontentloaded")
    return await page.content()


async def lookup_broker(
    license_number: str,
    *,
    proxy: str | None = "auto",
    timeout_ms: int = 30_000,
) -> OregonBrokerRecord | None:
    """Look up a single Oregon broker by license number via Playwright.

    Returns ``None`` when the license is not found in the Oregon database.
    Raises ``RuntimeError`` for transport / parse failures.
    """
    if not license_number or not license_number.strip():
        return None

    async def _fill(page: Any) -> None:
        await page.fill(_LICENSE_INPUT_SELECTOR, license_number.strip())

    state = await _open_browser_and_search(_fill, proxy=proxy, timeout_ms=timeout_ms)
    if state is None:
        return None
    results_html, browser, _page, pw = state
    try:
        detail_id = _extract_detail_id(results_html)
        if not detail_id:
            return None
        detail_html = await _fetch_detail(state, detail_id)
        detail_url = f"{DETAIL_URL}?id={urllib.parse.quote(detail_id, safe='')}"
        return await _record_from_detail_html(detail_html, detail_url)
    finally:
        await browser.close()
        await pw.stop()


async def lookup_broker_by_name(
    first_name: str,
    last_name: str,
    *,
    proxy: str | None = "auto",
    timeout_ms: int = 30_000,
) -> tuple[OregonBrokerRecord | None, str]:
    """Look up an Oregon broker by first + last name (fallback for brokers
    we have no license number for).

    Returns ``(record, status)`` where status is one of:

      - ``'found'`` — exactly one match in Oregon's DB; ``record`` is populated
      - ``'not_found'`` — no matches
      - ``'ambiguous'`` — two or more matches; we don't guess and leave the
        broker untouched

    Both names are required — single-name searches against Oregon's DB are
    too noisy to safely auto-pick a result.
    """
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first or not last:
        return None, "not_found"

    async def _fill(page: Any) -> None:
        await page.fill(_FIRST_NAME_SELECTOR, first)
        await page.fill(_LAST_NAME_SELECTOR, last)

    state = await _open_browser_and_search(_fill, proxy=proxy, timeout_ms=timeout_ms)
    if state is None:
        return None, "not_found"
    results_html, browser, _page, pw = state
    try:
        row_count = _count_result_rows(results_html)
        if row_count == 0:
            return None, "not_found"
        if row_count > 1:
            return None, "ambiguous"
        detail_id = _extract_detail_id(results_html)
        if not detail_id:
            return None, "not_found"
        detail_html = await _fetch_detail(state, detail_id)
        detail_url = f"{DETAIL_URL}?id={urllib.parse.quote(detail_id, safe='')}"
        record = await _record_from_detail_html(detail_html, detail_url)
        return record, "found"
    finally:
        await browser.close()
        await pw.stop()


__all__ = [
    "OregonAddress",
    "OregonBrokerRecord",
    "OregonDisciplinaryAction",
    "lookup_broker",
    "lookup_broker_by_name",
]
