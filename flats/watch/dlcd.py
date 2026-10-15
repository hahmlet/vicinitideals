"""Fetch, parse, and list DLCD plan-amendment notices for FLATS jurisdictions."""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml

Kind = Literal["adopted", "proposed"]
Verdict = Literal["no_effect", "encode", "watch"]

ROOT = Path(__file__).resolve().parents[2]
JURISDICTIONS_PATH = ROOT / "flats" / "config" / "dlcd_jurisdictions.yaml"
LEDGER_PATH = ROOT / "flats" / "config" / "dlcd_read.yaml"
REPORT_URLS: dict[Kind, str] = {
    "adopted": (
        "https://db.lcd.state.or.us/papa_website_reports/"
        "PublicNoticeAdoptedAmendments.aspx"
    ),
    "proposed": (
        "https://db.lcd.state.or.us/papa_website_reports/"
        "PublicNoticeProposedAmendments.aspx"
    ),
}
LEDGER_KEYS = {
    "id", "kind", "jurisdiction", "received", "read_on", "read_by", "verdict",
    "note", "followup",
}
VERDICTS = {"no_effect", "encode", "watch"}
CSV_FIELDS = {
    "JurisdictionName",
    "ReceivedDate",
    "LocalContact",
    "LocalFileNumber",
    "Textbox5",
    "DLCDFileNumber",
    "LocalContact2",
    "Summary",
    "Summary2",
}


@dataclass(frozen=True)
class Notice:
    """One DLCD export row, retaining the CSV fields and its report kind."""

    jurisdiction: str
    received: str | None
    local_contact: str | None
    local_file_number: str | None
    local_phone: str | None
    dlcd_file_number: str | None
    local_email: str | None
    adopted_date: str | None
    first_hearing_date: str | None
    final_hearing_date: str | None
    summary: str | None
    summary2: str | None
    kind: Kind
    other_fields: tuple[tuple[str, str], ...] = ()

    @property
    def id(self) -> str:
        """Return a kind-scoped stable ID, with a content hash as last resort."""
        reference = self.dlcd_file_number or self.local_file_number
        if not reference:
            values = (self.received, self.summary, self.summary2)
            content = "\0".join(value or "" for value in values)
            reference = hashlib.sha256(content.encode()).hexdigest()[:16]
        jurisdiction = self.jurisdiction.removeprefix("City of ")
        return f"{self.kind}:{jurisdiction}:{reference}"

    @property
    def link(self) -> str:
        """Return the official report page; the CSV has no item-level links."""
        return REPORT_URLS[self.kind]


def fetch(kind: Kind, start: date, end: date, out: Path) -> Path:
    """Export one DLCD ReportViewer report to ``out`` using Playwright."""
    if kind not in REPORT_URLS:
        raise ValueError(f"Unsupported DLCD report kind: {kind}")
    if start > end:
        raise ValueError("start date must not be after end date")

    from playwright.sync_api import sync_playwright

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(REPORT_URLS[kind], wait_until="domcontentloaded", timeout=60_000)
            page.fill("#txtFromDate", f"{start.month}/{start.day}/{start.year}")
            page.fill("#txtToDate", f"{end.month}/{end.day}/{end.year}")
            page.click("#btnGo")
            page.wait_for_timeout(10_000)
            body = page.locator("body").inner_text()
            invalid_end = re.search(
                r"The last valid end date is (\d{1,2}/\d{1,2}/\d{4})", body
            )
            if invalid_end:
                valid_end = datetime.strptime(invalid_end.group(1), "%m/%d/%Y").date()
                if valid_end < start:
                    raise RuntimeError(
                        f"DLCD's latest available date {valid_end} is before {start}"
                    )
                page.fill(
                    "#txtToDate",
                    f"{valid_end.month}/{valid_end.day}/{valid_end.year}",
                )
                page.click("#btnGo")
                page.wait_for_timeout(10_000)
                if re.search(
                    r"The last valid end date is \d{1,2}/\d{1,2}/\d{4}",
                    page.locator("body").inner_text(),
                ):
                    raise RuntimeError("DLCD rejected the adjusted report end date")
            with page.expect_download(timeout=60_000) as download_info:
                page.evaluate("() => $find('rv').exportReport('CSV')")
            download_info.value.save_as(out)
        finally:
            browser.close()
    return out


