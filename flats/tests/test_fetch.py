"""Getting the code text in, and what happens when it changes.

The property under test is that the same page fetched twice produces the same
bytes, and that when it genuinely does not, somebody is told rather than the
hash being quietly repaired underneath a signature.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.verify import VerificationLog, sign
from flats.provenance.fetch import (
    citing,
    fetch_text,
    html_to_text,
    implausible,
    main,
    slice_between,
)
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
DOC = "or/multnomah/portland/33.110.txt"
URL = "https://www.portland.gov/code/33/100s/110"

#: Long enough to read like an actual chapter. That matters now: a document
#: this thin used to be storable, and the whole point of the plausibility guard
#: is that a page of site furniture can no longer stand behind a citation.
PAGE = """<!doctype html>
<html><head><title>Chapter 33.110</title><style>.x{color:red}</style></head>
<body>
<nav>Skip to main content</nav>
<h1>33.110 Single-Dwelling Zones</h1>
<p>33.110.220 Development Standards</p>
<ul><li>Front setback: 10&nbsp;feet.</li><li>Side setback: 5 feet.</li></ul>
<p>33.110.230 Other</p>
<p>33.110.240 Maximum building coverage is 45 percent of the site area.</p>
<p>33.110.245 Maximum height is 30 feet in the R5 zone.</p>
<p>33.110.250 Minimum lot area is 3,000 square feet per dwelling.</p>
<p>33.110.255 Minimum lot width is 25 feet and minimum depth is 60 feet.</p>
<p>33.110.260 Minimum street frontage is 25 feet.</p>
<p>33.110.265 Additional floor area may be allowed for 4 units.</p>
<p>33.110.270 Garage entrances are set back 18 feet from the property line.</p>
<p>33.110.275 Minimum outdoor area is 250 square feet per unit.</p>
<p>33.110.280 Maximum floor area ratio is 0.5 in the R7 zone.</p>
<p>33.110.285 Parking is 1 space per dwelling, or 2 spaces on lots over
5,000 square feet.</p>
<p>33.110.290 Buildings may not exceed 2 stories within 12 feet of a
side lot line abutting an alley.</p>
<p>33.110.295 A minimum of 20 percent of the site is landscaped.</p>
<script>analytics()</script>
<footer>Portland.gov</footer>
</body></html>
"""

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220"\n'
    f'  url: "{URL}"\n'
    "  retrieved: 2026-08-12\n"
    f'  quote: "{DOC}#L2"\n'
)


def page(_url: str) -> str:
    return PAGE


@pytest.fixture()
def bench(tmp_path: Path) -> dict:
    root = tmp_path / "jurisdictions"
    rules = root / f"{PORTLAND}.yaml"
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(
        "label: Portland\n" + CITE + "zones:\n  R5:\n    setback_front_ft: 10\n",
        encoding="utf-8",
    )
    return {"root": root, "docs": tmp_path / "docs", "log": tmp_path / "verifications.jsonl"}


def run(bench: dict, *argv: str, get=page) -> int:
    return main(
        [
            DOC,
            URL,
            "--docs",
            str(bench["docs"]),
            "--rules",
            str(bench["root"]),
            "--log",
            str(bench["log"]),
            *argv,
        ],
        get=get,
    )


# --- extraction -------------------------------------------------------


def test_the_prose_survives_and_the_furniture_does_not() -> None:
    text = html_to_text(PAGE)

    assert "33.110.220 Development Standards" in text
    assert "Front setback: 10 feet." in text
    assert "analytics()" not in text, "script contents are not prose"
    assert "color:red" not in text


def test_entities_come_out_as_characters() -> None:
    assert "10 feet" in html_to_text("<p>10&nbsp;feet</p>")


def test_the_same_page_extracts_to_the_same_bytes() -> None:
    # The property everything downstream rests on. If this is not true, every
    # value on the page flips to stale on a re-fetch for no reason.
    assert html_to_text(PAGE) == html_to_text(PAGE)


def test_blocks_land_on_their_own_lines() -> None:
    lines = html_to_text("<li>a</li><li>b</li>").splitlines()

    assert [line for line in lines if line] == ["a", "b"]


def test_runs_of_whitespace_collapse() -> None:
    assert html_to_text("<p>a     b\n\n\tc</p>").strip() == "a b c"


def test_line_numbers_follow_the_text_not_the_markup() -> None:
    # A quote is `path#L42`, so what counts as line 42 has to be a property of
    # the ordinance, not of how the codifier happened to wrap its HTML. One
    # block is one line, however the source is formatted.
    tight = html_to_text("<p>Front setback: 10 feet.</p><p>Side setback: 5 feet.</p>")
    reflowed = html_to_text("<p>Front setback:\n   10 feet.</p>\n\n<p>Side\nsetback: 5 feet.</p>")

    assert tight == reflowed
    assert [line for line in tight.splitlines() if line] == [
        "Front setback: 10 feet.",
        "Side setback: 5 feet.",
    ]


def test_plain_text_sources_pass_through() -> None:
    assert fetch_text("https://example.gov/x.txt", get=lambda _u: "10 feet\n") == "10 feet\n"


# --- slicing ----------------------------------------------------------


def test_a_slice_keeps_only_the_section_that_was_read() -> None:
    text = slice_between(html_to_text(PAGE), "33.110.220", "33.110.230")

    assert text.startswith("33.110.220")
    assert "Side setback" in text
    assert "33.110.230" not in text


def test_a_missing_marker_is_loud() -> None:
    # Silently storing the whole page instead would put every quote's line
    # numbers somewhere else entirely.
    with pytest.raises(ProvenanceError, match="start marker"):
        slice_between(html_to_text(PAGE), "33.999.000")


def test_a_missing_end_marker_is_loud() -> None:
    with pytest.raises(ProvenanceError, match="end marker"):
        slice_between(html_to_text(PAGE), "33.110.220", "33.999.000")


# --- storing ----------------------------------------------------------


def test_fetching_stores_the_document(bench: dict, capsys) -> None:
    assert run(bench) == 0

    doc = ProvenanceStore(bench["docs"]).load(DOC)
    assert doc.url == URL
    assert "Front setback: 10 feet." in doc.text
    assert "stored" in capsys.readouterr().out


def test_fetching_twice_reports_no_change(bench: dict, capsys) -> None:
    run(bench)
    capsys.readouterr()

    assert run(bench) == 0
    assert "unchanged" in capsys.readouterr().out


def test_a_changed_source_is_refused_by_default(bench: dict, capsys) -> None:
    run(bench)
    capsys.readouterr()
    amended = PAGE.replace("10&nbsp;feet", "20 feet")

    assert run(bench, get=lambda _u: amended) == 1

    err = capsys.readouterr().err
    assert "CHANGED" in err
    assert ProvenanceStore(bench["docs"]).load(DOC).text.count("10 feet") == 1, "nothing overwritten"


def test_refreshing_withdraws_the_reviews_that_relied_on_the_old_words(
    bench: dict, capsys
) -> None:
    # The point of the whole command. A re-fetch repairs the stored hash, so
    # without this a signature would go on standing over a sentence that has
    # since been amended.
    run(bench)
    value = load_rules(bench["root"])[PORTLAND].zones["R5"].values["setback_front_ft"]
    log = VerificationLog()
    log.append(
        sign(PORTLAND, "R5", "setback_front_ft", value, reviewer="sjk", reviewed=date(2026, 8, 14)),
        bench["log"],
    )
    capsys.readouterr()

    assert run(bench, "--refresh", get=lambda _u: PAGE.replace("10&nbsp;feet", "20 feet")) == 0

    out = capsys.readouterr().out
    assert "refreshed" in out
    assert "withdrew" in out
    reloaded = VerificationLog.load(bench["log"])
    assert reloaded.active() == {}, "the review no longer applies"
    assert len(reloaded) == 2, "and the record that it happened survives"


def test_refreshing_an_undisputed_document_withdraws_nothing(bench: dict, capsys) -> None:
    run(bench)
    capsys.readouterr()

    assert run(bench, "--refresh", get=lambda _u: PAGE.replace("10&nbsp;feet", "20 feet")) == 0
    assert "withdrew" not in capsys.readouterr().out


def test_a_marker_that_stops_matching_fails_before_anything_is_written(
    bench: dict, capsys
) -> None:
    assert run(bench, "--start", "33.999.000") == 1

    assert not ProvenanceStore(bench["docs"]).exists(DOC)
    assert "start marker" in capsys.readouterr().err


# --- who is affected --------------------------------------------------


def test_citing_finds_the_values_that_point_at_a_document(bench: dict) -> None:
    layers = load_rules(bench["root"])

    assert citing(layers, DOC) == [(PORTLAND, "R5", "setback_front_ft", ())]
    assert citing(layers, "or/multnomah/portland/33.120.txt") == []


# --- what is not a document -------------------------------------------


def test_an_empty_response_is_not_stored(bench: dict, capsys) -> None:
    # Municode answers 200 with an empty shell and renders in JavaScript. That
    # empty file was stored as "the code" and would have backed citations.
    assert run(bench, get=lambda _u: "") == 1

    assert "empty" in capsys.readouterr().err
    assert not (bench["docs"] / DOC).exists()


def test_a_page_of_site_furniture_is_not_stored(bench: dict, capsys) -> None:
    # Portland's HTML route for chapter 33.805 returns 3.5 KB of nav bar and
    # footer with one number in it. A signature over that looks like diligence.
    chrome = (
        "<html><body>"
        + "".join(f"<p>Menu item and some navigation text here</p>" for _ in range(60))
        + "<p>Contact us for information</p></body></html>"
    )

    assert run(bench, get=lambda _u: chrome) == 1
    assert "no regulatory text" in capsys.readouterr().err


def test_a_refusal_leaves_an_existing_document_alone(bench: dict, capsys) -> None:
    run(bench)
    capsys.readouterr()
    before = ProvenanceStore(bench["docs"]).load(DOC).sha256

    assert run(bench, get=lambda _u: "") == 1
    assert ProvenanceStore(bench["docs"]).load(DOC).sha256 == before


def test_allow_thin_is_available_for_a_genuinely_short_section(bench: dict) -> None:
    # Real sections are sometimes two paragraphs. The override exists so those
    # can be stored deliberately, by somebody who has read them.
    short = "<html><body><p>19.115.040 Setbacks are 5 feet.</p></body></html>"

    assert run(bench, "--allow-thin", get=lambda _u: short) == 0


def test_the_guard_accepts_an_ordinary_chapter(bench: dict, capsys) -> None:
    assert run(bench) == 0
    assert "stored" in capsys.readouterr().out


def test_implausible_names_its_reason() -> None:
    assert implausible("") == "the response was empty"
    assert "characters" in (implausible("33.110.220 Setbacks are 5 feet.") or "")
    assert implausible(html_to_text(PAGE)) is None


def test_a_pdf_page_with_no_content_stream_is_a_blank_page_not_a_broken_document() -> None:
    # Tualatin's Development Code carries a page with no /Contents key — legal
    # per the PDF spec, and pypdf's layout mode raises KeyError on it. That
    # killed the whole fetch, reporting a 900-page code as unreadable over one
    # blank sheet.
    from io import BytesIO

    from pypdf import PdfWriter

    from flats.provenance.fetch import pdf_to_text

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)

    assert pdf_to_text(buf.getvalue()).strip() == ""


def test_a_fused_extraction_is_measured_not_mistaken_for_an_empty_code() -> None:
    # Tualatin's layout-mode text reads "areasintheCitythatareappropriate..."
    # — section numbers survive, so scope works and candidates simply never
    # appear, which reads as "the code states nothing" when the truth is
    # "nothing could read it".
    from flats.provenance.fetch import fused

    fused_text = "thepurposeoftheLowDensityResidentialzoneistoprovide " * 50
    clean = "the purpose of the Low Density Residential zone is to provide " * 50

    assert fused(fused_text)
    assert not fused(clean)


def test_extraction_mode_is_declared_per_document_and_validated() -> None:
    import pytest as _pytest
    from pydantic import ValidationError

    from flats.rules.model import CodeDocument

    doc = CodeDocument(id="40-41", url="https://x.gov/code", extraction="plain")

    assert doc.extraction == "plain"
    assert CodeDocument(id="a", url="https://x.gov/c").extraction == "layout"
    with _pytest.raises(ValidationError):
        CodeDocument(id="a", url="https://x.gov/c", extraction="ocr")


# --- table geometry ---------------------------------------------------

# Wood Village's Table 220-3 shape: the columns are housing types, and a type
# with no standard in a row leaves an empty cell. Flattened to one cell per
# line, the empties vanish and nothing can say which type a value belongs to.
TYPE_COLUMNS = """<p>220.320 Lot Size.</p>
<table><caption>Table 220-3. Standards</caption>
<tr><th>Standard</th><th>Townhouse</th><th>Detached Single Dwelling</th></tr>
<tr><td>Minimum lot area</td><td>1,500 sq ft</td><td>10,000 sq ft</td></tr>
<tr><td>Minimum front setback</td><td>10 ft</td><td></td></tr>
</table>"""

# Clackamas ZDO Table 315-2 shape: one setback cell spanning every R zone.
MERGED_CELL = """<table>
<tr><th>Zone</th><th>Minimum lot area</th><th>Minimum front setback</th></tr>
<tr><td>R-5</td><td>5,000 sq ft</td><td rowspan="3">20 ft</td></tr>
<tr><td>R-7</td><td>7,000 sq ft</td></tr>
<tr><td>R-10</td><td>10,000 sq ft</td></tr>
</table>"""


def _grid(source: str) -> list[str]:
    return [line for line in html_to_text(source).splitlines() if line.strip()]


def test_a_table_renders_as_aligned_columns() -> None:
    lines = _grid(TYPE_COLUMNS)

    assert "Table 220-3. Standards" in lines
    header = next(line for line in lines if line.startswith("Standard"))
    area = next(line for line in lines if line.startswith("Minimum lot area"))
    assert header.index("Townhouse") == area.index("1,500")
    assert header.index("Detached") == area.index("10,000")


def test_an_empty_cell_keeps_its_column_open() -> None:
    # The failure the whole change exists to prevent: without the empty cell,
    # "10 ft" slides under the detached-single column and corroborates a
    # standard it was never written for.
    lines = _grid(TYPE_COLUMNS)
    header = next(line for line in lines if line.startswith("Standard"))
    setback = next(line for line in lines if line.startswith("Minimum front setback"))

    assert setback.index("10 ft") == header.index("Townhouse")
    assert len(setback.split()) == 5, "no value under the second type"


def test_a_spanned_cell_speaks_in_every_row_it_covers() -> None:
    # ZDO 315-2 prints the setbacks once for nine zones. Flat text drops it
    # onto one of them and the other eight lose their setbacks entirely.
    lines = _grid(MERGED_CELL)
    rows = [line for line in lines if line.startswith(("R-5", "R-7", "R-10"))]

    assert len(rows) == 3
    assert all(row.endswith("20 ft") for row in rows)


def test_a_spanned_table_reads_back_as_one_row_per_zone() -> None:
    from flats.encode.extract import extract

    text = html_to_text(MERGED_CELL)
    for zone, area in (("R-5", 5000), ("R-7", 7000), ("R-10", 10000)):
        read = extract(text, path="doc.txt", jurisdiction="or/clackamas/x", zone=zone)
        got = {(c.field, c.value) for c in read.candidates if c.source == "table"}
        assert ("min_lot_sqft", area) in got
        assert ("setback_front_ft", 20) in got


def test_column_alignment_survives_the_whitespace_collapse() -> None:
    # Prose keeps its runs of spaces collapsed — the alignment exemption is
    # for grid lines only, and a document that leaked it would churn its own
    # hash every time a codifier reindented a paragraph.
    assert "a b c" in html_to_text("<p>a     b\n\n\tc</p>")


def test_a_layout_table_is_not_gridded() -> None:
    # Codifiers wrap whole pages in tables. Aligning one produces a line
    # thousands of characters wide and welds navigation into the ordinance.
    wide = "<table><tr>" + "".join(f"<td>{'x' * 90}</td>" for _ in range(6)) + "</tr>"
    wide += "<tr>" + "".join(f"<td>{'y' * 90}</td>" for _ in range(6)) + "</tr></table>"

    assert max(len(line) for line in _grid(wide)) < 400


def test_a_nested_table_does_not_break_the_row_it_sits_in() -> None:
    source = (
        "<table><tr><th>Zone</th><th>Minimum lot area</th></tr>"
        "<tr><td>R-5</td><td><table><tr><td>5,000 sq ft</td></tr></table></td></tr></table>"
    )
    rows = [line for line in _grid(source) if line.startswith("R-5")]

    assert len(rows) == 1
    assert "5,000 sq ft" in rows[0]


def test_the_same_table_extracts_to_the_same_bytes() -> None:
    assert html_to_text(TYPE_COLUMNS) == html_to_text(TYPE_COLUMNS)


def test_a_stored_document_records_which_extractor_read_it(tmp_path: Path) -> None:
    from flats.provenance.fetch import EXTRACTOR, store_document

    store = ProvenanceStore(tmp_path)
    store_document(
        store, "or/x/y.txt", "https://example.gov/y", "10 feet\n", retrieved=date(2026, 1, 1)
    )

    assert store.load("or/x/y.txt").extractor == EXTRACTOR


def test_a_document_from_an_older_extractor_is_reported(tmp_path: Path) -> None:
    # Old sidecars have no extractor field, and the fix is a re-fetch that
    # moves every quote into the document — reported, never done quietly.
    from flats.provenance.fetch import Evidence

    store = ProvenanceStore(tmp_path)
    store.save(
        "or/x/y.txt", url="https://example.gov/y", text="10 feet\n", retrieved=date(2026, 1, 1)
    )

    assert store.load("or/x/y.txt").extractor == ""
    report = Evidence(stale_extraction=frozenset({"or/x/y.txt"}))
    assert any("re-extract" in line for line in report.lines())
