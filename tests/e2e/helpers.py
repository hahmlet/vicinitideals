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
            "capital_balance": float, # Capital Balance column (running sum from total_sources)
        }

    Phase banner rows (single <td colspan=11>) are skipped automatically.
    Values are parsed through parse_currency so parenthetical negatives work.
    """
    rows_raw: list[dict] = page.evaluate("""() => {
        const rows = document.querySelectorAll('.line-table tbody tr');
        return Array.from(rows)
            .filter(r => r.querySelectorAll('td').length >= 11)
            .map(r => {
                const cells = r.querySelectorAll('td');
                return {
                    period:          cells[0].innerText.trim(),
                    phase:           cells[1].innerText.trim(),
                    net_cf:          cells[9].innerText.trim(),
                    capital_balance: cells[10].innerText.trim()
                };
            });
    }""")

    result = []
    for row in rows_raw:
        try:
            period = int(row["period"])
        except (ValueError, TypeError):
            period = -1
        # "Stabilized" → "stabilized", "Operation Lease Up" → "operation_lease_up"
        phase_raw = row["phase"].strip().lower().replace(" ", "_")
        result.append({
            "period":          period,
            "phase":           phase_raw,
            "net_cf":          parse_currency(row["net_cf"]),
            "capital_balance": parse_currency(row["capital_balance"]),
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
