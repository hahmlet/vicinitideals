"""Shared helpers for E2E tests — navigation, HTMX waits, auth, and math reading."""

from __future__ import annotations

import re

from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# HTMX / navigation
# ---------------------------------------------------------------------------

def wait_for_htmx(page: Page, timeout: int = 8000) -> None:
    """Wait for in-flight HTMX requests to settle using network idle.

    Falls back cleanly if no requests are in flight.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def navigate_to_deal(page: Page, base_url: str, deal_id: str) -> None:
    """Navigate to a deal's model builder page and wait for HTMX to settle."""
    page.goto(f"{base_url}/deals/{deal_id}")
    page.wait_for_load_state("domcontentloaded")
    wait_for_htmx(page)


def login(page: Page, base_url: str, email: str, password: str) -> None:
    """Log in via the login form.

    Waits for redirect to /deals after successful login.
    """
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("domcontentloaded")
    page.fill("[name=email]", email)
    page.fill("[name=password]", password)
    page.click("[type=submit]")
    page.wait_for_url(f"{base_url}/deals**", timeout=10_000)


# ---------------------------------------------------------------------------
# Currency / number parsing
# ---------------------------------------------------------------------------

def parse_currency(text: str) -> float:
    """Parse a UI currency string to a Python float.

    Handles:
      "$1,234,567"    →  1234567.0
      "($500,000)"    → -500000.0
      "($0)"          →  0.0
      "—"             →  0.0
      ""              →  0.0
    """
    text = text.strip()
    if not text or text == "—":
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return 0.0
    value = float(cleaned)
    return -value if negative else value


# ---------------------------------------------------------------------------
# Page value readers
# ---------------------------------------------------------------------------

def read_stat_raw(page: Page, label: str) -> str:
    """Return the raw inner text of a stat card's value by its label. Returns '' if missing."""
    loc = page.locator(f".stat-card:has(.stat-label:text('{label}')) .stat-value")
    if loc.count() == 0:
        return ""
    return loc.first.inner_text().strip()


def read_stat_currency(page: Page, label: str) -> float | None:
    """Read a stat card value as a currency float. Returns None if '—' or absent."""
    text = read_stat_raw(page, label)
    if not text or text == "—":
        return None
    return parse_currency(text)


def read_stat_pct(page: Page, label: str) -> float | None:
    """Read a stat card percentage (e.g. '8.5%') as a plain float (8.5). None if absent."""
    text = read_stat_raw(page, label)
    if not text or text == "—":
        return None
    cleaned = text.rstrip("%").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_stat_multiplier(page: Page, label: str) -> float | None:
    """Read a stat card multiplier (e.g. '1.25×') as a plain float. None if absent."""
    text = read_stat_raw(page, label)
    if not text or text == "—":
        return None
    cleaned = text.rstrip("×").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_cashflow_table(page: Page) -> list[dict]:
    """Read all data rows from the cashflow module table via one JS evaluation.

    Returns a list of dicts (one per data row, phase-banner rows excluded):
        {
            "period":          int,   # month number shown in "Mo." column
            "phase":           str,   # normalised phase name ("stabilized", "construction", …)
            "net_cf":          float, # Net CF column (positive = inflow)
            "capital_balance": float, # Capital Bal. (construction) or Cash Bal. (ops)
        }

    Columns are located **by header name**, not fixed index — the cashflow
    table has grown columns over time (e.g. the two DDF columns added Jun
    2026), and position-based reads silently picked up the wrong column. The
    cashflow table is identified as the ``.line-table`` whose header row
    contains a "Net CF" column. Phase-banner rows (single colspan <td>) are
    skipped automatically. Values are parsed through parse_currency so
    parenthetical negatives work.
    """
    table = page.evaluate("""() => {
        const norm = (s) => s.trim().toLowerCase().replace(/\\s+/g, ' ');
        // Pick the .line-table whose header row has a "Net CF" column.
        const tables = Array.from(document.querySelectorAll('table.line-table'));
        const cf = tables.find(t =>
            Array.from(t.querySelectorAll('thead th'))
                .some(th => norm(th.innerText) === 'net cf')
        );
        if (!cf) return { headers: [], rows: [] };
        const headers = Array.from(cf.querySelectorAll('thead th'))
            .map(th => norm(th.innerText));
        const rows = Array.from(cf.querySelectorAll('tbody tr'))
            // Data rows have one <td> per header; phase banners have a single
            // colspanned <td>.
            .filter(r => r.querySelectorAll('td').length >= headers.length)
            .map(r => Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim()));
        return { headers, rows };
    }""")

    headers: list[str] = table["headers"]
    rows: list[list[str]] = table["rows"]
    if not headers:
        return []

    def _idx(*names: str) -> int:
        for n in names:
            if n in headers:
                return headers.index(n)
        return -1

    # "Mo." renders as the period column; balances split across construction
    # ("capital bal.") and operations ("cash bal.").
    period_i = _idx("mo.", "month", "period")
    phase_i = _idx("phase")
    net_cf_i = _idx("net cf")
    cap_bal_i = _idx("capital bal.")
    cash_bal_i = _idx("cash bal.")

    def _cell(cells: list[str], i: int) -> str:
        return cells[i] if 0 <= i < len(cells) else ""

    result = []
    for cells in rows:
        try:
            period = int(_cell(cells, period_i))
        except (ValueError, TypeError):
            period = -1
        cap_bal = _cell(cells, cap_bal_i)
        cash_bal = _cell(cells, cash_bal_i)
        balance = cash_bal if cash_bal and cash_bal != "—" else cap_bal
        # "Stabilized" → "stabilized", "Operation Lease Up" → "operation_lease_up"
        phase_raw = _cell(cells, phase_i).strip().lower().replace(" ", "_")
        result.append({
            "period":          period,
            "phase":           phase_raw,
            "net_cf":          parse_currency(_cell(cells, net_cf_i)),
            "capital_balance": parse_currency(balance),
        })
    return result


def read_footer_total(page: Page) -> float | None:
    """Read the displayed total from the active module's line-table footer. None if absent."""
    loc = page.locator(".line-table-footer .line-total-amount")
    if loc.count() == 0:
        return None
    text = loc.first.inner_text().strip()
    if not text or text == "—":
        return None
    return parse_currency(text)


def read_table_col_amounts(
    page: Page,
    row_selector: str,
    col_selector: str = "td.col-right",
    col_index: int = 0,
) -> list[float]:
    """Read currency amounts from a specific column in a set of table rows.

    Args:
        row_selector: Playwright selector for the row elements (e.g. "#uses-tbody tr").
        col_selector:  Selector for cells within each row (default: "td.col-right").
        col_index:     Which matching cell to read per row (0 = first, -1 = last).

    Returns a list of parsed floats (0.0 for blank/dash cells).
    """
    rows = page.locator(row_selector).all()
    amounts: list[float] = []
    for row in rows:
        cells = row.locator(col_selector).all()
        if not cells:
            continue
        idx = col_index if col_index >= 0 else len(cells) + col_index
        if 0 <= idx < len(cells):
            text = cells[idx].inner_text().strip()
            amounts.append(parse_currency(text))
    return amounts


def read_sources_total(page: Page) -> float | None:
    """Read the capital total displayed in the Sources module header box. None if absent."""
    loc = page.locator(".sources-total-box strong")
    if loc.count() == 0:
        return None
    text = loc.first.inner_text().strip()
    if not text or text == "—":
        return None
    return parse_currency(text)
