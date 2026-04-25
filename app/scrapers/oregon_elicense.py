"""Scraper for the Oregon Real Estate Agency public license lookup.

Source: https://orea.elicense.micropact.com/Lookup/LicenseLookup.aspx

The site is ASP.NET WebForms with __VIEWSTATE postback. Flow:

  1. ``GET`` the lookup form → extract ``__VIEWSTATE`` + ``__VIEWSTATEGENERATOR``
  2. ``POST`` the same URL with the license number, viewstate, and the submit
     button name → response page contains the ``gvSearchResults`` table with
     the matching license row (or no row if not found).
  3. The Detail link in that row carries a credential ID inside an inline
     ``DisplayLicenceDetail('80861;103024;0;Name;6679775;0')`` JS call;
     extract that string verbatim.
  4. ``GET /Lookup/licensedetail.aspx?id={cred_id}`` → detail page with four
     fixed-id tables: ``Grid0`` (name+address), ``Grid1`` (license info),
     ``Grid2`` (affiliated firm), ``Grid3`` (disciplinary actions).

We use httpx (already a dep) plus stdlib regex / ``html.unescape`` for
parsing — the page structure is rigid (fixed IDs, fixed column order) so the
parser stays small and we avoid pulling in BeautifulSoup/lxml.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

LOOKUP_URL = "https://orea.elicense.micropact.com/Lookup/LicenseLookup.aspx"
DETAIL_URL = "https://orea.elicense.micropact.com/Lookup/licensedetail.aspx"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


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


async def lookup_broker(
    license_number: str,
    *,
    proxy: str | None = "auto",
    timeout: httpx.Timeout | None = None,
) -> OregonBrokerRecord | None:
    """Look up a single Oregon broker by license number.

    Returns ``None`` when the license is not found in the Oregon database.
    Raises ``httpx.HTTPError`` / ``RuntimeError`` for transport, proxy, or
    parse failures.
    """
    if not license_number or not license_number.strip():
        return None

    proxy_url = _build_proxy_url() if proxy == "auto" else proxy
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(
        headers=headers,
        proxy=proxy_url,
        timeout=timeout or _DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        # 1. GET form to grab __VIEWSTATE + cookies
        r1 = await client.get(LOOKUP_URL)
        r1.raise_for_status()
        viewstate = _extract_hidden(r1.text, "__VIEWSTATE")
        viewstate_gen = _extract_hidden(r1.text, "__VIEWSTATEGENERATOR") or "44A23853"
        if not viewstate:
            raise RuntimeError("Oregon eLicense: __VIEWSTATE not found on form page")

        # 2. POST the form (full-page postback path; no async UpdatePanel)
        post_data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstate_gen,
            "__VIEWSTATEENCRYPTED": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbCredentialNumber_Credential": license_number.strip(),
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbDBA_Contact": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbFirstName_Contact": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbLastName_Contact": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbAddress2_ContactAddress": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbCity_ContactAddress": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$ddStates": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$tbZipCode_ContactAddress": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$ddCounty": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$ctl03$lbMultipleCredentialTypePrefix": "",
            "ctl00$MainContentPlaceHolder$ucLicenseLookup$btnLookup": "Submit",
        }
        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": LOOKUP_URL,
            "Origin": "https://orea.elicense.micropact.com",
        }
        r2 = await client.post(LOOKUP_URL, data=post_data, headers=post_headers)
        r2.raise_for_status()

        detail_id = _extract_detail_id(r2.text)
        if not detail_id:
            return None  # license not found

        # 3. GET detail page
        detail_url = f"{DETAIL_URL}?id={urllib.parse.quote(detail_id, safe='')}"
        r3 = await client.get(detail_url, headers={"Referer": LOOKUP_URL})
        r3.raise_for_status()
        detail_html = r3.text

        # 4. Parse 4 grids
        grid0 = _parse_grid(detail_html, "Grid0")  # Name | Alt Name | Address
        grid1 = _parse_grid(detail_html, "Grid1")  # License | Type | Expiration | Status | Docs
        grid2 = _parse_grid(detail_html, "Grid2")  # Firm Name | Firm Address | License | Type | Status | Affiliation Date
        grid3 = _parse_grid(detail_html, "Grid3")  # Case # | Order Signed | Resolution | Found Issues | Docs

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
            license_number=license_number.strip(),
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


__all__ = [
    "OregonAddress",
    "OregonBrokerRecord",
    "OregonDisciplinaryAction",
    "lookup_broker",
]