def parse(csv_path: Path) -> list[Notice]:
    """Parse notice rows from a DLCD CSV export, skipping its report preamble."""
    csv_path = Path(csv_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))

    header_index = next(
        (
            index for index, row in enumerate(rows)
            if row and row[0].strip() == "JurisdictionName"
        ),
        None,
    )
    if header_index is None:
        raise ValueError(f"No DLCD notice header found in {csv_path}")

    kind = _report_kind(rows[:header_index], csv_path)
    headers = [value.strip() for value in rows[header_index]]
    missing = {"JurisdictionName", "Summary"} - set(headers)
    if missing:
        raise ValueError(f"Missing DLCD CSV columns: {', '.join(sorted(missing))}")

    notices: list[Notice] = []
    for row in rows[header_index + 1 :]:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != len(headers):
            continue
        values = dict(zip(headers, row, strict=True))
        jurisdiction = values.get("JurisdictionName", "").strip()
        if not jurisdiction:
            continue
        normalized = {key: _optional_text(value) for key, value in values.items()}
        notices.append(
            Notice(
                jurisdiction=jurisdiction,
                received=normalized.get("ReceivedDate"),
                local_contact=normalized.get("LocalContact"),
                local_file_number=normalized.get("LocalFileNumber"),
                local_phone=normalized.get("Textbox5"),
                dlcd_file_number=normalized.get("DLCDFileNumber"),
                local_email=normalized.get("LocalContact2"),
                adopted_date=_first_value(
                    normalized, "AdoptedDate", "AdoptionDate"
                ),
                first_hearing_date=_first_value(
                    normalized, "FirstHearingDate", "FirstHearingDate2"
                ),
                final_hearing_date=_first_value(
                    normalized, "FinalHearingDate", "FinalHearingDate2"
                ),
                summary=normalized.get("Summary"),
                summary2=normalized.get("Summary2"),
                kind=kind,
                other_fields=tuple(
                    (key, value or "")
                    for key, value in normalized.items()
                    if key not in CSV_FIELDS
                    and key not in {
                        "AdoptedDate",
                        "AdoptionDate",
                        "FirstHearingDate",
                        "FirstHearingDate2",
                        "FinalHearingDate",
                        "FinalHearingDate2",
                    }
                ),
            )
        )
    return notices


def load_jurisdictions(path: Path = JURISDICTIONS_PATH) -> dict[str, str]:
    """Load the exact DLCD export names and their FLATS jurisdiction slugs."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or any(
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(slug, str)
        or not slug.strip()
        for name, slug in raw.items()
    ):
        raise ValueError(f"Invalid DLCD jurisdiction mapping in {path}")
    return raw


def load_ledger(path: Path = LEDGER_PATH) -> list[dict[str, str | None]]:
    """Load and validate the notice-read ledger."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError(f"DLCD read ledger must be a list: {path}")
    for entry in raw:
        if isinstance(entry, dict):
            for key in ("received", "read_on"):
                if isinstance(entry.get(key), date):
                    entry[key] = entry[key].isoformat()
    _validate_ledger(raw)
    return raw


def new_notices(
    notices: list[Notice], ledger: list[dict[str, str | None]]
) -> list[Notice]:
    """Keep only notices for held jurisdictions not already present in ledger."""
    _validate_ledger(ledger)
    jurisdiction_map = load_jurisdictions()
    seen = {entry["id"] for entry in ledger}
    matched = (
        notice for notice in notices
        if notice.jurisdiction in jurisdiction_map and notice.id not in seen
    )
    return sorted(matched, key=_notice_sort_key)


def render_markdown(
    notices: list[Notice], jurisdictions: dict[str, str] | None = None
) -> str:
    """Render a complete agent reading list without judging its notices."""
    jurisdiction_map = jurisdictions or load_jurisdictions()
    lines = [
        "# New DLCD plan-amendment notices",
        "",
        f"{len(notices)} new notice(s). Read each summary and determine whether it "
        "changes a FLATS screen.",
        "",
    ]
    for notice in notices:
        slug = jurisdiction_map.get(notice.jurisdiction, "unmapped")
        lines.extend(
            [
                f"## {notice.jurisdiction} -> `{slug}`",
                "",
                f"- **Kind:** {notice.kind}",
                f"- **ID:** `{notice.id}`",
                f"- **DLCD file:** {notice.dlcd_file_number or 'not supplied'}",
                f"- **Local file:** {notice.local_file_number or 'not supplied'}",
                f"- **Received:** {notice.received or 'not supplied'}",
                f"- **Adopted date:** {notice.adopted_date or 'not supplied'}",
                f"- **First hearing:** {notice.first_hearing_date or 'not supplied'}",
                f"- **Final hearing:** {notice.final_hearing_date or 'not supplied'}",
                f"- **Link:** [DLCD {notice.kind} amendments report]({notice.link}) "
                "(the export has no item-level link)",
                "",
                "**Summary:**",
                "",
                notice.summary or "_No summary supplied._",
                "",
            ]
        )
        if notice.summary2:
            lines.extend(["**Additional summary / DLCD note:**", "", notice.summary2, ""])
        for key, value in notice.other_fields:
            lines.extend([f"**{key}:**", "", value or "_Not supplied._", ""])
    return "\n".join(lines)


def _report_kind(preamble: list[list[str]], csv_path: Path) -> Kind:
    text = " ".join(value for row in preamble for value in row).casefold()
    if re.search(r"\badopted amendments\b", text):
        return "adopted"
    if re.search(r"\bproposed amendments\b", text):
        return "proposed"
    stem = csv_path.stem.casefold()
    if stem.startswith("adopted"):
        return "adopted"
    if stem.startswith("proposed"):
        return "proposed"
    raise ValueError(f"Cannot determine report kind for {csv_path}")


def _optional_text(value: str) -> str | None:
    value = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    return value or None


def _first_value(values: dict[str, str | None], *names: str) -> str | None:
    return next((values[name] for name in names if values.get(name)), None)


def _date_key(value: str | None) -> date:
    if value:
        try:
            return datetime.strptime(value, "%B %d, %Y").date()
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
    return date.max


def _notice_sort_key(notice: Notice) -> tuple[date, str, str]:
    return _date_key(notice.received), notice.kind, notice.id


def _validate_ledger(entries: list[object]) -> None:
    ids: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"Ledger entry {index} must be a mapping")
        unknown = set(raw) - LEDGER_KEYS
        missing = LEDGER_KEYS - set(raw)
        if unknown:
            raise ValueError(f"Ledger entry {index} has unknown keys: {sorted(unknown)}")
        if missing:
            raise ValueError(f"Ledger entry {index} is missing keys: {sorted(missing)}")
        if any(
            not isinstance(raw[key], str) or not raw[key].strip()
            for key in ("id", "kind", "jurisdiction", "read_on", "read_by")
        ):
            raise ValueError(f"Ledger entry {index} has invalid required values")
        if raw["kind"] not in ("adopted", "proposed"):
            raise ValueError(f"Ledger entry {index} has invalid kind")
        if not isinstance(raw["verdict"], str) or raw["verdict"] not in VERDICTS:
            raise ValueError(f"Ledger entry {index} has invalid verdict")
        if raw["received"] is not None and not isinstance(raw["received"], str):
            raise ValueError(f"Ledger entry {index} has invalid received value")
        if any(
            raw[key] is not None and not isinstance(raw[key], str)
            for key in ("note", "followup")
        ):
            raise ValueError(f"Ledger entry {index} has invalid text value")
        if raw["id"] in ids:
            raise ValueError(f"Duplicate ledger id: {raw['id']}")
        ids.add(raw["id"])
